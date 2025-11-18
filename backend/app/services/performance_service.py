"""Performance service for backtesting results."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

from app import __version__
from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.report import build_campaign_report
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import get_latest_backtest_result, save_backtest_result


class PerformanceService:
    """Service for backtesting performance metrics."""

    def __init__(self):
        self.engine = BacktestEngine()
        self.reports_dir = Path(settings.DATA_DIR) / "backtest_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(__file__).resolve().parents[3]
        self.docs_assets_dir = self.project_root / "docs" / "assets"
        self.docs_assets_dir.mkdir(parents=True, exist_ok=True)
        self.performance_config = self._load_performance_config()

    def _load_performance_config(self) -> dict[str, Any]:
        """Load performance/tracking error configuration from YAML file."""
        defaults = {
            "tracking_error": {
                "max_rmse_pct": 0.03,
                "divergence_threshold_pct": 0.02,
            }
        }
        config_paths = [
            Path("config/performance.yaml"),
            Path("backend/config/performance.yaml"),
            self.project_root / "backend" / "config" / "performance.yaml",
        ]
        for path in config_paths:
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                        return raw
                except Exception as exc:
                    logger.warning("Failed to load performance config", extra={"path": str(path), "error": str(exc)})
        return defaults

    async def get_summary(self, use_cache: bool = True) -> dict[str, Any]:
        """Get performance summary from latest backtest."""
        # Check for cached result in DB
        if use_cache:
            with SessionLocal() as db:
                cached = get_latest_backtest_result(db)
                if cached:
                    # Return cached if less than 24 hours old
                    age = (datetime.utcnow() - cached.created_at).total_seconds()
                    if age < 86400:  # 24 hours
                        return {
                            "status": "success",
                            "metrics": cached.metrics,
                            "period": {
                                "start": cached.start_date,
                                "end": cached.end_date,
                            },
                            "report_path": str(self.reports_dir / "backtest-report.md"),
                        }

        # Run backtest for last 5 years if data available
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=5 * 365)

        try:
            result = await self.engine.run_backtest(start_date, end_date)
            if "error" in result:
                error_type = result.get("error_type", "UNKNOWN")
                error_details = result.get("details", result.get("error", "Unknown error"))
                return {
                    "status": "error",
                    "message": result["error"],
                    "error_type": error_type,
                    "details": error_details,
                    "metrics": {}
                }

            metrics = calculate_metrics(result)
            charts, chart_banners = self._generate_charts(result)
            build_campaign_report()

            # Persist to DB with versioning
            with SessionLocal() as db:
                save_backtest_result(
                    db,
                    version=__version__,
                    start_date=result["start_date"],
                    end_date=result["end_date"],
                    metrics=metrics,
                )

            # Calculate OOS days and metrics status
            start_ts = pd.to_datetime(result["start_date"])
            end_ts = pd.to_datetime(result["end_date"])
            total_days = (end_ts - start_ts).days
            
            # Estimate OOS period (20% of total, minimum 120 days)
            oos_days = max(120, int(total_days * 0.2))
            
            # Check metrics status using guardrails
            from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
            checker = GuardrailChecker(GuardrailConfig())
            
            metrics_status = "PASS"
            tracking_error_summary = result.get("tracking_error") or {}
            annualized_te = tracking_error_summary.get("annualized_tracking_error")
            initial_capital = result.get("initial_capital") or 0.0
            tracking_error_annualized_pct = None
            if annualized_te is not None and initial_capital:
                tracking_error_annualized_pct = annualized_te / initial_capital

            guardrail_result = checker.check_all(
                max_drawdown_pct=metrics.get("max_drawdown"),
                risk_of_ruin=metrics.get("risk_of_ruin"),
                trade_count=metrics.get("total_trades", 0),
                duration_days=total_days,
                tracking_error_annualized_pct=tracking_error_annualized_pct,
            )
            if not guardrail_result.passed:
                metrics_status = "FAIL"

            # Extract tracking error and execution data for response
            tracking_error = tracking_error_summary
            tracking_error_metrics = result.get("tracking_error_metrics") or {}
            execution_stats = result.get("execution_stats", {})
            equity_theoretical = result.get("equity_theoretical", [])
            equity_realistic = result.get("equity_realistic", [])
            equity_curve = result.get("equity_curve", [])
            has_realistic_data = bool(result.get("equity_curve_realistic") or equity_realistic)
            tracking_error_series = result.get("tracking_error_series", [])
            tracking_error_cumulative = result.get("tracking_error_cumulative", [])
            
            return {
                "status": "success",
                "metrics": metrics,
                "period": {
                    "start": result["start_date"],
                    "end": result["end_date"],
                },
                "report_path": str((self.project_root / "docs" / "backtest-report.md").resolve()),
                "charts": charts,
                "chart_banners": chart_banners,
                "version": __version__,
                "oos_days": oos_days,
                "metrics_status": metrics_status,
                "equity_theoretical": equity_theoretical,
                "equity_realistic": equity_realistic,
                "equity_curve": equity_curve,
                "tracking_error": tracking_error,
                "tracking_error_metrics": tracking_error_metrics,
                "tracking_error_series": tracking_error_series,
                "tracking_error_cumulative": tracking_error_cumulative,
                "has_realistic_data": has_realistic_data,
            }
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            return {
                "status": "error",
                "message": str(e),
                "error_type": "EXCEPTION",
                "details": error_trace,
                "metrics": {}
            }

    def _generate_charts(self, backtest_result: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        charts: dict[str, str] = {}
        banners: list[str] = []
        equity_curve_records = backtest_result.get("equity_curve", [])
        trades = backtest_result.get("trades", [])
        equity_theoretical = backtest_result.get("equity_theoretical", [])
        equity_realistic = backtest_result.get("equity_realistic", [])
        tracking_error_summary = backtest_result.get("tracking_error") or {}
        tracking_error_metrics = backtest_result.get("tracking_error_metrics") or {}
        tracking_error_series = backtest_result.get("tracking_error_series", [])
        tracking_error_cumulative = backtest_result.get("tracking_error_cumulative", [])

        def _save_chart(fig: plt.Figure, filename: str) -> str:
            local_path = self.reports_dir / filename
            docs_path = self.docs_assets_dir / filename
            fig.savefig(local_path, dpi=150, bbox_inches="tight")
            fig.savefig(docs_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return str(docs_path.resolve())

        # Build consolidated equity DataFrame for plotting
        equity_df = pd.DataFrame(equity_curve_records)
        if equity_df.empty:
            curve_th = backtest_result.get("equity_curve_theoretical", [])
            curve_rl = backtest_result.get("equity_curve_realistic", [])
            if curve_th and curve_rl:
                df_th = pd.DataFrame(curve_th).rename(columns={"equity": "equity_theoretical"})
                df_rl = pd.DataFrame(curve_rl).rename(columns={"equity": "equity_realistic"})
                equity_df = pd.merge(df_th, df_rl, on="timestamp", how="outer")
        if not equity_df.empty:
            equity_df["timestamp"] = pd.to_datetime(equity_df["timestamp"])
            equity_df = equity_df.sort_values("timestamp")

        # Determine data availability and warnings
        has_realistic_data = (
            not equity_df.empty
            and "equity_realistic" in equity_df
            and equity_df["equity_realistic"].notna().any()
        )
        if not has_realistic_data:
            banners.append("WARNING: No hay curva realista para comparar contra la teórica.")

        te_config = self.performance_config.get("tracking_error", {})
        initial_capital = backtest_result.get("initial_capital") or 0.0
        rmse_value = tracking_error_metrics.get("rmse") or tracking_error_summary.get("rmse")
        rmse_threshold_pct = te_config.get("max_rmse_pct")
        if (
            rmse_value is not None
            and initial_capital
            and rmse_threshold_pct is not None
            and (rmse_value / initial_capital) > rmse_threshold_pct
        ):
            banners.append(
                f"ALERT: Tracking error RMSE {rmse_value / initial_capital:.2%} supera el umbral configurado ({rmse_threshold_pct:.0%})."
            )

        divergence_threshold_pct = te_config.get("divergence_threshold_pct")
        divergence_threshold_bps = divergence_threshold_pct * 10000 if divergence_threshold_pct is not None else None
        max_divergence_bps = tracking_error_summary.get("max_divergence_bps")
        if (
            max_divergence_bps is not None
            and divergence_threshold_bps is not None
            and max_divergence_bps > divergence_threshold_bps
        ):
            banners.append(
                f"ALERT: Divergencia máxima {max_divergence_bps:.0f} bps supera el umbral ({divergence_threshold_bps:.0f} bps)."
            )

        # Dual equity curve chart
        if not equity_df.empty:
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(
                equity_df["timestamp"],
                equity_df["equity_theoretical"],
                color="#1d4ed8",
                label="Equity Teórica",
                linewidth=2,
            )
            if has_realistic_data:
                ax.plot(
                    equity_df["timestamp"],
                    equity_df["equity_realistic"],
                    color="#ef4444",
                    label="Equity Realista",
                    linewidth=2,
                )
            ax.set_title("Equity Teórica vs. Realista")
            ax.set_xlabel("Tiempo")
            ax.set_ylabel("Capital ($)")
            ax.grid(True, alpha=0.3)
            ax.legend()
            dual_chart_path = _save_chart(fig, "equity_dual.png")
            charts["equity_dual"] = dual_chart_path
            charts["equity_curve"] = dual_chart_path  # Legacy key

            # Drawdown chart (use realistic if available)
            reference_series = (
                equity_df["equity_realistic"] if has_realistic_data else equity_df["equity_theoretical"]
            ).astype(float)
            running_max = reference_series.cummax()
            drawdown = ((reference_series - running_max) / running_max).fillna(0.0) * 100
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.fill_between(equity_df["timestamp"], drawdown, color="#ef4444", alpha=0.3)
            ax.plot(equity_df["timestamp"], drawdown, color="#ef4444")
            ax.set_title("Drawdown (%)")
            ax.set_xlabel("Tiempo")
            ax.set_ylabel("Drawdown")
            ax.grid(True, alpha=0.3)
            charts["drawdown"] = _save_chart(fig, "drawdown.png")

        # Tracking error panel (instant + cumulative)
        if tracking_error_series:
            te_series_df = pd.DataFrame(tracking_error_series)
            te_series_df["timestamp"] = pd.to_datetime(te_series_df["timestamp"])
            te_series_df = te_series_df.sort_values("timestamp")

            if not tracking_error_cumulative:
                cumulative_values = te_series_df["tracking_error"].cumsum()
                te_cumulative_df = pd.DataFrame(
                    {
                        "timestamp": te_series_df["timestamp"],
                        "tracking_error_cumulative": cumulative_values,
                    }
                )
            else:
                te_cumulative_df = pd.DataFrame(tracking_error_cumulative)
                te_cumulative_df["timestamp"] = pd.to_datetime(te_cumulative_df["timestamp"])
                te_cumulative_df = te_cumulative_df.sort_values("timestamp")

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
            ax1.plot(
                te_series_df["timestamp"],
                te_series_df["tracking_error"],
                color="#f59e0b",
                linewidth=1,
            )
            ax1.axhline(y=0, color="black", linestyle="--", alpha=0.4)
            ax1.set_ylabel("Tracking Error ($)")
            ax1.set_title("Tracking Error Instantáneo (Real - Teórico)")
            ax1.grid(True, alpha=0.3)

            ax2.plot(
                te_cumulative_df["timestamp"],
                te_cumulative_df["tracking_error_cumulative"],
                color="#8b5cf6",
                linewidth=2,
            )
            ax2.axhline(y=0, color="black", linestyle="--", alpha=0.4)
            ax2.set_xlabel("Tiempo")
            ax2.set_ylabel("Tracking Error Acumulado ($)")
            ax2.set_title("Tracking Error Acumulado")
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            te_chart_path = _save_chart(fig, "tracking_error_panel.png")
            charts["tracking_error_panel"] = te_chart_path
            charts["tracking_error"] = te_chart_path  # Legacy key

        if trades:
            df = pd.DataFrame(trades)
            wins = int((df["pnl"] > 0).sum())
            losses = int((df["pnl"] <= 0).sum())
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(["Ganadoras", "Perdedoras"], [wins, losses], color=["#22c55e", "#ef4444"], alpha=0.8)
            ax.set_title("Distribución de Trades")
            ax.set_ylabel("Número de operaciones")
            ax.grid(axis="y", alpha=0.2)
            charts["win_rate"] = _save_chart(fig, "win_rate.png")

        return charts, banners
