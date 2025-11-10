"""Performance service for backtesting results."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from app import __version__
from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.report import build_campaign_report
from app.core.config import settings
from app.core.database import SessionLocal
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
            result = self.engine.run_backtest(start_date, end_date)
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
            charts = self._generate_charts(result)
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

            return {
                "status": "success",
                "metrics": metrics,
                "period": {
                    "start": result["start_date"],
                    "end": result["end_date"],
                },
                "report_path": str((self.project_root / "docs" / "backtest-report.md").resolve()),
                "charts": charts,
                "version": __version__,
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

    def _generate_charts(self, backtest_result: dict[str, Any]) -> dict[str, str]:
        charts: dict[str, str] = {}
        equity_curve = backtest_result.get("equity_curve", [])
        trades = backtest_result.get("trades", [])

        def _save_chart(fig: plt.Figure, filename: str) -> str:
            local_path = self.reports_dir / filename
            docs_path = self.docs_assets_dir / filename
            fig.savefig(local_path, dpi=150, bbox_inches="tight")
            fig.savefig(docs_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return str(docs_path.resolve())

        if equity_curve:
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(equity_curve, color="#1d4ed8", label="Equity")
            ax.set_title("Equity Curve")
            ax.set_xlabel("Trade #")
            ax.set_ylabel("Capital ($)")
            ax.grid(True, alpha=0.3)
            ax.legend()
            charts["equity_curve"] = _save_chart(fig, "equity_curve.png")

            series = pd.Series(equity_curve, dtype=float)
            running_max = series.cummax()
            drawdown = ((series - running_max) / running_max) * 100
            drawdown = drawdown.fillna(0.0)

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.fill_between(range(len(drawdown)), drawdown, color="#ef4444", alpha=0.3)
            ax.plot(drawdown, color="#ef4444", label="Drawdown %")
            ax.set_title("Drawdown")
            ax.set_xlabel("Trade #")
            ax.set_ylabel("Drawdown (%)")
            ax.grid(True, alpha=0.3)
            ax.legend()
            charts["drawdown"] = _save_chart(fig, "drawdown.png")

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

        return charts
