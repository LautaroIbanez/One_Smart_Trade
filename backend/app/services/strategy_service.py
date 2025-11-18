"""Strategy-level risk controls: SL/TP optimizer integration and guardrails."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import logger

try:  # pragma: no cover - optional dependency
    from app.data.orderbook import OrderBookRepository, OrderBookSnapshot
except Exception:  # noqa: BLE001
    logger.warning("OrderBookRepository import failed; liquidity guardrails disabled")
    OrderBookRepository = None  # type: ignore[assignment]
    OrderBookSnapshot = None  # type: ignore[assignment]
from app.quant.regime import RegimeClassifier
from app.risk import StopLossTakeProfitOptimizer
from app.services.alert_service import AlertService


class StrategyService:
    """High-level orchestrator for regime-aware SL/TP configuration and guardrails."""

    def __init__(
        self,
        *,
        optimizer: StopLossTakeProfitOptimizer | None = None,
        regime_classifier: RegimeClassifier | None = None,
        orderbook_repo: OrderBookRepository | None = None,
        default_symbol: str = "BTCUSDT",
        venue: str = "binance",
        rr_floor: float = 1.25,
        liquidity_window_minutes: int = 180,
        liquidity_zone_bps: float = 8.0,
    ) -> None:
        self.optimizer = optimizer or StopLossTakeProfitOptimizer()
        self.regime_classifier = regime_classifier or RegimeClassifier(method="kmeans", n_regimes=3)
        if orderbook_repo is not None:
            self.orderbook_repo = orderbook_repo
        elif OrderBookRepository is not None:
            self.orderbook_repo = OrderBookRepository(venue=venue)
        else:
            self.orderbook_repo = None
        self.alerts = AlertService()
        self.default_symbol = default_symbol
        self.rr_floor = rr_floor
        self.liquidity_window_minutes = liquidity_window_minutes
        self.liquidity_zone_bps = liquidity_zone_bps
        self._last_regime_probs: dict[str, float] | None = None

    async def apply_sl_tp_policy(
        self,
        signal: dict[str, Any],
        market_df: pd.DataFrame,
        *,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """Apply optimized SL/TP parameters and guardrails to a signal payload."""
        if not signal:
            return signal

        resolved_symbol = symbol or signal.get("symbol") or self.default_symbol
        regime = self._detect_regime(market_df)
        config = self.optimizer.load_config(resolved_symbol, regime)

        if not config:
            self.alerts.notify(
                "risk.optimizer_missing",
                f"No SL/TP config for regime={regime}",
                payload={"symbol": resolved_symbol},
            )
            self._apply_conservative_defaults(signal, market_df, regime)
            return signal

        signal.setdefault("factors", {})["optimizer_regime"] = regime
        self._apply_config(signal, market_df, config)

        guardrail_reason = await self._apply_guardrails(signal, config, resolved_symbol)
        if guardrail_reason:
            signal["signal"] = "HOLD"
            risk_metrics = signal.setdefault("risk_metrics", {})
            risk_metrics["guardrail_reason"] = guardrail_reason
            self.alerts.notify(
                "risk.guardrail_triggered",
                f"Signal degraded to HOLD due to {guardrail_reason}",
                payload={"symbol": resolved_symbol, "regime": regime},
            )
        return signal

    def _detect_regime(self, df: pd.DataFrame) -> str:
        if df is None or df.empty:
            return "unknown"
        try:
            features = self.regime_classifier.extract_features(df)
            if features.empty:
                return "unknown"
            self.regime_classifier.fit_rolling(features)
            proba = self.regime_classifier.predict_proba(features)
            if proba.empty:
                return "unknown"
            latest = proba.iloc[-1]
            self._last_regime_probs = latest.to_dict()
            return str(latest.idxmax())
        except Exception as exc:
            logger.warning("Failed to classify regime: %s", exc, extra={"component": "StrategyService"})
            return "unknown"

    def _apply_config(self, signal: dict[str, Any], market_df: pd.DataFrame, config: dict[str, Any]) -> None:
        params = config.get("best_params") or {}
        if not params:
            windows = config.get("windows") or []
            if windows:
                params = windows[-1].get("params", {})
        if not params:
            self._apply_conservative_defaults(signal, market_df, config.get("regime", "fallback"))
            return

        entry_range = signal.get("entry_range") or {}
        entry = float(entry_range.get("optimal") or 0.0)
        if entry <= 0:
            return

        atr = self._latest_atr(market_df)
        if atr <= 0:
            return

        direction = signal.get("signal", "HOLD").upper()
        sl_distance = atr * params.get("atr_multiplier_sl", 1.5)
        tp_distance = atr * params.get("atr_multiplier_tp", 2.0)
        tp_ratio = params.get("tp_ratio", 2.0)
        reward_distance = tp_distance * tp_ratio

        if direction == "BUY":
            stop_loss = entry - sl_distance
            take_profit = entry + reward_distance
        elif direction == "SELL":
            stop_loss = entry + sl_distance
            take_profit = entry - reward_distance
        else:
            return

        sl_tp = {
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "stop_loss_pct": round((stop_loss - entry) / entry * 100, 2),
            "take_profit_pct": round((take_profit - entry) / entry * 100, 2),
        }
        signal["stop_loss_take_profit"] = sl_tp

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr_ratio = reward / risk if risk else 0.0

        risk_metrics = signal.setdefault("risk_metrics", {})
        risk_metrics.update(
            {
                "risk": round(risk, 4),
                "reward": round(reward, 4),
                "risk_reward_ratio": round(rr_ratio, 3),
                "rr_threshold": float(config.get("rr_threshold", self.rr_floor)),
                "optimizer_version": config.get("metadata", {}).get("updated_at"),
                "optimizer_regime": config.get("regime"),
            }
        )

    def _apply_conservative_defaults(self, signal: dict[str, Any], market_df: pd.DataFrame, regime: str) -> None:
        params = {
            "atr_multiplier_sl": 3.0,
            "atr_multiplier_tp": 1.2,
            "tp_ratio": 1.15,
        }
        fallback_config = {
            "best_params": params,
            "regime": regime,
            "rr_threshold": self.rr_floor,
            "metadata": {"updated_at": datetime.now(timezone.utc).isoformat(), "fallback": True},
        }
        self._apply_config(signal, market_df, fallback_config)
        signal.setdefault("risk_metrics", {})["fallback"] = "conservative_defaults"

    async def _apply_guardrails(
        self,
        signal: dict[str, Any],
        config: dict[str, Any],
        symbol: str,
    ) -> str | None:
        risk_metrics = signal.get("risk_metrics") or {}
        rr_ratio = float(risk_metrics.get("risk_reward_ratio") or 0.0)
        rr_threshold = float(config.get("rr_threshold", self.rr_floor))
        if rr_ratio and rr_ratio < rr_threshold:
            return "rr_threshold"

        sl_tp = signal.get("stop_loss_take_profit") or {}
        stop_loss = sl_tp.get("stop_loss")
        if stop_loss is None:
            return None

        try:
            in_liquidity_zone = await self._stop_in_liquidity_zone(symbol, float(stop_loss))
        except Exception as exc:
            logger.warning("Liquidity zone evaluation failed: %s", exc)
            in_liquidity_zone = False

        if in_liquidity_zone:
            return "liquidity_zone"
        return None

    async def _stop_in_liquidity_zone(self, symbol: str, price: float) -> bool:
        if price <= 0:
            return False
        if self.orderbook_repo is None:
            return False

        end = pd.Timestamp.utcnow().tz_localize("UTC")
        start = end - pd.Timedelta(minutes=self.liquidity_window_minutes)
        snapshots = await self.orderbook_repo.load(symbol, start, end)
        if not snapshots:
            return False
        liquidity_values = [self._liquidity_near_price(snapshot, price) for snapshot in snapshots]
        liquidity_values = [val for val in liquidity_values if val is not None and val > 0]
        if not liquidity_values:
            return False
        latest = liquidity_values[-1]
        threshold = float(np.quantile(liquidity_values, 0.9))
        return latest >= threshold

    def _liquidity_near_price(self, snapshot: OrderBookSnapshot | None, price: float) -> float | None:
        if snapshot is None:
            return None
        band = price * self.liquidity_zone_bps / 10_000
        if band <= 0:
            return None
        bids = sum(qty * px for px, qty in snapshot.bids if price - band <= px <= price)
        asks = sum(qty * px for px, qty in snapshot.asks if price <= px <= price + band)
        total = bids + asks
        return float(total) if total > 0 else None

    @staticmethod
    def _latest_atr(df: pd.DataFrame) -> float:
        if df is None or df.empty:
            return 0.0
        for col in ("atr_14", "atr", "atr14"):
            if col in df.columns:
                series = df[col].dropna()
                if not series.empty:
                    return float(series.iloc[-1])
        return 0.0

