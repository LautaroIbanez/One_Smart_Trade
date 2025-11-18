"""Reporting module for SL/TP walk-forward optimization results."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.logging import logger


@dataclass
class WalkForwardReport:
    """Container for walk-forward optimization report data."""

    symbol: str
    regime: str
    windows: list[dict[str, Any]]
    consensus_params: dict[str, float]
    aggregate_metrics: dict[str, float]
    mae_distribution: dict[str, float]
    mfe_distribution: dict[str, float]
    trailing_stop_hit_rate: float | None
    rr_vs_benchmark: dict[str, float]
    max_drawdown: float
    generated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "windows": self.windows,
            "consensus_params": self.consensus_params,
            "aggregate_metrics": self.aggregate_metrics,
            "mae_distribution": self.mae_distribution,
            "mfe_distribution": self.mfe_distribution,
            "trailing_stop_hit_rate": self.trailing_stop_hit_rate,
            "rr_vs_benchmark": self.rr_vs_benchmark,
            "max_drawdown": self.max_drawdown,
            "generated_at": self.generated_at.isoformat(),
        }


class SLTPReportGenerator:
    """Generate markdown reports and dashboards for SL/TP optimization results."""

    def __init__(self, artifacts_dir: str | Path = "artifacts/sl_tp", reports_dir: str | Path = "reports"):
        """Initialize report generator."""
        self.artifacts_dir = Path(artifacts_dir)
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        symbol: str,
        regime: str,
        windows: list[dict[str, Any]],
        consensus_params: dict[str, float],
        aggregate_metrics: dict[str, float],
        trades_df: pd.DataFrame | None = None,
        benchmark_rr: float = 1.5,
    ) -> WalkForwardReport:
        """
        Generate comprehensive report from optimization results.

        Args:
            symbol: Trading symbol
            regime: Market regime
            windows: List of window results from walk-forward
            consensus_params: Consensus parameters across windows
            aggregate_metrics: Aggregate metrics across all windows
            trades_df: Optional trades dataframe for MAE/MFE analysis
            benchmark_rr: Benchmark RR ratio for comparison

        Returns:
            WalkForwardReport object
        """
        # Calculate MAE/MFE distributions
        mae_dist = self._calculate_mae_mfe_distribution(trades_df, "mae") if trades_df is not None else {}
        mfe_dist = self._calculate_mae_mfe_distribution(trades_df, "mfe") if trades_df is not None else {}

        # Calculate trailing stop hit rate (if available in windows)
        trailing_hit_rate = self._calculate_trailing_hit_rate(windows)

        # Calculate RR vs benchmark
        avg_rr = aggregate_metrics.get("avg_rr", 0.0)
        rr_vs_benchmark = {
            "optimized_rr": avg_rr,
            "benchmark_rr": benchmark_rr,
            "improvement_pct": ((avg_rr - benchmark_rr) / benchmark_rr * 100.0) if benchmark_rr > 0 else 0.0,
        }

        max_dd = aggregate_metrics.get("max_drawdown", 0.0)

        report = WalkForwardReport(
            symbol=symbol,
            regime=regime,
            windows=windows,
            consensus_params=consensus_params,
            aggregate_metrics=aggregate_metrics,
            mae_distribution=mae_dist,
            mfe_distribution=mfe_dist,
            trailing_stop_hit_rate=trailing_hit_rate,
            rr_vs_benchmark=rr_vs_benchmark,
            max_drawdown=max_dd,
            generated_at=datetime.utcnow(),
        )

        return report

    def save_markdown_report(self, report: WalkForwardReport) -> Path:
        """Save report as markdown file."""
        filename = f"sl_tp_walkforward_{report.symbol}_{report.regime}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.reports_dir / filename

        content = self._format_markdown(report)
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Saved SL/TP report to {filepath}")
        return filepath

    def _calculate_mae_mfe_distribution(self, trades_df: pd.DataFrame, column: str) -> dict[str, float]:
        """Calculate distribution statistics for MAE or MFE."""
        if trades_df is None or column not in trades_df.columns:
            return {}

        values = trades_df[column].dropna()
        if values.empty:
            return {}

        return {
            "p50": float(values.quantile(0.5)),
            "p70": float(values.quantile(0.7)),
            "p90": float(values.quantile(0.9)),
            "p95": float(values.quantile(0.95)),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "min": float(values.min()),
            "max": float(values.max()),
        }

    def _calculate_trailing_hit_rate(self, windows: list[dict[str, Any]]) -> float | None:
        """Calculate trailing stop hit rate from window results."""
        hit_rates = []
        for window in windows:
            test_metrics = window.get("test_metrics", {})
            # Assuming trailing stop data might be in metrics
            if "trailing_stop_hit_rate" in test_metrics:
                hit_rates.append(test_metrics["trailing_stop_hit_rate"])
            elif "hit_rate" in test_metrics:
                # Use general hit rate as proxy
                hit_rates.append(test_metrics["hit_rate"])

        if not hit_rates:
            return None
        return float(sum(hit_rates) / len(hit_rates))

    def _format_markdown(self, report: WalkForwardReport) -> str:
        """Format report as markdown."""
        lines = [
            f"# SL/TP Walk-Forward Optimization Report",
            "",
            f"**Symbol:** {report.symbol}  ",
            f"**Regime:** {report.regime}  ",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            "",
            "---",
            "",
            "## Consensus Parameters",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
        ]

        for param, value in report.consensus_params.items():
            lines.append(f"| {param} | {value:.4f} |")

        lines.extend([
            "",
            "## Aggregate Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Calmar Ratio | {report.aggregate_metrics.get('calmar', 0.0):.4f} |",
            f"| Profit Factor | {report.aggregate_metrics.get('profit_factor', 0.0):.4f} |",
            f"| Hit Rate | {report.aggregate_metrics.get('hit_rate', 0.0):.2%} |",
            f"| Avg RR | {report.aggregate_metrics.get('avg_rr', 0.0):.4f} |",
            f"| Expectancy (R) | {report.aggregate_metrics.get('expectancy_r', 0.0):.4f} |",
            f"| Max Drawdown | {report.aggregate_metrics.get('max_drawdown', 0.0):.2%} |",
            "",
            "## MAE Distribution",
            "",
        ])

        if report.mae_distribution:
            lines.extend([
                "| Percentile | Value |",
                "|------------|-------|",
                f"| P50 (Median) | {report.mae_distribution.get('p50', 0.0):.4f} |",
                f"| P70 | {report.mae_distribution.get('p70', 0.0):.4f} |",
                f"| P90 | {report.mae_distribution.get('p90', 0.0):.4f} |",
                f"| P95 | {report.mae_distribution.get('p95', 0.0):.4f} |",
                f"| Mean | {report.mae_distribution.get('mean', 0.0):.4f} |",
                f"| Std Dev | {report.mae_distribution.get('std', 0.0):.4f} |",
                "",
            ])
        else:
            lines.append("*No MAE data available*  \n")

        lines.extend([
            "## MFE Distribution",
            "",
        ])

        if report.mfe_distribution:
            lines.extend([
                "| Percentile | Value |",
                "|------------|-------|",
                f"| P50 (Median) | {report.mfe_distribution.get('p50', 0.0):.4f} |",
                f"| P70 | {report.mfe_distribution.get('p70', 0.0):.4f} |",
                f"| P90 | {report.mfe_distribution.get('p90', 0.0):.4f} |",
                f"| P95 | {report.mfe_distribution.get('p95', 0.0):.4f} |",
                f"| Mean | {report.mfe_distribution.get('mean', 0.0):.4f} |",
                f"| Std Dev | {report.mfe_distribution.get('std', 0.0):.4f} |",
                "",
            ])
        else:
            lines.append("*No MFE data available*  \n")

        if report.trailing_stop_hit_rate is not None:
            lines.extend([
                f"## Trailing Stop Performance",
                "",
                f"**Hit Rate:** {report.trailing_stop_hit_rate:.2%}  ",
                "",
            ])

        lines.extend([
            "## RR vs Benchmark",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Optimized RR | {report.rr_vs_benchmark.get('optimized_rr', 0.0):.4f} |",
            f"| Benchmark RR | {report.rr_vs_benchmark.get('benchmark_rr', 0.0):.4f} |",
            f"| Improvement | {report.rr_vs_benchmark.get('improvement_pct', 0.0):+.2f}% |",
            "",
            "## Walk-Forward Windows",
            "",
        ])

        for i, window in enumerate(report.windows, 1):
            lines.extend([
                f"### Window {i}",
                "",
                f"**Train:** {window['train_range'][0]} to {window['train_range'][1]}  ",
                f"**Test:** {window['test_range'][0]} to {window['test_range'][1]}  ",
                "",
                "**Test Metrics:**",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Calmar | {window['test_metrics'].get('calmar', 0.0):.4f} |",
                f"| Profit Factor | {window['test_metrics'].get('profit_factor', 0.0):.4f} |",
                f"| Hit Rate | {window['test_metrics'].get('hit_rate', 0.0):.2%} |",
                f"| Avg RR | {window['test_metrics'].get('avg_rr', 0.0):.4f} |",
                f"| Max DD | {window['test_metrics'].get('max_drawdown', 0.0):.2%} |",
                "",
            ])

        lines.extend([
            "---",
            "",
            "*Report generated by SL/TP Optimization Pipeline*",
        ])

        return "\n".join(lines)

