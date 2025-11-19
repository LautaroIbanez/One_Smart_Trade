"""Telemetry and logging for campaign metrics to Prometheus/Grafana."""
from __future__ import annotations

from typing import Any

from prometheus_client import Gauge, Histogram, Counter

from app.core.logging import logger

# Prometheus metrics
campaign_calmar_realistic = Gauge(
    "campaign_calmar_realistic",
    "Calmar ratio (realistic) for campaign",
    ["campaign_id"],
)

campaign_max_dd_realistic = Gauge(
    "campaign_max_drawdown_realistic",
    "Maximum drawdown (realistic) for campaign",
    ["campaign_id"],
)

campaign_risk_of_ruin = Gauge(
    "campaign_risk_of_ruin",
    "Risk of ruin probability for campaign",
    ["campaign_id"],
)

campaign_equity_divergence = Gauge(
    "campaign_equity_divergence_pct",
    "Equity divergence between theoretical and realistic (%)",
    ["campaign_id"],
)

campaign_equity_divergence_7d = Gauge(
    "campaign_equity_divergence_7d_pct",
    "Equity divergence over 7 days (%)",
    ["campaign_id"],
)

campaign_metrics_histogram = Histogram(
    "campaign_metrics_duration_seconds",
    "Time to calculate campaign metrics",
    ["campaign_id", "metric_type"],
)

campaign_alert_counter = Counter(
    "campaign_alerts_total",
    "Total number of campaign alerts",
    ["campaign_id", "alert_type", "severity"],
)


class CampaignTelemetry:
    """Telemetry service for campaign metrics."""

    def record_campaign_metrics(
        self,
        campaign_id: str,
        *,
        calmar_realistic: float | None = None,
        max_dd_realistic: float | None = None,
        risk_of_ruin: float | None = None,
        equity_divergence_pct: float | None = None,
        equity_divergence_7d_pct: float | None = None,
    ) -> None:
        """
        Record campaign metrics to Prometheus.

        Args:
            campaign_id: Campaign identifier
            calmar_realistic: Realistic Calmar ratio
            max_dd_realistic: Maximum drawdown (realistic) as decimal (e.g., 0.25 for 25%)
            risk_of_ruin: Risk of ruin probability
            equity_divergence_pct: Equity divergence percentage
            equity_divergence_7d_pct: Equity divergence over 7 days percentage
        """
        if calmar_realistic is not None:
            campaign_calmar_realistic.labels(campaign_id=campaign_id).set(calmar_realistic)

        if max_dd_realistic is not None:
            # Convert to percentage if needed
            max_dd_pct = max_dd_realistic * 100 if max_dd_realistic <= 1.0 else max_dd_realistic
            campaign_max_dd_realistic.labels(campaign_id=campaign_id).set(max_dd_pct)

        if risk_of_ruin is not None:
            campaign_risk_of_ruin.labels(campaign_id=campaign_id).set(risk_of_ruin)

        if equity_divergence_pct is not None:
            campaign_equity_divergence.labels(campaign_id=campaign_id).set(equity_divergence_pct)

        if equity_divergence_7d_pct is not None:
            campaign_equity_divergence_7d.labels(campaign_id=campaign_id).set(equity_divergence_7d_pct)

        logger.info(
            "Campaign metrics recorded",
            extra={
                "campaign_id": campaign_id,
                "calmar_realistic": calmar_realistic,
                "max_dd_realistic": max_dd_realistic,
                "risk_of_ruin": risk_of_ruin,
                "equity_divergence_pct": equity_divergence_pct,
                "equity_divergence_7d_pct": equity_divergence_7d_pct,
            },
        )

    def check_and_alert(
        self,
        campaign_id: str,
        *,
        risk_of_ruin: float | None = None,
        equity_divergence_7d_pct: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Check metrics and emit alerts if thresholds exceeded.

        Args:
            campaign_id: Campaign identifier
            risk_of_ruin: Risk of ruin probability
            equity_divergence_7d_pct: Equity divergence over 7 days (%)

        Returns:
            List of alerts triggered
        """
        alerts = []

        # Risk of ruin alerts
        if risk_of_ruin is not None:
            if risk_of_ruin > 0.20:  # 20% - RED
                alert = {
                    "type": "risk_of_ruin",
                    "severity": "critical",
                    "message": f"Risk of ruin ({risk_of_ruin:.2%}) exceeds critical threshold (20%)",
                    "value": risk_of_ruin,
                    "threshold": 0.20,
                }
                alerts.append(alert)
                campaign_alert_counter.labels(
                    campaign_id=campaign_id,
                    alert_type="risk_of_ruin",
                    severity="critical",
                ).inc()
                logger.error(
                    "Risk of ruin critical alert",
                    extra={"campaign_id": campaign_id, "risk_of_ruin": risk_of_ruin},
                )

            elif risk_of_ruin > 0.10:  # 10% - YELLOW
                alert = {
                    "type": "risk_of_ruin",
                    "severity": "warning",
                    "message": f"Risk of ruin ({risk_of_ruin:.2%}) exceeds warning threshold (10%)",
                    "value": risk_of_ruin,
                    "threshold": 0.10,
                }
                alerts.append(alert)
                campaign_alert_counter.labels(
                    campaign_id=campaign_id,
                    alert_type="risk_of_ruin",
                    severity="warning",
                ).inc()
                logger.warning(
                    "Risk of ruin warning alert",
                    extra={"campaign_id": campaign_id, "risk_of_ruin": risk_of_ruin},
                )

        # Equity divergence alerts
        if equity_divergence_7d_pct is not None:
            if abs(equity_divergence_7d_pct) > 5.0:
                alert = {
                    "type": "equity_divergence",
                    "severity": "warning",
                    "message": f"Equity divergence over 7 days ({equity_divergence_7d_pct:.2f}%) exceeds threshold (5%)",
                    "value": equity_divergence_7d_pct,
                    "threshold": 5.0,
                }
                alerts.append(alert)
                campaign_alert_counter.labels(
                    campaign_id=campaign_id,
                    alert_type="equity_divergence",
                    severity="warning",
                ).inc()
                logger.warning(
                    "Equity divergence alert",
                    extra={
                        "campaign_id": campaign_id,
                        "equity_divergence_7d_pct": equity_divergence_7d_pct,
                    },
                )

        return alerts




