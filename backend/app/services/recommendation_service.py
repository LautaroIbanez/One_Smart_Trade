"""Recommendation service."""
from __future__ import annotations

import base64
import csv
import io
from datetime import datetime, time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import pandas as pd
import yaml

from app.analytics.trade_efficiency import TradeEfficiencyAnalyzer, TradeEfficiencyEvaluation
from app.core.config import settings
from app.core.database import SessionLocal
from sqlalchemy import and_, case, desc, func, or_, select
from app.backtesting.auto_shutdown import AutoShutdownManager, AutoShutdownPolicy, StrategyMetrics
from app.backtesting.risk_sizing import RiskSizer
from app.backtesting.tracking_error import TrackingErrorCalculator, calculate_tracking_error
from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.core.logging import logger
from app.db.crud import (
    calculate_production_drawdown,
    close_recommendation,
    create_recommendation,
    get_current_champion,
    get_latest_recommendation,
    get_open_recommendation,
    get_recommendation_history as db_history,
)
from app.db.models import RecommendationORM
from app.quant.signal_engine import generate_signal
from app.services.alert_service import AlertService
from app.services.strategy_service import StrategyService
from app.services.user_portfolio_service import UserPortfolioService
from app.services.user_risk_profile_service import UserRiskProfileService, UserRiskContext
from app.services.exposure_ledger_service import ExposureLedgerService
from app.signals.loggers import SignalLogRecord, log_signal_event
from app.confidence.service import ConfidenceService
from app.observability.risk_metrics import (
    USER_RISK_REJECTIONS_TOTAL,
    USER_RUIN_PROBABILITY,
    USER_EXPOSURE_RATIO,
    USER_EXPOSURE_LIMIT_ALERT,
)


