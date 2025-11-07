"""Performance service for backtesting results."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app import __version__
from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.report import generate_report
from app.core.config import settings
from app.core.database import SessionLocal
from app.db.crud import get_latest_backtest_result, save_backtest_result


class PerformanceService:
    """Service for backtesting performance metrics."""

    def __init__(self):
        self.engine = BacktestEngine()
        self.reports_dir = Path(settings.DATA_DIR) / "backtest_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

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

            # Generate report (this also writes to docs/backtest-report.md)
            report_data = generate_report(result, self.reports_dir)

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
                "report_path": report_data["report_path"],
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
