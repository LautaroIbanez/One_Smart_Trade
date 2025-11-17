"""Observability and dashboard metrics for backtest campaigns."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.core.logging import logger


@dataclass
class CampaignMetrics:
    """Aggregated metrics for a campaign."""

    calmar_train: float
    calmar_val: float
    calmar_wf_avg: float
    calmar_oos: float
    max_drawdown_realistic: float
    risk_of_ruin: float
    cagr_theoretical: float
    cagr_realistic: float
    cagr_divergence_pct: float
    oos_length_days: int
    total_trades: int
    duration_days: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "calmar_train": self.calmar_train,
            "calmar_val": self.calmar_val,
            "calmar_wf_avg": self.calmar_wf_avg,
            "calmar_oos": self.calmar_oos,
            "max_drawdown_realistic": self.max_drawdown_realistic,
            "risk_of_ruin": self.risk_of_ruin,
            "cagr_theoretical": self.cagr_theoretical,
            "cagr_realistic": self.cagr_realistic,
            "cagr_divergence_pct": self.cagr_divergence_pct,
            "oos_length_days": self.oos_length_days,
            "total_trades": self.total_trades,
            "duration_days": self.duration_days,
        }


class CampaignObservability:
    """Observability dashboard for backtest campaigns."""

    def __init__(self) -> None:
        """Initialize observability tracker."""
        self.campaigns: list[CampaignMetrics] = []

    def record_campaign(
        self,
        *,
        train_metrics: dict[str, Any] | None = None,
        val_metrics: dict[str, Any] | None = None,
        wf_result: Any | None = None,  # WalkForwardResult
        oos_metrics: dict[str, Any] | None = None,
        oos_result: dict[str, Any] | None = None,
        duration_days: int,
    ) -> CampaignMetrics:
        """
        Record campaign metrics.

        Args:
            train_metrics: Training set metrics
            val_metrics: Validation set metrics
            wf_result: Walk-forward result
            oos_metrics: OOS metrics
            oos_result: OOS result dict
            duration_days: Total duration in days

        Returns:
            CampaignMetrics
        """
        # Extract Calmar ratios
        calmar_train = train_metrics.get("calmar", 0.0) if train_metrics else 0.0
        calmar_val = val_metrics.get("calmar", 0.0) if val_metrics else 0.0
        calmar_wf_avg = wf_result.avg_test_score if wf_result else 0.0
        calmar_oos = oos_metrics.get("calmar", 0.0) if oos_metrics else 0.0

        # Extract other metrics
        max_drawdown_realistic = oos_metrics.get("max_drawdown", 0.0) / 100.0 if oos_metrics else 0.0
        risk_of_ruin = oos_metrics.get("risk_of_ruin", 0.0) if oos_metrics else 0.0

        # Calculate CAGR
        cagr_theoretical = oos_metrics.get("cagr", 0.0) if oos_metrics else 0.0

        # Calculate realistic CAGR from equity curve
        cagr_realistic = 0.0
        if oos_result and "equity_realistic" in oos_result:
            equity_curve = oos_result["equity_realistic"]
            if len(equity_curve) > 1:
                initial = equity_curve[0]
                final = equity_curve[-1]
                years = duration_days / 365.25
                if years > 0 and initial > 0:
                    cagr_realistic = ((final / initial) ** (1 / years) - 1) * 100

        cagr_divergence_pct = abs(cagr_theoretical - cagr_realistic)

        # Extract trade count
        total_trades = oos_result.get("trades", []) if oos_result else []
        trade_count = len(total_trades) if isinstance(total_trades, list) else 0

        # Extract OOS length
        oos_length_days = oos_result.get("length_days", 0) if oos_result else 0

        metrics = CampaignMetrics(
            calmar_train=calmar_train,
            calmar_val=calmar_val,
            calmar_wf_avg=calmar_wf_avg,
            calmar_oos=calmar_oos,
            max_drawdown_realistic=max_drawdown_realistic,
            risk_of_ruin=risk_of_ruin,
            cagr_theoretical=cagr_theoretical,
            cagr_realistic=cagr_realistic,
            cagr_divergence_pct=cagr_divergence_pct,
            oos_length_days=oos_length_days,
            total_trades=trade_count,
            duration_days=duration_days,
        )

        self.campaigns.append(metrics)

        # Check for alerts
        self._check_alerts(metrics)

        return metrics

    def _check_alerts(self, metrics: CampaignMetrics) -> None:
        """Check for alert conditions and log warnings."""
        # Alert if theoretical and realistic CAGR diverge > 5%
        if metrics.cagr_divergence_pct > 5.0:
            logger.warning(
                "CAGR divergence alert",
                extra={
                    "cagr_theoretical": metrics.cagr_theoretical,
                    "cagr_realistic": metrics.cagr_realistic,
                    "divergence_pct": metrics.cagr_divergence_pct,
                },
            )

        # Alert if OOS Calmar is low
        if metrics.calmar_oos < 1.5:
            logger.warning(
                "Low OOS Calmar",
                extra={
                    "calmar_oos": metrics.calmar_oos,
                    "threshold": 1.5,
                },
            )

        # Alert if max drawdown is high
        if metrics.max_drawdown_realistic > 0.25:
            logger.warning(
                "High max drawdown",
                extra={
                    "max_drawdown": metrics.max_drawdown_realistic,
                    "threshold": 0.25,
                },
            )

    def get_dashboard_data(self) -> dict[str, Any]:
        """
        Get dashboard data for all campaigns.

        Returns:
            Dict with aggregated metrics
        """
        if not self.campaigns:
            return {"campaigns": [], "summary": {}}

        df = pd.DataFrame([m.to_dict() for m in self.campaigns])

        summary = {
            "total_campaigns": len(self.campaigns),
            "avg_calmar_train": float(df["calmar_train"].mean()),
            "avg_calmar_val": float(df["calmar_val"].mean()),
            "avg_calmar_wf": float(df["calmar_wf_avg"].mean()),
            "avg_calmar_oos": float(df["calmar_oos"].mean()),
            "avg_max_drawdown": float(df["max_drawdown_realistic"].mean()),
            "avg_risk_of_ruin": float(df["risk_of_ruin"].mean()),
            "avg_cagr_divergence": float(df["cagr_divergence_pct"].mean()),
            "campaigns_passing_guardrails": int(
                (
                    (df["calmar_oos"] >= 1.5)
                    & (df["max_drawdown_realistic"] <= 0.25)
                    & (df["risk_of_ruin"] <= 0.05)
                    & (df["cagr_divergence_pct"] <= 5.0)
                ).sum()
            ),
        }

        return {
            "campaigns": [m.to_dict() for m in self.campaigns],
            "summary": summary,
        }