class RecommendationService:
    """Service for managing trading recommendations."""

    def __init__(
        self,
        session=None,
        shutdown_manager: AutoShutdownManager | None = None,
    ):
        self._cache: Optional[dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self.session = session
        self.curation = DataCuration()
        self.alerts = AlertService()
        self.strategy_service = StrategyService()
        self.trade_efficiency = TradeEfficiencyAnalyzer()
        self._champion_cache: Optional[dict[str, Any]] = None
        self.shutdown_manager = shutdown_manager or AutoShutdownManager(
            policy=AutoShutdownPolicy()
        )
        self.confidence_service = ConfidenceService()
        self.user_portfolio_service = UserPortfolioService(session=session)
        self.user_risk_profile_service = UserRiskProfileService(session=session)
        self.exposure_ledger_service = ExposureLedgerService(session=session)
        self.tracking_error_threshold_pct = self._load_tracking_error_threshold()
        # Risk manager will be initialized per-user with real equity
        self._default_risk_manager = UnifiedRiskManager(
            base_capital=10000.0,
            risk_budget_pct=1.0,
            max_drawdown_pct=50.0,
        )

    def _log_signal_emission(self, rec, signal_payload: dict[str, Any]) -> int | None:
        """Persist structured signal metadata for calibration."""
        try:
            timestamp = signal_payload.get("timestamp")
            decision_ts = datetime.utcnow()
            if isinstance(timestamp, str):
                try:
                    decision_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    decision_ts = datetime.utcnow()

            factors = signal_payload.get("factors") or {}
            signal_breakdown = signal_payload.get("signal_breakdown") or {}
            votes = signal_payload.get("votes")
            risk_metrics = signal_payload.get("risk_metrics")

            market_regime = (
                factors.get("market_regime")
                or factors.get("regime_label")
                or factors.get("regime_name")
            )

            vol_bucket = None
            for key in ("vol_regime_1d", "vol_regime_4h", "vol_regime_1h"):
                if key in factors:
                    idx = factors.get(key)
                    if isinstance(idx, (int, float)):
                        bucket_map = {0: "low", 1: "balanced", 2: "high"}
                        vol_bucket = bucket_map.get(int(idx), f"bucket_{int(idx)}")
                        break

            horizon_minutes = signal_payload.get("horizon_minutes") or 1440
            strategy_id = self._resolve_strategy_id(signal_payload)

            # Get risk_of_ruin from sizing if available
            suggested_sizing = signal_payload.get("suggested_sizing") or {}
            risk_of_ruin = suggested_sizing.get("risk_of_ruin")
            ruin_adjustment = suggested_sizing.get("ruin_adjustment")

            metadata = {
                "signal_breakdown": signal_breakdown,
                "votes": votes,
                "risk_metrics": risk_metrics,
                "entry_range": signal_payload.get("entry_range"),
                "stop_loss_take_profit": signal_payload.get("stop_loss_take_profit"),
                "calibration_metadata": signal_payload.get("calibration_metadata"),
            }
            
            # Add risk_of_ruin and ruin_adjustment to metadata for audit
            if risk_of_ruin is not None:
                metadata["risk_of_ruin"] = float(risk_of_ruin)
            if ruin_adjustment:
                metadata["ruin_adjustment"] = ruin_adjustment

            confidence_raw = signal_payload.get("confidence_raw", signal_payload.get("confidence", 0.0))
            record = SignalLogRecord(
                strategy_id=strategy_id,
                signal=signal_payload["signal"],
                confidence_raw=float(confidence_raw),
                decision_timestamp=decision_ts,
                confidence_calibrated=signal_payload.get("confidence_calibrated"),
                recommendation_id=rec.id,
                market_regime=market_regime,
                vol_bucket=vol_bucket,
                features_regimen=factors,
                metadata=metadata,
                outcome="open",
                horizon_minutes=horizon_minutes,
            )
            log_id = log_signal_event(record, session=self.session)
            return log_id
        except Exception as exc:
            logger.warning(
                "Failed to log signal emission",
                extra={"recommendation_id": getattr(rec, "id", None), "error": str(exc)},
            )
            return None

    def _resolve_strategy_id(self, signal_payload: dict[str, Any]) -> str:
        champion_cfg = signal_payload.get("champion_config") or self._champion_cache or {}
        for key in ("params_id", "params_digest", "objective"):
            value = champion_cfg.get(key)
            if value:
                return str(value)
        return "ensemble_core"

    def _build_confidence_band(self, confidence_calibrated: float | None, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if confidence_calibrated is None:
            return None
        meta = metadata or {}
        ece = meta.get("ece")
        margin = 3.0
        if isinstance(ece, (int, float)):
            margin = max(2.0, min(15.0, ece * 100.0 * 1.5))
        lower = max(0.0, round(confidence_calibrated - margin, 1))
        upper = min(100.0, round(confidence_calibrated + margin, 1))
        note = meta.get("band_note") or (
            f"Histórico en régimen {meta.get('regime', 'ensemble')}" if meta.get("regime") else None
        )
        band = {
            "lower": lower,
            "upper": upper,
            "source": meta.get("calibrator_type") or meta.get("regime") or "ensemble_core",
        }
        if note:
            band["note"] = note
        return band

    def _finalize_confidence_fields(self, payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> None:
        raw = payload.get("confidence_raw", payload.get("confidence"))
        try:
            raw_value = round(float(raw or 0.0), 1)
        except (TypeError, ValueError):
            raw_value = 0.0
        payload["confidence_raw"] = raw_value
        payload["confidence"] = raw_value
        cal = payload.get("confidence_calibrated")
        if cal is None:
            cal = raw_value
        else:
            try:
                cal = round(float(cal), 1)
            except (TypeError, ValueError):
                cal = raw_value
        payload["confidence_calibrated"] = cal
        band = payload.get("confidence_band") or self._build_confidence_band(cal, metadata)
        if band:
            payload["confidence_band"] = band

    def _apply_confidence_calibration(self, signal_payload: dict[str, Any]) -> None:
        """Enrich signal payload with calibrated confidence."""
        try:
            confidence_raw = float(signal_payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence_raw = 0.0
        signal_payload["confidence_raw"] = round(confidence_raw, 1)
        factors = signal_payload.get("factors") or {}
        regime = (
            signal_payload.get("market_regime")
            or factors.get("market_regime")
            or factors.get("regime_label")
            or factors.get("regime_name")
        )
        calibrated, metadata = self.confidence_service.calibrate(confidence_raw, regime=regime)
        signal_payload["confidence_calibrated"] = round(calibrated, 1) if calibrated is not None else None
        if metadata:
            signal_payload.setdefault("calibration_metadata", metadata)
            breakdown = signal_payload.setdefault("signal_breakdown", {})
            breakdown["calibration"] = metadata
        band = self._build_confidence_band(signal_payload.get("confidence_calibrated"), signal_payload.get("calibration_metadata"))
        if band:
            signal_payload["confidence_band"] = band
            breakdown = signal_payload.setdefault("signal_breakdown", {})
            calibration_block = breakdown.setdefault("calibration", {})
            calibration_block["confidence_band"] = band
        self._finalize_confidence_fields(signal_payload, signal_payload.get("calibration_metadata"))

    def _apply_trade_efficiency(self, signal: dict[str, Any]) -> tuple[bool, TradeEfficiencyEvaluation]:
        """Enforce historical MAE/MFE constraints before publishing a signal."""
        symbol = signal.get("symbol") or self._champion_cache.get("symbol") if self._champion_cache else None
        symbol = symbol or "BTCUSDT"
        factors = signal.get("factors") or {}
        regime = (
            factors.get("optimizer_regime")
            or signal.get("market_regime")
            or factors.get("market_regime")
            or factors.get("regime_label")
        )

        evaluation = self.trade_efficiency.evaluate_signal(signal, symbol=symbol, regime=regime)
        signal.setdefault("risk_metrics", {})["efficiency_summary"] = evaluation.summary
        signal["trade_efficiency"] = evaluation.to_dict()
        return evaluation.accepted, evaluation

    def _get_open_recommendation(self):
        if self.session is not None:
            return get_open_recommendation(self.session)
        with SessionLocal() as db:
            try:
                rec = get_open_recommendation(db)
                if rec:
                    db.expunge(rec)
                return rec
            finally:
                db.close()

    def _cache_result(self, rec, include_sizing: bool = True, user_id: str | None = None) -> dict[str, Any]:
        """Convert RecommendationORM to dict, including ID and metadata."""
        result = self._from_orm(rec)
        self._cache = result
        self._cache_timestamp = rec.created_at
        self._finalize_confidence_fields(result, result.get("calibration_metadata") or {})
        
        # Add suggested sizing if entry/stop are available
        if include_sizing:
            sizing_result = self._calculate_position_sizing(result, user_id=user_id)
            if sizing_result:
                # Check if sizing was blocked due to missing equity, ruin risk, or risk limits
                if sizing_result.get("status") in ("missing_equity", "ruin_risk_too_high", "risk_blocked", "exposure_limit_exceeded"):
                    result["sizing_status"] = sizing_result["status"]
                    result["sizing_message"] = sizing_result.get("message")
                    result["suggested_sizing"] = sizing_result
                    result["recommended_position_size"] = None
                    result["risk_pct"] = None
                    result["capital_assumed"] = None
                    result["recommended_risk_fraction"] = None
                    result["requires_capital_input"] = sizing_result.get("requires_capital_input", False)
                    if sizing_result.get("status") == "risk_blocked":
                        result["risk_limit_violations"] = sizing_result.get("violations", [])
                    elif sizing_result.get("status") == "exposure_limit_exceeded":
                        result["exposure_summary"] = {
                            "current_exposure_multiplier": sizing_result.get("current_exposure_multiplier"),
                            "projected_exposure_multiplier": sizing_result.get("projected_exposure_multiplier"),
                            "limit_multiplier": sizing_result.get("limit_multiplier"),
                            "beta_value": sizing_result.get("beta_value"),
                        }
                else:
                    # Valid sizing result
                result["suggested_sizing"] = sizing_result
                result["recommended_position_size"] = sizing_result.get("units", 0.0)
                result["risk_pct"] = sizing_result.get("risk_pct", 0.0)
                result["capital_assumed"] = sizing_result.get("capital_used", 0.0)
                result["recommended_risk_fraction"] = sizing_result.get("risk_pct", 0.5) / 100.0
                    result["exposure_multiplier"] = sizing_result.get("exposure_multiplier")
                    result["risk_of_ruin"] = sizing_result.get("risk_of_ruin")
                    result["limits_check"] = sizing_result.get("limits_check", {})
            else:
                # No sizing available (missing entry/stop)
                result["suggested_sizing"] = None
                result["recommended_position_size"] = None
                result["risk_pct"] = None
                result["capital_assumed"] = None
                result["recommended_risk_fraction"] = None
        else:
            result["recommended_risk_fraction"] = None
        
        # Add disclaimer
        result.setdefault("disclaimer", "This is not financial advice. Trading cryptocurrencies involves significant risk. Position sizing requires your portfolio data or explicit capital input via /api/v1/risk/sizing.")
        
        return result
    
    def _calculate_position_sizing(self, recommendation: dict[str, Any], user_id: str | None = None) -> dict[str, Any] | None:
        """
        Calculate position sizing using real user risk context.
        
        Returns None if user has no equity data (forces user to provide capital via /api/v1/risk/sizing).
        """
        entry_range = recommendation.get("entry_range", {})
        stop_loss_tp = recommendation.get("stop_loss_take_profit", {})
        entry = entry_range.get("optimal")
        stop = stop_loss_tp.get("stop_loss")
        
        if not entry or not stop:
            return None
        
        # Get comprehensive user risk context
        ctx = self.user_risk_profile_service.get_context(user_id, base_risk_pct=1.0)
        
        # CRITICAL: If user has no equity data, return None to force explicit capital input
        if not ctx.has_data or ctx.equity <= 0:
            logger.info(f"User {user_id or 'anonymous'} has no equity data - sizing requires explicit capital")
            user_id_str = str(user_id or "default")
            USER_RISK_REJECTIONS_TOTAL.labels(user_id=user_id_str, rejection_type="missing_equity").inc()
            return {
                "status": "missing_equity",
                "message": "Conecta tu cuenta o ingresa capital para recibir sizing personalizado. Usa /api/v1/risk/sizing con tu capital disponible.",
                "requires_capital_input": True,
            }
        
        # Initialize risk manager with user's real equity
        risk_manager = UnifiedRiskManager(
            base_capital=ctx.equity,
            risk_budget_pct=ctx.base_risk_pct,
            max_drawdown_pct=50.0,
        )
        
        # Update risk manager with user's current drawdown state
        risk_manager.current_equity = ctx.equity
        risk_manager.peak_equity = ctx.peak_equity if ctx.peak_equity else ctx.equity
        risk_manager.current_drawdown_pct = ctx.drawdown_pct
        
        # Get exposure profile multiplier (0.0 to 1.0) based on drawdown and exposure
        exposure_multiplier = risk_manager.exposure_profile()
        
        # Apply risk capacity from context (additional constraint)
        risk_capacity = ctx.risk_capacity
        effective_exposure_multiplier = min(exposure_multiplier, risk_capacity)
        
        # Adjust base risk percentage by exposure multiplier
        adjusted_risk_pct = ctx.base_risk_pct * effective_exposure_multiplier
        
        # Calculate sizing using UnifiedRiskManager with user's real data
        sizing_result = risk_manager.size_trade(
            entry=entry,
            stop=stop,
            user_equity=ctx.equity,
            user_drawdown=ctx.drawdown_pct,
            volatility_estimate=ctx.realized_vol,
            base_risk_pct=adjusted_risk_pct,
            dd_limit=50.0,
            min_risk_pct=0.2,
        )
        
        # Simulate ruin risk with user's actual trading metrics
        from app.core.config import settings
        
        # Use win_rate and payoff_ratio from context if available
        win_rate = ctx.win_rate
        payoff_ratio = ctx.payoff_ratio
        trade_history = ctx.trade_history or []
        
        # Update risk manager with trade history for drawdown tracking
        if trade_history:
            risk_manager.update_drawdown(ctx.equity, trade_history)
        
        # Simulate ruin with user's actual metrics
        if win_rate is not None and payoff_ratio is not None:
            risk_of_ruin = risk_manager.simulate_ruin(
                win_rate=win_rate,
                payoff_ratio=payoff_ratio,
            )
        elif trade_history:
            # Use trade history to estimate
            risk_of_ruin = risk_manager.simulate_ruin()
        else:
            # No data, use conservative default
            risk_of_ruin = 0.0
        
        # Apply ruin risk adjustment with smooth reduction curve
        RUIN_THRESHOLD = settings.RISK_OF_RUIN_MAX  # Default: 5%
        ruin_multiplier = 1.0
        sizing_adjusted = False
        
        if risk_of_ruin > RUIN_THRESHOLD:
            # Calculate smooth reduction multiplier
            # At threshold, multiplier = 1.0
            # At 2x threshold, multiplier = 0.0 (but we cap at 0.1 minimum)
            # Formula: max(0.1, 1 - (ruin - threshold) / threshold)
            excess_ruin = risk_of_ruin - RUIN_THRESHOLD
            ruin_multiplier = max(0.1, 1.0 - (excess_ruin / RUIN_THRESHOLD))
            sizing_adjusted = True
            
            logger.warning(
                f"User {user_id} risk of ruin {risk_of_ruin:.2%} exceeds threshold {RUIN_THRESHOLD:.2%} - "
                f"applying sizing reduction multiplier {ruin_multiplier:.2%}"
            )
            
            # Update Prometheus metrics
            user_id_str = str(user_id or "default")
            USER_RUIN_PROBABILITY.labels(user_id=user_id_str).set(risk_of_ruin)
            
            # If multiplier is too low (below 0.2), block completely
            if ruin_multiplier < 0.2:
                USER_RISK_REJECTIONS_TOTAL.labels(user_id=user_id_str, rejection_type="ruin_risk_too_high").inc()
                return {
                    "status": "ruin_risk_too_high",
                    "message": f"El riesgo de ruina ({risk_of_ruin:.2%}) excede significativamente el umbral seguro ({RUIN_THRESHOLD:.2%}). Reduce exposición o espera recuperación de drawdown.",
                    "risk_of_ruin": risk_of_ruin,
                    "threshold": RUIN_THRESHOLD,
                    "current_equity": ctx.equity,
                    "current_drawdown_pct": ctx.drawdown_pct,
                    "win_rate": win_rate,
                    "payoff_ratio": payoff_ratio,
                }
        
        # Apply ruin multiplier to sizing if needed
        if sizing_adjusted and sizing_result.get("units", 0.0) > 0:
            original_units = sizing_result.get("units", 0.0)
            adjusted_units = original_units * ruin_multiplier
            sizing_result["units"] = adjusted_units
            sizing_result["notional"] = adjusted_units * entry
            sizing_result["risk_amount"] = adjusted_units * abs(entry - stop)
            sizing_result["risk_percentage"] = (sizing_result["risk_amount"] / ctx.equity * 100.0) if ctx.equity > 0 else 0.0
            sizing_result["ruin_adjustment"] = {
                "applied": True,
                "multiplier": ruin_multiplier,
                "original_units": original_units,
                "adjusted_units": adjusted_units,
                "risk_of_ruin": risk_of_ruin,
                "threshold": RUIN_THRESHOLD,
            }
        
        # Check for sizing errors
        if sizing_result.get("error"):
            if sizing_result.get("sizing_method") == "insufficient_capital":
                logger.warning(f"User {user_id} has insufficient capital: {sizing_result.get('error')}")
                return {
                    "error": sizing_result["error"],
                    "capital_required": sizing_result.get("capital_required", 0.0),
                    "capital_available": sizing_result.get("capital_available", 0.0),
                    "note": "Insufficient capital to open position with minimum risk. Please deposit more funds.",
                    "capital_used": ctx.equity,
                    "risk_pct": adjusted_risk_pct,
                }
            return None
        
        # Apply dynamic risk limits before returning sizing
        notional = sizing_result.get("notional", 0.0)
        symbol = recommendation.get("symbol", "BTCUSDT")  # Default symbol
        signal = recommendation.get("signal", "BUY")
        
        # Calculate beta for the symbol
        from app.core.config import settings
        beta_value = self.exposure_ledger_service.calculate_beta(symbol)
        
        # Validate aggregate exposure with beta-adjusted notional
        exposure_validation = self.exposure_ledger_service.validate_new_position(
            user_id=user_id,
            user_equity=ctx.equity,
            new_notional=notional,
            new_beta=beta_value,
            limit_multiplier=settings.EXPOSURE_LIMIT_MULTIPLIER,
        )
        
        # Update Prometheus metrics
        user_id_str = str(user_id or "default")
        USER_EXPOSURE_RATIO.labels(user_id=user_id_str).set(exposure_validation["current_exposure_multiplier"])
        
        # Check if exposure exceeds 80% of limit (alert threshold)
        exposure_utilization = exposure_validation["current_exposure_multiplier"] / exposure_validation["limit_multiplier"] if exposure_validation["limit_multiplier"] > 0 else 0.0
        if exposure_utilization > 0.8:
            USER_EXPOSURE_LIMIT_ALERT.labels(user_id=user_id_str).set(1.0)
        else:
            USER_EXPOSURE_LIMIT_ALERT.labels(user_id=user_id_str).set(0.0)
        
        # If aggregate exposure would exceed limit, block or reduce
        if not exposure_validation["allowed"]:
            current_exp = exposure_validation["current_exposure_multiplier"]
            projected_exp = exposure_validation["projected_exposure_multiplier"]
            limit_exp = exposure_validation["limit_multiplier"]
            
            logger.warning(
                f"User {user_id} position sizing blocked by aggregate exposure limit: "
                f"current={current_exp:.2f}×, projected={projected_exp:.2f}×, limit={limit_exp:.2f}×"
            )
            
            # Update Prometheus metrics
            user_id_str = str(user_id or "default")
            USER_RISK_REJECTIONS_TOTAL.labels(user_id=user_id_str, rejection_type="exposure_limit_exceeded").inc()
            
            # Build UI-friendly message
            ui_message = (
                f"Exposición actual {current_exp:.1f}×, tras esta señal sería {projected_exp:.1f}× "
                f"(> límite {limit_exp:.1f}×) → señal rechazada"
            )
            
            return {
                "status": "exposure_limit_exceeded",
                "reason": exposure_validation["reason"],
                "message": ui_message,
                "current_exposure_multiplier": current_exp,
                "projected_exposure_multiplier": projected_exp,
                "limit_multiplier": limit_exp,
                "current_beta_adjusted_notional": exposure_validation["current_beta_adjusted_notional"],
                "projected_beta_adjusted_notional": exposure_validation["projected_beta_adjusted_notional"],
                "limit_beta_adjusted_notional": exposure_validation.get("limit_beta_adjusted_notional", 0.0),
                "exceeds_by": exposure_validation.get("exceeds_by", 0.0),
                "capital_used": ctx.equity,
                "requested_notional": notional,
                "beta_value": beta_value,
            }
        
        # Get open positions for correlation limit validation
        open_positions = self.user_risk_profile_service.get_open_positions(user_id)
        
        # Calculate correlation matrix if we have multiple symbols (for now, single symbol so skip)
        correlation_matrix = None  # TODO: Implement when multi-symbol support is added
        
        # Apply other limits (concentration, correlation)
        limits_result = risk_manager.apply_limits(
            position_request={
                "symbol": symbol,
                "notional": notional,
                "entry": entry,
                "side": signal,
            },
            user_equity=ctx.equity,
            existing_positions=open_positions,
            exposure_cap=1.0,  # 100% of equity max (already validated by exposure ledger)
            concentration_limit_pct=30.0,  # 30% per symbol
            correlation_threshold=0.7,  # 70% correlation threshold
            correlation_matrix=correlation_matrix,
        )
        
        # If limits are violated, block the sizing
        if not limits_result["allowed"]:
            logger.warning(
                f"User {user_id} position sizing blocked by risk limits: {limits_result['reason']}",
                extra={"violations": limits_result.get("violations", [])}
            )
            
            # Update Prometheus metrics
            user_id_str = str(user_id or "default")
            USER_RISK_REJECTIONS_TOTAL.labels(user_id=user_id_str, rejection_type="risk_blocked").inc()
            
            # Log incident for audit
            self._log_risk_limit_incident(
                user_id=user_id,
                recommendation_id=recommendation.get("id"),
                violations=limits_result.get("violations", []),
                reason=limits_result["reason"],
                position_request={
                    "symbol": symbol,
                    "notional": notional,
                    "entry": entry,
                    "side": signal,
                },
            )
            
            return {
                "status": "risk_blocked",
                "reason": limits_result["reason"],
                "violations": limits_result.get("violations", []),
                "message": f"Límites de riesgo excedidos: {limits_result['reason']}. Reduzca exposición o espere a cerrar posiciones existentes.",
                "capital_used": ctx.equity,
                "requested_notional": notional,
            }
        
        # Build comprehensive response
        result = {
            "units": sizing_result.get("units", 0.0),
            "notional": sizing_result.get("notional", 0.0),
            "risk_amount": sizing_result.get("risk_amount", 0.0),
            "risk_percentage": sizing_result.get("risk_percentage", 0.0),
            "risk_pct": sizing_result.get("risk_pct", adjusted_risk_pct),
            "capital_used": ctx.equity,
            "sizing_method": sizing_result.get("sizing_method", "risk_based"),
            "adjustments": sizing_result.get("adjustments", {}),
            "exposure_multiplier": round(exposure_multiplier, 4),
            "risk_capacity": round(risk_capacity, 4),
            "effective_exposure_multiplier": round(effective_exposure_multiplier, 4),
            "risk_of_ruin": round(risk_of_ruin, 4),
            "current_drawdown_pct": ctx.drawdown_pct,
            "current_exposure_pct": ctx.avg_exposure_pct,
            "effective_leverage": ctx.effective_leverage,
            "win_rate": ctx.win_rate,
            "payoff_ratio": ctx.payoff_ratio,
            "limits_check": {
                "passed": True,
                "violations": [],
            },
            "exposure_summary": {
                "current_exposure_multiplier": exposure_validation["current_exposure_multiplier"],
                "projected_exposure_multiplier": exposure_validation["projected_exposure_multiplier"],
                "limit_multiplier": exposure_validation["limit_multiplier"],
                "beta_value": beta_value,
            },
        }
        
        # Update Prometheus metrics for successful sizing
        user_id_str = str(user_id or "default")
        USER_RUIN_PROBABILITY.labels(user_id=user_id_str).set(risk_of_ruin)
        USER_EXPOSURE_RATIO.labels(user_id=user_id_str).set(exposure_validation["current_exposure_multiplier"])
        
        # Check exposure alert threshold (80% of limit)
        exposure_utilization = exposure_validation["current_exposure_multiplier"] / exposure_validation["limit_multiplier"] if exposure_validation["limit_multiplier"] > 0 else 0.0
        if exposure_utilization > 0.8:
            USER_EXPOSURE_LIMIT_ALERT.labels(user_id=user_id_str).set(1.0)
        else:
            USER_EXPOSURE_LIMIT_ALERT.labels(user_id=user_id_str).set(0.0)
        
        # Add ruin adjustment info if applied
        if sizing_result.get("ruin_adjustment"):
            result["ruin_adjustment"] = sizing_result["ruin_adjustment"]
        
        # Add informative note
        ruin_note = ""
        if sizing_adjusted:
            ruin_note = f" Ajuste por riesgo de ruina aplicado: multiplicador {ruin_multiplier:.1%}."
        
        # Build exposure summary message
        current_exp = exposure_validation["current_exposure_multiplier"]
        projected_exp = exposure_validation["projected_exposure_multiplier"]
        limit_exp = exposure_validation["limit_multiplier"]
        exposure_msg = f"Exposición actual {current_exp:.1f}×, tras esta señal sería {projected_exp:.1f}× (límite {limit_exp:.1f}×)."
        
        result["note"] = (
            f"Calculado con tu equity real (${ctx.equity:,.2f}), drawdown {ctx.drawdown_pct:.2f}%, "
            f"exposición {ctx.avg_exposure_pct:.2f}%. Multiplicador de exposición: {exposure_multiplier:.2%}, "
            f"capacidad de riesgo: {risk_capacity:.2%}. Riesgo de ruina: {risk_of_ruin:.2%} "
            f"(win_rate: {ctx.win_rate:.1%} si disponible, payoff: {ctx.payoff_ratio:.2f} si disponible). "
            f"{exposure_msg} "
            f"Límites de riesgo validados: exposición agregada (beta-ajustada), concentración y correlación.{ruin_note}"
        )
        
        return result

    def _reset_cache(self) -> None:
        self._cache = None
        self._cache_timestamp = None

    def _log_risk_limit_incident(
        self,
        user_id: str | None,
        recommendation_id: int | None,
        violations: list[dict[str, Any]],
        reason: str,
        position_request: dict[str, Any],
    ) -> None:
        """
        Log risk limit violation incident for audit trail.
        
        Args:
            user_id: User ID
            recommendation_id: Recommendation ID if available
            violations: List of violation details
            reason: Human-readable reason
            position_request: Position request that was blocked
        """
        try:
            logger.warning(
                "Risk limit violation blocked position sizing",
                extra={
                    "user_id": user_id,
                    "recommendation_id": recommendation_id,
                    "violations": violations,
                    "reason": reason,
                    "position_request": position_request,
                    "incident_type": "risk_limit_violation",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            # TODO: Store in audit table for compliance/analysis
            # Could create RiskLimitIncidentORM table if needed
        except Exception as e:
            logger.error(f"Failed to log risk limit incident: {e}", exc_info=True)

    async def _check_shutdown_status(self) -> dict[str, Any]:
        """
        Check shutdown status using production metrics.
        
        Returns:
            Dict with shutdown status and metrics
        """
        if not self.shutdown_manager:
            return {"shutdown": False, "reason": "no_shutdown_manager"}
        
        db = self.session or SessionLocal()
        try:
            # Get production drawdown
            dd_info = calculate_production_drawdown(db)
            current_dd_pct = dd_info.get("max_drawdown_pct", 0.0)
            equity_curve = dd_info.get("equity_curve", [1.0])
            
            # Get recommendation history for metrics
            history = db_history(db, limit=100)
            trades = []
            for rec in history:
                if rec.status == "closed" and rec.exit_price and rec.entry_price:
                    # Calculate PnL
                    if rec.side == "BUY":
                        pnl = (rec.exit_price - rec.entry_price) / rec.entry_price * 100
                    else:
                        pnl = (rec.entry_price - rec.exit_price) / rec.entry_price * 100
                    
                    trades.append({
                        "pnl": pnl,
                        "return_pct": pnl,
                        "entry_price": rec.entry_price,
                        "exit_price": rec.exit_price,
                        "side": rec.side,
                    })
            
            # Create strategy metrics
            current_equity = equity_curve[-1] if equity_curve else 1.0
            peak_equity = max(equity_curve) if equity_curve else 1.0
            
            strategy_metrics = StrategyMetrics(
                current_drawdown_pct=current_dd_pct,
                peak_equity=peak_equity,
                current_equity=current_equity,
                trades=trades if trades else None,
                equity_curve=equity_curve,
            )
            
            # Evaluate shutdown policy
            return self.shutdown_manager.evaluate(strategy_metrics)
        finally:
            if not self.session:
                db.close()

    async def generate_recommendation(self) -> Optional[dict[str, Any]]:
        """Generate a new recommendation using curated datasets."""
        from app.quant.narrative import build_narrative

        champion = self._ensure_champion_context(run_alerts=True)
        if champion is None:
            return {"status": "error", "reason": "no_champion_configuration"}

        # Check auto-shutdown before generating recommendation
        if self.shutdown_manager:
            shutdown_status = await self._check_shutdown_status()
            if shutdown_status["shutdown"]:
                logger.warning(
                    "Auto-shutdown active, blocking recommendation generation",
                    extra={"reason": shutdown_status["shutdown_reason"]},
                )
                return {
                    "status": "shutdown",
                    "reason": shutdown_status["shutdown_reason"],
                    "shutdown_status": shutdown_status,
                }
            
            # Apply size reduction if needed
            if shutdown_status["size_reduction"]:
                logger.info(
                    "Size reduction active",
                    extra={
                        "factor": shutdown_status["size_reduction_factor"],
                        "reason": shutdown_status["size_reduction_reason"],
                    },
                )
        
        # Validate user risk context before generating recommendation
        ctx = self.user_risk_profile_service.get_context(settings.DEFAULT_USER_ID, base_risk_pct=1.0)
        
        # Check if user is overexposed (should block new signals)
        if ctx.has_data and ctx.is_overexposed:
            logger.warning(
                f"User {settings.DEFAULT_USER_ID} is overexposed (leverage: {ctx.effective_leverage:.2f}x, "
                f"exposure: {ctx.avg_exposure_pct:.2f}%) - blocking recommendation generation"
            )
            return {
                "status": "overexposed",
                "reason": f"Exposición excesiva detectada (apalancamiento: {ctx.effective_leverage:.2f}×, exposición: {ctx.avg_exposure_pct:.2f}%). Reduzca posiciones abiertas antes de recibir nuevas señales.",
                "effective_leverage": float(ctx.effective_leverage),
                "current_exposure_pct": float(ctx.avg_exposure_pct),
                "current_equity": float(ctx.equity),
            }
        
        # Check cooldown status before generating recommendation
        from app.db.crud import get_user_risk_state
        db = self.session or SessionLocal()
        try:
            user_state = get_user_risk_state(db, settings.DEFAULT_USER_ID)
            if user_state:
                # Check cooldown
                if user_state.cooldown_until:
                    now = datetime.utcnow()
                    cooldown_dt = user_state.cooldown_until
                    now_tz = now.replace(tzinfo=cooldown_dt.tzinfo) if cooldown_dt.tzinfo else now
                    if cooldown_dt > now_tz:
                        delta = cooldown_dt - now_tz
                        cooldown_remaining = int(delta.total_seconds())
                        logger.warning(
                            "Cooldown active, blocking recommendation generation",
                            extra={
                                "reason": user_state.cooldown_reason,
                                "remaining_seconds": cooldown_remaining,
                            },
                        )
                    # Get contextual educational articles for cooldown
                    from app.db.crud import get_contextual_articles
                    contextual_articles = []
                    try:
                        articles = get_contextual_articles(db, settings.DEFAULT_USER_ID, trigger_type="cooldown", limit=3)
                        contextual_articles = [
                            {
                                "id": a.id,
                                "title": a.title,
                                "slug": a.slug,
                                "summary": a.summary,
                                "category": a.category,
                            }
                            for a in articles
                        ]
                    except Exception as e:
                        logger.warning(f"Failed to fetch contextual articles: {e}", exc_info=True)
                    
                    return {
                        "status": "cooldown",
                        "reason": user_state.cooldown_reason or "Período de enfriamiento activo",
                        "cooldown_until": cooldown_dt.isoformat(),
                        "cooldown_remaining_seconds": cooldown_remaining,
                        "contextual_articles": contextual_articles,
                    }
                
                # Check leverage hard stop
                if user_state.leverage_hard_stop:
                    logger.warning(
                        "Leverage hard stop active, blocking recommendation generation",
                        extra={
                            "leverage": user_state.effective_leverage,
                            "equity": user_state.current_equity,
                            "notional": user_state.total_notional,
                            "since": user_state.leverage_hard_stop_since.isoformat() if user_state.leverage_hard_stop_since else None,
                        },
                    )
                    # Get contextual educational articles for leverage
                    from app.db.crud import get_contextual_articles
                    contextual_articles = []
                    try:
                        articles = get_contextual_articles(db, settings.DEFAULT_USER_ID, trigger_type="leverage", limit=3)
                        contextual_articles = [
                            {
                                "id": a.id,
                                "title": a.title,
                                "slug": a.slug,
                                "summary": a.summary,
                                "category": a.category,
                            }
                            for a in articles
                        ]
                    except Exception as e:
                        logger.warning(f"Failed to fetch contextual articles: {e}", exc_info=True)
                    
                    return {
                        "status": "leverage_hard_stop",
                        "reason": f"Apalancamiento excesivo detectado ({user_state.effective_leverage:.2f}×). Reduzca la exposición antes de continuar.",
                        "effective_leverage": float(user_state.effective_leverage),
                        "current_equity": float(user_state.current_equity),
                        "total_notional": float(user_state.total_notional),
                        "hard_stop_since": user_state.leverage_hard_stop_since.isoformat() if user_state.leverage_hard_stop_since else None,
                        "contextual_articles": contextual_articles,
                    }
        except Exception as e:
            logger.warning(f"Error checking user risk state: {e}", exc_info=True)
        finally:
            if not self.session:
                db.close()

        open_rec = self._get_open_recommendation()
        if open_rec:
            logger.info("Reusing open recommendation with status=%s for consensus", open_rec.status)
            return self._from_orm(open_rec)

        try:
            latest_daily = self.curation.get_latest_curated("1d")
        except FileNotFoundError:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        try:
            latest_hourly = self.curation.get_latest_curated("1h")
        except FileNotFoundError:
            logger.warning("No 1h data available, using 1d as fallback")
            latest_hourly = latest_daily

        if latest_daily is None or latest_daily.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        if latest_hourly is None or latest_hourly.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            latest_hourly = latest_daily

        try:
            signal = generate_signal(latest_hourly, latest_daily)
            signal = await self.strategy_service.apply_sl_tp_policy(signal, latest_daily)
            if "close" in latest_hourly.columns:
                signal["current_price"] = float(latest_hourly["close"].iloc[-1])
            if "open_time" in latest_hourly.columns:
                ts = latest_hourly["open_time"].iloc[-1]
                signal["market_timestamp"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            signal["spot_source"] = "1h"
            self._apply_confidence_calibration(signal)
            self._finalize_confidence_fields(signal, signal.get("calibration_metadata"))
        except ValueError as exc:
            logger.warning(f"Recommendation invalidated by risk controls: {exc}")
            return {"status": "invalid", "reason": str(exc)}
        except Exception:
            logger.exception("Unexpected error during signal generation")
            return None
        analysis = build_narrative(signal)
        signal["analysis"] = analysis
        if self._champion_cache:
            signal["champion_config"] = self._champion_cache

        efficiency_ok, efficiency_eval = self._apply_trade_efficiency(signal)
        if not efficiency_ok:
            return {
                "status": "invalid",
                "reason": efficiency_eval.summary,
                "trade_efficiency": efficiency_eval.to_dict(),
            }

        rec = None
        signal_log_id: int | None = None

        # Save recommendation if session is provided
        if self.session:
            rec = create_recommendation(self.session, signal)
        else:
            # Fallback to creating a new session
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, signal)
                finally:
                    db.close()

        logger.info(f"Generated and saved recommendation: {signal['signal']}")
        
        # Cache result first to get sizing with risk_of_ruin (this calculates sizing)
        result = self._cache_result(rec) if rec else signal
        
        # Add sizing data to signal payload for logging (before logging)
        if rec and isinstance(result, dict):
            suggested_sizing = result.get("suggested_sizing")
            if suggested_sizing:
                signal["suggested_sizing"] = suggested_sizing
            
            # If recommendation was created and sizing is valid, register position in exposure ledger
            if suggested_sizing and not suggested_sizing.get("status"):
                # Valid sizing, register position
                try:
                    from app.core.config import settings
                    symbol = signal.get("symbol", "BTCUSDT")
                    direction = signal.get("signal", "BUY")
                    notional = suggested_sizing.get("notional", 0.0)
                    entry = signal.get("entry_range", {}).get("optimal") or signal.get("current_price", 0.0)
                    
                    if notional > 0 and entry > 0:
                        beta_value = self.exposure_ledger_service.calculate_beta(symbol)
                        self.exposure_ledger_service.add_position(
                            user_id=settings.DEFAULT_USER_ID,
                            recommendation_id=rec.id,
                            symbol=symbol,
                            direction=direction,
                            notional=notional,
                            entry_price=entry,
                            beta_value=beta_value,
                        )
                except Exception as e:
                    logger.warning(f"Failed to register position in exposure ledger: {e}", exc_info=True)
        
        # Log signal emission with risk_of_ruin in metadata
        signal_log_id: int | None = None
        if rec:
            signal_log_id = self._log_signal_emission(rec, signal)
        
        if not rec:
            self._finalize_confidence_fields(result, result.get("calibration_metadata"))
        if rec and signal.get("calibration_metadata"):
            result["calibration_metadata"] = signal["calibration_metadata"]
        if signal_log_id and isinstance(result, dict):
            result["signal_log_id"] = signal_log_id
        
        # Add shutdown status if applicable
        if self.shutdown_manager:
            shutdown_status = await self._check_shutdown_status()
            result["shutdown_status"] = shutdown_status
            if shutdown_status["size_reduction"]:
                result["size_reduction_factor"] = shutdown_status["size_reduction_factor"]
        
        return result

    async def get_today_recommendation(self, user_id: str | None = None) -> Optional[dict[str, Any]]:
        """Get today's recommendation from DB or generate on-demand."""
        today = datetime.utcnow().date()

        self._ensure_champion_context(run_alerts=False)

        open_rec = self._get_open_recommendation()
        if open_rec:
            logger.info(
                "Serving open recommendation from %s with status=%s",
                open_rec.date,
                open_rec.status,
            )
            return self._cache_result(open_rec, user_id=user_id)

        # Check cache first
        if self._cache and self._cache_timestamp and self._cache_timestamp.date() == today:
            logger.debug("Returning cached recommendation")
            return self._cache

        # Try DB first
        with SessionLocal() as db:
            try:
                rec = get_latest_recommendation(db)
                if rec:
                    rec_date = rec.created_at.date()
                    if rec_date == today:
                        logger.info(f"Found today's recommendation in DB (created at {rec.created_at})")
                        return self._cache_result(rec, user_id=user_id)
                    else:
                        logger.debug(f"Latest recommendation is from {rec_date}, not today")
            finally:
                db.close()

        # Generate on-demand if not present
        logger.info("Generating recommendation on-demand")
        dc = DataCuration()
        try:
            df_1d = dc.get_latest_curated("1d")
        except FileNotFoundError:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        try:
            df_1h = dc.get_latest_curated("1h")
        except FileNotFoundError:
            logger.warning("No 1h data available, using 1d as fallback")
            df_1h = df_1d

        if df_1d is None or df_1d.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        if df_1h is None or df_1h.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            df_1h = df_1d

        try:
            recommendation = generate_signal(df_1h, df_1d)
            recommendation = await self.strategy_service.apply_sl_tp_policy(recommendation, df_1d)
            # Add analysis if not present (will be generated in create_recommendation)
            if "analysis" not in recommendation or not recommendation["analysis"]:
                from app.quant.narrative import build_narrative
                recommendation["analysis"] = build_narrative(recommendation)
            if "close" in df_1h.columns:
                recommendation["current_price"] = float(df_1h["close"].iloc[-1])
            if "open_time" in df_1h.columns:
                ts = df_1h["open_time"].iloc[-1]
                recommendation["market_timestamp"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            recommendation["spot_source"] = "1h"

            efficiency_ok, efficiency_eval = self._apply_trade_efficiency(recommendation)
            if not efficiency_ok:
                return {
                    "status": "invalid",
                    "reason": efficiency_eval.summary,
                    "trade_efficiency": efficiency_eval.to_dict(),
                }

            result = None
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, recommendation)
                    logger.info(f"Generated and saved recommendation: {recommendation['signal']}")
                    result = self._cache_result(rec, user_id=user_id)
                finally:
                    db.close()

            if result:
                return result
        except ValueError as exc:
            logger.warning(f"Recommendation invalidated by risk controls: {exc}")
            return {"status": "invalid", "reason": str(exc)}
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}", exc_info=True)
            return None

    async def get_recommendation_history(
        self,
        *,
        limit: int = 25,
        cursor: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        signal: str | None = None,
        result: str | None = None,
        status: str | None = None,
        tracking_error_min: float | None = None,
        tracking_error_max: float | None = None,
    ) -> dict[str, Any]:
        """Get recommendation history with pagination and filters."""
        self._ensure_champion_context(run_alerts=False)
        limit = max(1, min(limit, 200))
        signal_value = signal.upper() if signal else None
        result_value = result.upper() if result else None
        cursor_tuple = self._decode_cursor(cursor)
        start_dt = self._parse_date(start_date, start_of_day=True)
        end_dt = self._parse_date(end_date, start_of_day=False)

        records, has_more, next_cursor = self._query_history_records(
            limit=limit,
            cursor_filter=cursor_tuple,
            start_dt=start_dt,
            end_dt=end_dt,
            signal=signal_value,
            status=status,
            result=result_value,
            tracking_error_min=tracking_error_min,
            tracking_error_max=tracking_error_max,
            include_pagination=True,
        )

        items = [self._build_history_item(self._from_orm(rec)) for rec in records]
        insights = {
            "sparkline_series": self._build_history_sparklines(items),
            "stats": self._build_history_stats(items),
        }
        response_filters = {
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date,
            "signal": signal_value,
            "result": result_value,
            "status": status,
            "tracking_error_min": tracking_error_min,
            "tracking_error_max": tracking_error_max,
        }

        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "filters": {k: v for k, v in response_filters.items() if v is not None},
            "insights": insights,
            "download_url": self._build_history_export_url(response_filters, cursor),
        }

    async def export_recommendation_history(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        signal: str | None = None,
        result: str | None = None,
        status: str | None = None,
        tracking_error_min: float | None = None,
        tracking_error_max: float | None = None,
        export_format: str = "csv",
    ) -> dict[str, Any]:
        """Generate downloadable history snapshot."""
        self._ensure_champion_context(run_alerts=False)
        limit = max(1, min(limit, 1000))
        signal_value = signal.upper() if signal else None
        result_value = result.upper() if result else None
        cursor_tuple = self._decode_cursor(cursor)
        start_dt = self._parse_date(start_date, start_of_day=True)
        end_dt = self._parse_date(end_date, start_of_day=False)

        records, _, _ = self._query_history_records(
            limit=limit,
            cursor_filter=cursor_tuple,
            start_dt=start_dt,
            end_dt=end_dt,
            signal=signal_value,
            status=status,
            result=result_value,
            tracking_error_min=tracking_error_min,
            tracking_error_max=tracking_error_max,
            include_pagination=False,
        )
        items = [self._build_history_item(self._from_orm(rec)) for rec in records]

        if export_format == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(
                [
                    "timestamp",
                    "signal",
                    "status",
                    "execution_status",
                    "entry_price",
                    "exit_price",
                    "return_pct",
                    "tracking_error_pct",
                    "tracking_error_bps",
                    "code_commit",
                    "dataset_version",
                ]
            )
            for item in items:
                writer.writerow(
                    [
                        item.get("timestamp"),
                        item.get("signal"),
                        item.get("status"),
                        item.get("execution_status"),
                        item.get("entry_price"),
                        item.get("exit_price"),
                        item.get("return_pct"),
                        item.get("tracking_error_pct"),
                        item.get("tracking_error_bps"),
                        item.get("code_commit"),
                        item.get("dataset_version"),
                    ]
                )
            buffer.seek(0)
            content = buffer.getvalue().encode("utf-8")
            filename = f"recommendation_history_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            return {
                "content": content,
                "media_type": "text/csv",
                "headers": {
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Records": str(len(items)),
                },
            }

        raise ValueError(f"Unsupported export format: {export_format}")

    async def get_signal_performance(
        self,
        *,
        lookahead_days: int = 5,
        limit: int = 90,
    ) -> dict[str, Any]:
        """
        Cross recommendations with subsequent prices to measure realised performance.
        """
        self._ensure_champion_context(run_alerts=False)
        lookahead_days = max(1, min(lookahead_days, 30))
        limit = max(1, min(limit, 365))

        with SessionLocal() as db:
            try:
                recs = db_history(db, limit=limit)
            finally:
                db.close()

        if not recs:
            payload = {
                "status": "no_data",
                "timeline": [],
                "equity_curve": [],
                "equity_theoretical": [],
                "equity_realistic": [],
                "drawdown_curve": [],
                "win_rate": 0.0,
                "average_tracking_error": 0.0,
                "trades_evaluated": 0,
                "tracking_error_metrics": {},
            }
            if self._champion_cache:
                payload["champion_config"] = self._champion_cache
            return payload

        df_prices = self.curation.get_historical_curated("1d", days=365 * 5)
        if df_prices is None or df_prices.empty:
            payload = {
                "status": "no_prices",
                "timeline": [],
                "equity_curve": [],
                "equity_theoretical": [],
                "equity_realistic": [],
                "drawdown_curve": [],
                "win_rate": 0.0,
                "average_tracking_error": 0.0,
                "trades_evaluated": 0,
                "tracking_error_metrics": {},
            }
            if self._champion_cache:
                payload["champion_config"] = self._champion_cache
            return payload

        df_prices = df_prices.copy()
        df_prices["date"] = pd.to_datetime(df_prices["open_time"]).dt.date
        df_prices.set_index("date", inplace=True)

        capital = 1.0
        equity_curve = [round(capital, 4)]  # Theoretical (no frictions)
        equity_theoretical = [round(capital, 4)]
        equity_realistic = [round(capital, 4)]
        drawdown_curve = [0.0]
        peak = capital
        peak_theoretical = capital
        peak_realistic = capital

        timeline: list[dict[str, Any]] = []
        tracking_errors: list[float] = []
        wins = 0
        trades_count = 0

        sorted_recs = sorted(recs, key=lambda r: r.created_at)

        for rec in sorted_recs:
            rec_date = datetime.strptime(rec.date, "%Y-%m-%d").date()
            if rec_date not in df_prices.index:
                continue

            future_slice = df_prices.loc[rec_date:]
            if future_slice.empty or len(future_slice) < 2:
                continue

            window = future_slice.iloc[1 : lookahead_days + 1]
            if window.empty:
                continue

            exit_price = float(window.iloc[-1]["close"])
            exit_reason = "EXIT"
            hit_date = window.index[-1]
            entry_price = float(rec.entry_optimal)
            
            # Estimate volatility for slippage calculation
            price_row = window.iloc[-1]
            vol_estimate = 0.02  # Default 2% volatility
            if "close" in price_row and price_row["close"] > 0:
                # Estimate from price range
                price_range = abs(float(price_row.get("high", 0)) - float(price_row.get("low", 0)))
                vol_estimate = min(price_range / price_row["close"], 0.05)  # Cap at 5%

            if rec.signal == "BUY":
                for idx, row in window.iterrows():
                    low = float(row["low"])
                    high = float(row["high"])
                    if low <= rec.stop_loss:
                        exit_price = float(rec.stop_loss)
                        exit_reason = "SL"
                        hit_date = idx
                        break
                    if high >= rec.take_profit:
                        exit_price = float(rec.take_profit)
                        exit_reason = "TP"
                        hit_date = idx
                        break
            elif rec.signal == "SELL":
                for idx, row in window.iterrows():
                    high = float(row["high"])
                    low = float(row["low"])
                    if high >= rec.stop_loss:
                        exit_price = float(rec.stop_loss)
                        exit_reason = "SL"
                        hit_date = idx
                        break
                    if low <= rec.take_profit:
                        exit_price = float(rec.take_profit)
                        exit_reason = "TP"
                        hit_date = idx
                        break

            # Theoretical execution (no frictions)
            if rec.signal == "BUY":
                theoretical_return_pct = ((exit_price - entry_price) / entry_price) * 100
            elif rec.signal == "SELL":
                theoretical_return_pct = ((entry_price - exit_price) / entry_price) * 100
            else:
                theoretical_return_pct = 0.0
            
            # Realistic execution (with slippage and execution friction)
            # Entry slippage: 0.1% for market orders, scaled by volatility
            entry_slippage_pct = 0.001 * (1 + vol_estimate * 10)  # 0.1% base + volatility adjustment
            if rec.signal == "BUY":
                realistic_entry = entry_price * (1 + entry_slippage_pct)
            else:  # SELL
                realistic_entry = entry_price * (1 - entry_slippage_pct)
            
            # Exit slippage: depends on whether hitting TP/SL or exit
            if exit_reason == "TP" or exit_reason == "SL":
                # Limit order slippage: 0.05% (better fill for limit orders)
                exit_slippage_pct = 0.0005 * (1 + vol_estimate * 5)
            else:
                # Market exit: 0.1% slippage
                exit_slippage_pct = 0.001 * (1 + vol_estimate * 10)
            
            if rec.signal == "BUY":
                realistic_exit = exit_price * (1 - exit_slippage_pct)
                realistic_return_pct = ((realistic_exit - realistic_entry) / realistic_entry) * 100
            elif rec.signal == "SELL":
                realistic_exit = exit_price * (1 + exit_slippage_pct)
                realistic_return_pct = ((realistic_entry - realistic_exit) / realistic_entry) * 100
            else:
                realistic_return_pct = 0.0
            
            # Use theoretical return for legacy equity_curve (maintained for compatibility)
            return_pct = theoretical_return_pct

            if rec.signal in ("BUY", "SELL"):
                trades_count += 1
                if theoretical_return_pct > 0:
                    wins += 1
            
            # Update theoretical equity
            capital_theoretical = capital_theoretical * (1 + (theoretical_return_pct / 100))
            peak_theoretical = max(peak_theoretical, capital_theoretical)
            
            # Update realistic equity
            capital_realistic = capital_realistic * (1 + (realistic_return_pct / 100))
            peak_realistic = max(peak_realistic, capital_realistic)
            
            # Legacy equity_curve (theoretical for backward compatibility)
            capital = capital_theoretical
            peak = peak_theoretical
            drawdown_pct = ((capital / peak) - 1) * 100 if peak > 0 else 0.0

            equity_curve.append(round(capital, 4))
            equity_theoretical.append(round(capital_theoretical, 4))
            equity_realistic.append(round(capital_realistic, 4))
            drawdown_curve.append(round(drawdown_pct, 2))
            
            # Calculate per-trade deviation
            trade_deviation_pct = abs((realistic_return_pct - theoretical_return_pct) / theoretical_return_pct * 100) if theoretical_return_pct != 0 else 0.0

            target_level = None
            if exit_reason == "TP":
                target_level = float(rec.take_profit)
            elif exit_reason == "SL":
                target_level = float(rec.stop_loss)
            tracking_error = (
                abs(exit_price - target_level) / target_level * 100
                if target_level and target_level != 0
                else 0.0
            )
            if target_level:
                tracking_errors.append(tracking_error)

            timeline.append(
                {
                    "date": rec.date,
                    "signal": rec.signal,
                    "entry_price": round(entry_price, 2),
                    "entry_price_realistic": round(realistic_entry, 2),
                    "stop_loss": round(float(rec.stop_loss), 2),
                    "take_profit": round(float(rec.take_profit), 2),
                    "exit_price": round(exit_price, 2),
                    "exit_price_realistic": round(realistic_exit, 2),
                    "level_hit": exit_reason,
                    "holding_days": len(window),
                    "return_pct": round(return_pct, 2),
                    "return_pct_realistic": round(realistic_return_pct, 2),
                    "tracking_error": round(tracking_error, 2),
                    "deviation_pct": round(trade_deviation_pct, 2),
                    "entry_slippage_pct": round(entry_slippage_pct * 100, 4),
                    "exit_slippage_pct": round(exit_slippage_pct * 100, 4),
                    "hit_date": hit_date.isoformat() if hasattr(hit_date, "isoformat") else str(hit_date),
                    "signal_breakdown": rec.signal_breakdown or {},
                }
            )

        average_tracking_error = float(sum(tracking_errors) / len(tracking_errors)) if tracking_errors else 0.0
        win_rate = (wins / trades_count * 100) if trades_count else 0.0
        
        # Calculate tracking error metrics using same structure as backtests (for comparability)
        tracking_error_metrics = {}
        tracking_error_summary = None
        if len(equity_theoretical) > 1 and len(equity_realistic) > 1:
            # Use TrackingErrorCalculator to maintain consistency with backtests
            # Daily bars for signal performance (signals are evaluated daily)
            bars_per_year = 365
            tracking_error_calc = TrackingErrorCalculator.from_curves(
                theoretical=equity_theoretical,
                realistic=equity_realistic,
                bars_per_year=bars_per_year,
            )
            tracking_error_summary = tracking_error_calc.to_dict()
            
            # Also calculate legacy metrics for backward compatibility
            tracking_error_results = calculate_tracking_error(equity_theoretical, equity_realistic)
            tracking_error_metrics = {
                "mean_deviation": tracking_error_results["mean_deviation"],
                "max_divergence": tracking_error_results["max_divergence"],
                "tracking_sharpe": tracking_error_results["tracking_sharpe"],
                "rmse": tracking_error_results["rmse"],
                "correlation": tracking_error_results["correlation"],
                "max_drawdown_divergence": tracking_error_results["max_drawdown_divergence"],
                "cumulative_tracking_error": tracking_error_results["cumulative_tracking_error"],
                "p95_divergence": tracking_error_results["p95_divergence"],
                "p99_divergence": tracking_error_results["p99_divergence"],
                "theoretical_max_drawdown": tracking_error_results.get("theoretical_max_drawdown", 0.0),
                "realistic_max_drawdown": tracking_error_results.get("realistic_max_drawdown", 0.0),
                # Add new metrics from TrackingErrorCalculator for comparability
                "annualized_tracking_error": tracking_error_summary.get("annualized_tracking_error", 0.0),
                "bars_with_divergence_above_threshold_pct": tracking_error_summary.get("bars_with_divergence_above_threshold_pct", 0.0),
                "mean_divergence_bps": tracking_error_summary.get("mean_divergence_bps", 0.0),
                "max_divergence_bps": tracking_error_summary.get("max_divergence_bps", 0.0),
            }

        payload = {
            "status": "ok",
            "timeline": timeline,
            "equity_curve": equity_curve,  # Legacy: equals equity_theoretical
            "equity_theoretical": equity_theoretical,
            "equity_realistic": equity_realistic,
            "drawdown_curve": drawdown_curve,
            "win_rate": round(win_rate, 2),
            "average_tracking_error": round(average_tracking_error, 2),
            "trades_evaluated": trades_count,
            "tracking_error_metrics": tracking_error_metrics,
            "tracking_error_summary": tracking_error_summary,  # Same structure as backtests for comparability
        }
        if self._champion_cache:
            payload["champion_config"] = self._champion_cache
        return payload

    async def auto_close_open_trade(self) -> None:
        """Check if the open trade hit TP/SL and close it automatically."""
        updated_rec = None
        exit_price = exit_reason = None
        exit_at = None
        exit_pct = None

        with SessionLocal() as db:
            try:
                rec = get_open_recommendation(db)
                if rec is None:
                    return
                evaluation = self._evaluate_exit_conditions(rec)
                if evaluation is None:
                    return
                exit_price, exit_reason, exit_at, exit_pct = evaluation
                # Get default user_id (for single-user system, use a default UUID)
                # In multi-user system, this would come from session/auth
                default_user_id = settings.DEFAULT_USER_ID if hasattr(settings, "DEFAULT_USER_ID") else None
                
                updated_rec = close_recommendation(
                    db,
                    rec,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    exit_at=exit_at,
                    exit_pct=exit_pct,
                    user_id=default_user_id,
                )
                
                # Close position in exposure ledger
                try:
                    self.exposure_ledger_service.close_position(
                        user_id=default_user_id,
                        recommendation_id=rec.id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to close position in exposure ledger: {e}", exc_info=True)
                
                db.expunge(updated_rec)
            finally:
                db.close()

        self._reset_cache()

        if updated_rec:
            logger.info(
                "Closed recommendation %s (%s) at %.2f due to %s (%.2f%%)",
                updated_rec.id,
                updated_rec.signal,
                exit_price,
                exit_reason,
                exit_pct if exit_pct is not None else 0.0,
            )

    def _evaluate_exit_conditions(self, rec) -> tuple[float, str, datetime, float] | None:
        """Determine if the open trade has hit TP or SL based on curated data."""
        if rec.signal not in {"BUY", "SELL"}:
            return None

        try:
            df = self.curation.get_latest_curated("1h")
        except FileNotFoundError:
            logger.debug("Cannot evaluate exit: 1h curated data missing")
            return None

        if df is None or df.empty or "open_time" not in df.columns:
            return None

        opened_at = rec.opened_at or rec.created_at
        if opened_at is None:
            return None

        start_ts = pd.Timestamp(opened_at)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize("UTC")
        else:
            start_ts = start_ts.tz_convert("UTC")

        df = df[df["open_time"] >= start_ts]
        if df.empty:
            return None

        for _, row in df.iterrows():
            timestamp = row["open_time"]
            if not isinstance(timestamp, pd.Timestamp):
                timestamp = pd.Timestamp(timestamp)
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize("UTC")
            exit_at = timestamp.to_pydatetime()

            low = float(row["low"])
            high = float(row["high"])

            if rec.signal == "BUY":
                if low <= rec.stop_loss:
                    exit_price = float(rec.stop_loss)
                    pnl_pct = ((exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
                    return exit_price, "stop_loss", exit_at, pnl_pct
                if high >= rec.take_profit:
                    exit_price = float(rec.take_profit)
                    pnl_pct = ((exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
                    return exit_price, "take_profit", exit_at, pnl_pct
            elif rec.signal == "SELL":
                if high >= rec.stop_loss:
                    exit_price = float(rec.stop_loss)
                    pnl_pct = ((rec.entry_optimal - exit_price) / rec.entry_optimal) * 100
                    return exit_price, "stop_loss", exit_at, pnl_pct
                if low <= rec.take_profit:
                    exit_price = float(rec.take_profit)
                    pnl_pct = ((rec.entry_optimal - exit_price) / rec.entry_optimal) * 100
                    return exit_price, "take_profit", exit_at, pnl_pct

        return None

    def _from_orm(self, r) -> dict[str, Any]:
        """Convert ORM model to API response dict."""
        payload = {
            "id": r.id,
            "signal": r.signal,
            "entry_range": {"min": r.entry_min, "max": r.entry_max, "optimal": r.entry_optimal},
            "stop_loss_take_profit": {
                "stop_loss": r.stop_loss,
                "take_profit": r.take_profit,
                "stop_loss_pct": r.stop_loss_pct,
                "take_profit_pct": r.take_profit_pct,
            },
            "confidence": r.confidence,
            "confidence_calibrated": r.confidence_calibrated,
            "current_price": r.current_price,
            "market_timestamp": r.market_timestamp,
            "spot_source": r.spot_source,
            "analysis": r.analysis or "",
            "indicators": r.indicators or {},
            "risk_metrics": r.risk_metrics or {},
            "factors": r.factors or {},
            "signal_breakdown": r.signal_breakdown or {},
            "calibration_metadata": None,
            "timestamp": r.created_at.isoformat(),
            "status": r.status,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "exit_reason": r.exit_reason,
            "exit_price": r.exit_price,
            "exit_price_pct": r.exit_price_pct,
            "recommended_risk_fraction": None,  # Will be set by _cache_result if sizing is available
            "code_commit": r.code_commit,
            "dataset_version": r.dataset_version,
            "params_digest": r.params_digest,
            "snapshot_json": r.snapshot_json,
            "disclaimer": "This is not financial advice. Trading cryptocurrencies involves significant risk.",
        }
        calibration_meta = payload["signal_breakdown"].get("calibration", {}) if payload["signal_breakdown"] else {}
        payload["calibration_metadata"] = calibration_meta or None
        payload["confidence_raw"] = r.confidence
        payload["confidence_band"] = self._build_confidence_band(r.confidence_calibrated, calibration_meta)
        self._finalize_confidence_fields(payload, calibration_meta)
        if self._champion_cache:
            payload["champion_config"] = self._champion_cache
        return payload

    def _ensure_champion_context(self, run_alerts: bool = True) -> Optional[Any]:
        """Load active champion, cache payload, and optionally run alerts."""
        champion = self._load_active_champion()
        if champion is None:
            logger.error("No active champion configuration available")
            self._champion_cache = None
            return None
        self._champion_cache = self._champion_payload(champion)
        if run_alerts:
            self._check_risk_alerts(champion)
        return champion

    def _load_tracking_error_threshold(self) -> float:
        """Load divergence threshold (in percentage points) from config."""
        default_pct = 2.0
        config_paths = [
            Path("config/performance.yaml"),
            Path("backend/config/performance.yaml"),
            Path(__file__).resolve().parents[2] / "config" / "performance.yaml",
        ]
        for path in config_paths:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                divergence = config.get("tracking_error", {}).get("divergence_threshold_pct")
                if isinstance(divergence, (int, float)):
                    return float(divergence) * 100.0
            except Exception:
                continue
        return default_pct

    def _parse_date(self, value: str | None, *, start_of_day: bool) -> datetime | None:
        if not value:
            return None
        try:
            if len(value) == 10:
                date_obj = datetime.strptime(value, "%Y-%m-%d").date()
                target_time = time.min if start_of_day else time.max
                return datetime.combine(date_obj, target_time)
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _encode_cursor(self, rec) -> str:
        raw = f"{rec.created_at.isoformat()}|{rec.id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    def _decode_cursor(self, cursor: str | None) -> tuple[datetime, int] | None:
        if not cursor:
            return None
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
            ts_str, id_str = decoded.split("|")
            return datetime.fromisoformat(ts_str), int(id_str)
        except Exception:
            return None

    def _tracking_error_expression(self):
        target_price = case(
            (RecommendationORM.exit_reason.in_(("TP", "TAKE_PROFIT", "take_profit")), RecommendationORM.take_profit),
            (RecommendationORM.exit_reason.in_(("SL", "STOP_LOSS", "stop_loss")), RecommendationORM.stop_loss),
            else_=None,
        )
        return func.abs(
            (RecommendationORM.exit_price - target_price) / func.nullif(target_price, 0.0)
        ) * 100.0

    def _calculate_return_pct(self, signal: str, entry: float, target: float | None) -> float | None:
        if not entry or not target or entry == 0:
            return None
        if signal == "BUY":
            return ((target - entry) / entry) * 100.0
        if signal == "SELL":
            return ((entry - target) / entry) * 100.0
        return None

    def _build_history_item(self, data: dict[str, Any]) -> dict[str, Any]:
        item = dict(data)
        entry = data.get("entry_range", {}).get("optimal")
        stop_loss = data.get("stop_loss_take_profit", {}).get("stop_loss")
        take_profit = data.get("stop_loss_take_profit", {}).get("take_profit")
        exit_price = data.get("exit_price")
        exit_reason = (data.get("exit_reason") or "").upper() if data.get("exit_reason") else None
        signal = data.get("signal")

        theoretical_return_pct = None
        target_price = None
        if exit_reason in ("TP", "TAKE_PROFIT"):
            target_price = take_profit
            theoretical_return_pct = self._calculate_return_pct(signal, entry, take_profit)
        elif exit_reason in ("SL", "STOP_LOSS"):
            target_price = stop_loss
            theoretical_return_pct = self._calculate_return_pct(signal, entry, stop_loss)

        tracking_error_pct = None
        if exit_price is not None and target_price:
            tracking_error_pct = abs((exit_price - target_price) / target_price) * 100.0 if target_price else None
        tracking_error_bps = tracking_error_pct * 100.0 if tracking_error_pct is not None else None
        divergence_flag = bool(
            tracking_error_pct is not None and tracking_error_pct >= self.tracking_error_threshold_pct
        )

        realistic_return_pct = data.get("exit_price_pct")
        execution_status = "open"
        if data.get("status") == "closed":
            execution_status = exit_reason or "closed"
            if not exit_reason and realistic_return_pct is not None:
                execution_status = "win" if realistic_return_pct > 0 else "loss"

        item.update(
            {
                "date": data.get("timestamp")[:10] if data.get("timestamp") else None,
                "execution_status": execution_status,
                "exit_reason": exit_reason,
                "entry_price": entry,
                "exit_price": exit_price,
                "return_pct": realistic_return_pct,
                "pnl_pct": realistic_return_pct,
                "theoretical_return_pct": theoretical_return_pct,
                "realistic_return_pct": realistic_return_pct,
                "tracking_error_pct": tracking_error_pct,
                "tracking_error_bps": tracking_error_bps,
                "divergence_flag": divergence_flag,
                "snapshot_url": f"/api/v1/recommendation/{data.get('id')}/snapshot" if data.get("snapshot_json") else None,
            }
        )
        return item

    def _build_history_stats(self, items: list[dict[str, Any]]) -> dict[str, float]:
        if not items:
            return {"count": 0, "avg_tracking_error_pct": 0.0, "divergence_rate_pct": 0.0}
        tracking_errors = [i["tracking_error_pct"] for i in items if i.get("tracking_error_pct") is not None]
        divergence_count = sum(1 for i in items if i.get("divergence_flag"))
        avg_tracking_error = sum(tracking_errors) / len(tracking_errors) if tracking_errors else 0.0
        divergence_rate = (divergence_count / len(items)) * 100.0 if items else 0.0
        return {
            "count": float(len(items)),
            "avg_tracking_error_pct": round(avg_tracking_error, 4),
            "divergence_rate_pct": round(divergence_rate, 2),
        }

    def _build_history_sparklines(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, float]]]:
        sparkline: dict[str, list[dict[str, float]]] = {}
        for signal in ("BUY", "SELL", "HOLD"):
            eq_theoretical = 1.0
            eq_realistic = 1.0
            series: list[dict[str, float]] = []
            signal_items = [item for item in items if item.get("signal") == signal]
            for item in reversed(signal_items):
                ret_theoretical = item.get("theoretical_return_pct") or 0.0
                ret_realistic = (
                    item.get("realistic_return_pct") if item.get("realistic_return_pct") is not None else ret_theoretical
                )
                eq_theoretical *= 1 + (ret_theoretical / 100.0)
                eq_realistic *= 1 + (ret_realistic / 100.0)
                series.append(
                    {
                        "timestamp": item.get("timestamp"),
                        "theoretical": round(eq_theoretical, 4),
                        "realistic": round(eq_realistic, 4),
                    }
                )
            sparkline[signal] = series[-20:]
        return sparkline

    def _build_history_export_url(self, filters: dict[str, Any], cursor: str | None) -> str:
        params = {k: v for k, v in filters.items() if v is not None}
        if cursor:
            params["cursor"] = cursor
        params["format"] = "csv"
        return f"/api/v1/recommendation/history?{urlencode(params)}"

    def _query_history_records(
        self,
        *,
        limit: int,
        cursor_filter: tuple[datetime, int] | None,
        start_dt: datetime | None,
        end_dt: datetime | None,
        signal: str | None,
        status: str | None,
        result: str | None,
        tracking_error_min: float | None,
        tracking_error_max: float | None,
        include_pagination: bool,
    ) -> tuple[list[RecommendationORM], bool, str | None]:
        stmt = select(RecommendationORM).order_by(desc(RecommendationORM.created_at), desc(RecommendationORM.id))
        if cursor_filter:
            cursor_ts, cursor_id = cursor_filter
            stmt = stmt.where(
                or_(
                    RecommendationORM.created_at < cursor_ts,
                    and_(
                        RecommendationORM.created_at == cursor_ts,
                        RecommendationORM.id < cursor_id,
                    ),
                )
            )
        if start_dt:
            stmt = stmt.where(RecommendationORM.created_at >= start_dt)
        if end_dt:
            stmt = stmt.where(RecommendationORM.created_at <= end_dt)
        if signal:
            stmt = stmt.where(RecommendationORM.signal == signal)
        if status:
            stmt = stmt.where(RecommendationORM.status == status)
        if result:
            stmt = stmt.where(RecommendationORM.exit_reason == result)

        te_expr = self._tracking_error_expression()
        if tracking_error_min is not None:
            stmt = stmt.where(RecommendationORM.exit_price.isnot(None)).where(te_expr >= tracking_error_min)
        if tracking_error_max is not None:
            stmt = stmt.where(RecommendationORM.exit_price.isnot(None)).where(te_expr <= tracking_error_max)

        query_limit = limit + 1 if include_pagination else limit
        with SessionLocal() as db:
            try:
                rows = list(db.execute(stmt.limit(query_limit)).scalars().all())
            finally:
                db.close()

        has_more = False
        next_cursor = None
        records = rows
        if include_pagination and len(rows) > limit:
            has_more = True
            records = rows[:limit]
            next_cursor = self._encode_cursor(records[-1])
        return records, has_more, next_cursor

    def _load_active_champion(self):
        """Fetch active champion record using available session."""
        champion = None
        if self.session is not None:
            try:
                champion = get_current_champion(self.session)
            except Exception:
                champion = None
        if champion:
            return champion
        with SessionLocal() as db:
            try:
                champion = get_current_champion(db)
                if champion:
                    db.expunge(champion)
                return champion
            finally:
                db.close()

    def _champion_payload(self, champion) -> dict[str, Any]:
        """Return serialisable champion payload for API consumers."""
        return {
            "params_id": champion.params_id,
            "score": champion.score,
            "objective": champion.objective,
            "target_metric": champion.target_metric,
            "target_value": champion.target_value,
            "drawdown_limit": champion.drawdown_limit,
            "promoted_at": champion.promoted_at.isoformat() if champion.promoted_at else None,
            "engine_args": champion.engine_args or {},
            "execution_overrides": champion.execution_overrides or {},
        }

    def _check_risk_alerts(self, champion) -> None:
        """Trigger alerts when risk thresholds are breached."""
        metrics = champion.metrics or {}
        risk_profile = metrics.get("risk_profile", {}) if isinstance(metrics, dict) else {}

        ruin_prob = risk_profile.get("ruin_prob")
        ruin_threshold = getattr(settings, "RISK_RUIN_ALERT_THRESHOLD", 0.05)
        if isinstance(ruin_prob, (int, float)) and ruin_prob >= ruin_threshold:
            self.alerts.notify(
                "risk_monitor.ruin_prob",
                f"Ruin probability {ruin_prob:.2%} exceeds threshold {ruin_threshold:.2%}",
                payload={
                    "params_id": champion.params_id,
                    "score": champion.score,
                    "threshold": ruin_threshold,
                },
            )

        drawdown_limit = champion.drawdown_limit
        if drawdown_limit is None:
            drawdown_limit = risk_profile.get("p95_worst_dd_pct")
        if not isinstance(drawdown_limit, (int, float)):
            return

        buffer_factor = getattr(settings, "PRODUCTION_DD_ALERT_BUFFER", 0.9)
        if buffer_factor <= 0:
            return

        with SessionLocal() as db:
            try:
                prod_stats = calculate_production_drawdown(db)
            finally:
                db.close()

        observed_dd = prod_stats.get("max_drawdown_pct", 0.0)
        threshold_dd = drawdown_limit * buffer_factor
        if isinstance(observed_dd, (int, float)) and observed_dd >= threshold_dd:
            self.alerts.notify(
                "risk_monitor.production_drawdown",
                f"Production drawdown {observed_dd:.2f}% near limit {drawdown_limit:.2f}%",
                payload={
                    "params_id": champion.params_id,
                    "score": champion.score,
                    "threshold": threshold_dd,
                    "drawdown_limit": drawdown_limit,
                },
            )

