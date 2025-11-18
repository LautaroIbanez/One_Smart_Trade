"""Trade efficiency metrics and guardrails."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import math
import pandas as pd

from app.backtesting.trade_analytics import TradeAnalyticsRepository
from app.core.logging import logger


@dataclass(frozen=True)
class TradeEfficiencyMetrics:
    """Point-in-time metrics describing a prospective or historical trade."""

    mae: float
    mae_pct: float
    mfe: float
    mfe_pct: float
    ulcer_index: float
    rr_expected: float
    rr_realized: float | None
    risk: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mae": self.mae,
            "mae_pct": self.mae_pct,
            "mfe": self.mfe,
            "mfe_pct": self.mfe_pct,
            "ulcer_index": self.ulcer_index,
            "rr_expected": self.rr_expected,
            "rr_realized": self.rr_realized,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class TradeEfficiencyEvaluation:
    """Result of enforcing efficiency guardrails for a signal."""

    accepted: bool
    summary: str
    reasons: list[str]
    stats: dict[str, Any]
    metrics: TradeEfficiencyMetrics

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "accepted": self.accepted,
            "summary": self.summary,
            "reasons": self.reasons,
            "stats": self.stats,
        }
        payload["metrics"] = self.metrics.to_dict()
        return payload


class TradeEfficiencyAnalyzer:
    """Loads historical MAE/MFE stats and enforces guardrails for new signals."""

    def __init__(
        self,
        *,
        repository: TradeAnalyticsRepository | None = None,
        rr_floor: float = 1.2,
        cache_ttl: int = 10,
    ) -> None:
        self.repository = repository or TradeAnalyticsRepository()
        self.rr_floor = rr_floor
        self.cache_ttl = cache_ttl
        self._stats_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def compute_trade_metrics(self, payload: dict[str, Any]) -> TradeEfficiencyMetrics:
        """Compute MAE/MFE expectations for a signal or closed trade payload."""
        entry_range = payload.get("entry_range") or {}
        sl_tp = payload.get("stop_loss_take_profit") or {}
        entry = float(entry_range.get("optimal", payload.get("entry_price", 0.0)))
        stop_loss = float(sl_tp.get("stop_loss", payload.get("stop_loss", 0.0)))
        take_profit = float(sl_tp.get("take_profit", payload.get("take_profit", 0.0)))

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        mae = payload.get("mae") if isinstance(payload.get("mae"), (int, float)) else risk
        mfe = payload.get("mfe") if isinstance(payload.get("mfe"), (int, float)) else reward

        base = abs(entry) or 1e-9
        mae_pct = (mae / base) * 100.0
        mfe_pct = (mfe / base) * 100.0

        # For individual trades, Ulcer Index is approximated as the MAE percentage
        # (proper UI requires equity curve series, which we don't have for single trades)
        ulcer_index = abs(mae_pct)
        rr_expected = reward / risk if risk else 0.0

        rr_realized = None
        risk_metrics = payload.get("risk_metrics") or {}
        if isinstance(risk_metrics.get("risk_reward_ratio"), (int, float)):
            rr_realized = float(risk_metrics["risk_reward_ratio"])

        return TradeEfficiencyMetrics(
            mae=float(mae),
            mae_pct=float(mae_pct),
            mfe=float(mfe),
            mfe_pct=float(mfe_pct),
            ulcer_index=float(ulcer_index),
            rr_expected=float(rr_expected),
            rr_realized=rr_realized,
            risk=float(risk),
        )

    def evaluate_signal(
        self,
        signal: dict[str, Any],
        *,
        symbol: str,
        regime: str | None = None,
        rr_min_override: float | None = None,
    ) -> TradeEfficiencyEvaluation:
        """Compare a signal's stop/target against historical MAE/MFE tolerances."""
        metrics = self.compute_trade_metrics(signal)
        stats = self._load_stats(symbol, regime)

        reasons: list[str] = []
        accepted = True

        expected_mae = stats.get("mae_p70")
        if expected_mae is not None and metrics.risk > 0 and expected_mae > metrics.risk:
            accepted = False
            reasons.append(
                f"MAE P70 ({expected_mae:.2f}) excede la distancia actual del stop ({metrics.risk:.2f})"
            )

        rr_reference = stats.get("rr_expected") or metrics.rr_expected
        rr_min = rr_min_override or stats.get("rr_min") or self.rr_floor
        if rr_reference is not None and rr_reference < rr_min:
            accepted = False
            reasons.append(
                f"RR esperado ({rr_reference:.2f}) < mínimo permitido ({rr_min:.2f})"
            )

        summary = self._build_summary(accepted, metrics, stats, reasons)
        evaluation = TradeEfficiencyEvaluation(
            accepted=accepted,
            summary=summary,
            reasons=reasons,
            stats=stats,
            metrics=metrics,
        )
        return evaluation

    def _build_summary(
        self,
        accepted: bool,
        metrics: TradeEfficiencyMetrics,
        stats: dict[str, Any],
        reasons: list[str],
    ) -> str:
        mae_ref = stats.get("mae_p70")
        rr_ref = stats.get("rr_expected")
        if not accepted and reasons:
            return reasons[0]

        parts = []
        if mae_ref:
            parts.append(f"Stop sugerido basado en MAE P70 ≈ {mae_ref:.2f}")
        if stats.get("trailing_hint"):
            parts.append(stats["trailing_hint"])
        if rr_ref:
            parts.append(f"RR histórico esperado ≈ {rr_ref:.2f}")
        if not parts:
            return "Sin referencias históricas suficientes para validar eficiencia."
        return "; ".join(parts)

    def _load_stats(self, symbol: str, regime: str | None) -> dict[str, Any]:
        key = (symbol, regime or "global")
        if key in self._stats_cache:
            return self._stats_cache[key]

        df = self.repository.load_latest()
        stats = self._default_stats()
        if df is None or df.empty:
            self._stats_cache[key] = stats
            return stats

        filtered = df[df["symbol"] == symbol] if "symbol" in df.columns else df.copy()
        if regime and "regime" in filtered.columns:
            filtered = filtered[(filtered["regime"].fillna("").str.lower() == regime.lower())]

        if filtered.empty:
            filtered = df  # fallback to global sample

        stats["mae_p50"] = float(filtered["mae"].quantile(0.5)) if "mae" in filtered else None
        stats["mae_p70"] = float(filtered["mae"].quantile(0.7)) if "mae" in filtered else None
        stats["mfe_p50"] = float(filtered["mfe"].quantile(0.5)) if "mfe" in filtered else None

        if "mae" in filtered and "mfe" in filtered:
            rr_series = filtered["mfe"] / filtered["mae"].clip(lower=1e-9)
            stats["rr_expected"] = float(rr_series.mean())

        if stats["mae_p70"] and stats["rr_expected"]:
            stats["trailing_hint"] = (
                f"Trailing dinámico recomendado ≈ {stats['mae_p70'] * 0.5:.2f}"
            )

        self._stats_cache[key] = stats
        return stats

    @staticmethod
    def _default_stats() -> dict[str, Any]:
        return {
            "mae_p50": None,
            "mae_p70": None,
            "mfe_p50": None,
            "rr_expected": None,
            "rr_min": None,
            "trailing_hint": None,
        }


