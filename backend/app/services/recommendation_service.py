"""Recommendation service."""
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.db.crud import (
    calculate_production_drawdown,
    close_recommendation,
    create_recommendation,
    get_current_champion,
    get_latest_recommendation,
    get_open_recommendation,
    get_recommendation_history as db_history,
)
from app.backtesting.auto_shutdown import AutoShutdownManager, AutoShutdownPolicy, StrategyMetrics
from app.backtesting.risk_sizing import RiskSizer
from app.backtesting.tracking_error import calculate_tracking_error
from app.core.logging import logger
from app.db.crud import calculate_production_drawdown
from app.quant.signal_engine import generate_signal
from app.services.alert_service import AlertService


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
        self._champion_cache: Optional[dict[str, Any]] = None
        self.shutdown_manager = shutdown_manager or AutoShutdownManager(
            policy=AutoShutdownPolicy()
        )

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

    def _cache_result(self, rec, include_sizing: bool = True) -> dict[str, Any]:
        """Convert RecommendationORM to dict, including ID and metadata."""
        result = self._from_orm(rec)
        self._cache = result
        self._cache_timestamp = rec.created_at
        
        # Add recommended risk fraction (default: 1% = 0.01)
        # This can be customized per strategy or campaign, but defaults to 1%
        default_risk_fraction = 0.01
        result["recommended_risk_fraction"] = default_risk_fraction
        
        # Add suggested sizing if entry/stop are available
        if include_sizing:
            entry_range = result.get("entry_range", {})
            stop_loss_tp = result.get("stop_loss_take_profit", {})
            entry = entry_range.get("optimal")
            stop = stop_loss_tp.get("stop_loss")
            
            if entry and stop:
                # Default sizing calculation (user needs to provide capital)
                # We'll add a note that capital is required
                risk_per_unit = abs(entry - stop)
                if risk_per_unit > 0:
                    # Calculate sizing for default $10,000 capital and 1% risk
                    default_capital = 10000.0
                    default_risk_pct = default_risk_fraction * 100.0
                    risk_sizer = RiskSizer(risk_budget_pct=default_risk_fraction)
                    default_units = risk_sizer.compute_size(
                        equity=default_capital,
                        entry=entry,
                        stop=stop,
                    )
                    default_notional = default_units * entry
                    default_risk = default_units * risk_per_unit
                    
                    result["suggested_sizing"] = {
                        "note": f"Calculated with default $10,000 capital and {default_risk_pct}% risk. Use /api/v1/risk/sizing for custom parameters.",
                        "default_capital": default_capital,
                        "default_risk_pct": default_risk_pct,
                        "units": round(default_units, 8),
                        "notional": round(default_notional, 2),
                        "risk_amount": round(default_risk, 2),
                        "risk_per_unit": round(risk_per_unit, 2),
                        "entry": entry,
                        "stop": stop,
                    }
        
        return result

    def _reset_cache(self) -> None:
        self._cache = None
        self._cache_timestamp = None

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
            if "close" in latest_hourly.columns:
                signal["current_price"] = float(latest_hourly["close"].iloc[-1])
            if "open_time" in latest_hourly.columns:
                ts = latest_hourly["open_time"].iloc[-1]
                signal["market_timestamp"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            signal["spot_source"] = "1h"
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

        rec = None

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
        result = self._cache_result(rec) if rec else signal
        
        # Add shutdown status if applicable
        if self.shutdown_manager:
            shutdown_status = await self._check_shutdown_status()
            result["shutdown_status"] = shutdown_status
            if shutdown_status["size_reduction"]:
                result["size_reduction_factor"] = shutdown_status["size_reduction_factor"]
        
        return result

    async def get_today_recommendation(self) -> Optional[dict[str, Any]]:
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
            return self._cache_result(open_rec)

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
                        return self._cache_result(rec)
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

            result = None
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, recommendation)
                    logger.info(f"Generated and saved recommendation: {recommendation['signal']}")
                    result = self._cache_result(rec)
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

    async def get_recommendation_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recommendation history from DB."""
        self._ensure_champion_context(run_alerts=False)
        with SessionLocal() as db:
            try:
                recs = db_history(db, limit=limit)
                return [self._from_orm(r) for r in recs]
            finally:
                db.close()

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
        
        # Calculate tracking error metrics between theoretical and realistic curves
        tracking_error_metrics = {}
        if len(equity_theoretical) > 1 and len(equity_realistic) > 1:
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
            "current_price": r.current_price,
            "market_timestamp": r.market_timestamp,
            "spot_source": r.spot_source,
            "analysis": r.analysis or "",
            "indicators": r.indicators or {},
            "risk_metrics": r.risk_metrics or {},
            "factors": r.factors or {},
            "signal_breakdown": r.signal_breakdown or {},
            "timestamp": r.created_at.isoformat(),
             "status": r.status,
             "opened_at": r.opened_at.isoformat() if r.opened_at else None,
             "closed_at": r.closed_at.isoformat() if r.closed_at else None,
             "exit_reason": r.exit_reason,
            "exit_price": r.exit_price,
            "exit_price_pct": r.exit_price_pct,
            "recommended_risk_fraction": 0.01,  # Default 1%, can be overridden in _cache_result
            "code_commit": r.code_commit,
            "dataset_version": r.dataset_version,
            "params_digest": r.params_digest,
            "snapshot_json": r.snapshot_json,
            "disclaimer": "This is not financial advice. Trading cryptocurrencies involves significant risk.",
        }
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

