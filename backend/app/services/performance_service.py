"""Performance service for backtesting results."""
from typing import Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.report import generate_report
from app.core.config import settings
from app.core.database import SessionLocal
from app.db.crud import save_backtest_result, get_latest_backtest_result
from app import __version__


class PerformanceService:
    """Service for backtesting performance metrics."""

    def __init__(self):
        self.engine = BacktestEngine()
        self.reports_dir = Path(settings.DATA_DIR) / "backtest_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    async def get_summary(self, use_cache: bool = True) -> Dict[str, Any]:
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
                return {"status": "error", "message": result["error"], "metrics": {}}

            metrics = calculate_metrics(result)

            # Generate report
            report_data = generate_report(result, self.reports_dir)

            # Persist to DB
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
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "metrics": {}}
