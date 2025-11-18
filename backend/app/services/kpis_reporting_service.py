"""Service for generating daily KPI reports from recommendations."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import get_recommendation_history, calculate_production_drawdown
from app.db.models import RecommendationORM
from sqlalchemy import and_, func, select


class KPIsReportingService:
    """Service for generating daily KPI reports."""
    
    def __init__(self):
        self.reports_dir = Path(settings.DATA_DIR) / "kpis_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def calculate_daily_kpis(self, lookback_days: int = 30) -> dict[str, Any]:
        """
        Calculate daily KPIs from recommendations.
        
        Args:
            lookback_days: Number of days to look back (default: 30)
        
        Returns:
            Dict with KPIs: win_rate_30d, avg_risk_reward_ratio, drawdown, hold_count
        """
        db = SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
            
            # Get recommendations from last 30 days
            stmt = select(RecommendationORM).where(
                RecommendationORM.created_at >= cutoff_date
            ).order_by(RecommendationORM.created_at.desc())
            
            recs = db.execute(stmt).scalars().all()
            
            if not recs:
                return {
                    "report_date": datetime.utcnow().isoformat(),
                    "lookback_days": lookback_days,
                    "win_rate_30d": 0.0,
                    "avg_risk_reward_ratio": 0.0,
                    "drawdown_pct": 0.0,
                    "hold_count": 0,
                    "total_recommendations": 0,
                    "closed_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "status": "no_data",
                }
            
            # Calculate metrics
            closed_trades = []
            hold_count = 0
            risk_reward_ratios = []
            
            for rec in recs:
                # Count HOLD signals
                if rec.signal == "HOLD":
                    hold_count += 1
                    continue
                
                # For closed trades, calculate win rate and RR
                if rec.status == "closed" and rec.exit_price and rec.entry_optimal:
                    # Calculate return
                    if rec.signal == "BUY":
                        return_pct = ((rec.exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
                    elif rec.signal == "SELL":
                        return_pct = ((rec.entry_optimal - rec.exit_price) / rec.entry_optimal) * 100
                    else:
                        return_pct = 0.0
                    
                    is_win = return_pct > 0
                    closed_trades.append({
                        "return_pct": return_pct,
                        "is_win": is_win,
                    })
                    
                    # Calculate risk/reward ratio from SL/TP
                    if rec.stop_loss and rec.take_profit and rec.entry_optimal:
                        risk = abs(rec.entry_optimal - rec.stop_loss)
                        reward = abs(rec.take_profit - rec.entry_optimal)
                        if risk > 0:
                            rr_ratio = reward / risk
                            risk_reward_ratios.append(rr_ratio)
            
            # Calculate win rate
            winning_trades = sum(1 for t in closed_trades if t["is_win"])
            losing_trades = len(closed_trades) - winning_trades
            win_rate_30d = (winning_trades / len(closed_trades) * 100) if closed_trades else 0.0
            
            # Calculate average risk/reward ratio
            avg_risk_reward_ratio = (sum(risk_reward_ratios) / len(risk_reward_ratios)) if risk_reward_ratios else 0.0
            
            # Get current drawdown
            dd_info = calculate_production_drawdown(db)
            drawdown_pct = dd_info.get("current_drawdown_pct", 0.0)
            
            return {
                "report_date": datetime.utcnow().isoformat(),
                "lookback_days": lookback_days,
                "win_rate_30d": round(win_rate_30d, 2),
                "avg_risk_reward_ratio": round(avg_risk_reward_ratio, 2),
                "drawdown_pct": round(drawdown_pct, 2),
                "hold_count": hold_count,
                "total_recommendations": len(recs),
                "closed_trades": len(closed_trades),
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "status": "success",
            }
        finally:
            db.close()
    
    def generate_report(self, format: str = "json", lookback_days: int = 30) -> dict[str, Any]:
        """
        Generate KPI report in specified format.
        
        Args:
            format: Report format ("json" or "csv")
            lookback_days: Number of days to look back (default: 30)
        
        Returns:
            Dict with report content, filepath, and metadata
        """
        kpis = self.calculate_daily_kpis(lookback_days=lookback_days)
        
        # Add metadata
        report = {
            **kpis,
            "generated_at": datetime.utcnow().isoformat(),
            "format": format,
        }
        
        # Generate filename with date
        date_str = datetime.utcnow().strftime("%Y%m%d")
        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        if format == "json":
            filename = f"kpis_report_{timestamp_str}.json"
            filepath = self.reports_dir / filename
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            content = json.dumps(report, indent=2, default=str).encode("utf-8")
            media_type = "application/json"
        elif format == "csv":
            filename = f"kpis_report_{timestamp_str}.csv"
            filepath = self.reports_dir / filename
            
            # Convert to CSV format
            csv_rows = [
                ["Metric", "Value"],
                ["Report Date", report["report_date"]],
                ["Lookback Days", report["lookback_days"]],
                ["Win Rate 30d (%)", report["win_rate_30d"]],
                ["Avg Risk/Reward Ratio", report["avg_risk_reward_ratio"]],
                ["Drawdown (%)", report["drawdown_pct"]],
                ["HOLD Count", report["hold_count"]],
                ["Total Recommendations", report["total_recommendations"]],
                ["Closed Trades", report["closed_trades"]],
                ["Winning Trades", report["winning_trades"]],
                ["Losing Trades", report["losing_trades"]],
                ["Generated At", report["generated_at"]],
            ]
            
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(csv_rows)
            
            # Read back for content
            with open(filepath, "rb") as f:
                content = f.read()
            media_type = "text/csv"
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        logger.info(f"Generated KPI report: {filepath} (format: {format})")
        
        return {
            "status": "success",
            "filepath": str(filepath),
            "filename": filename,
            "content": content,
            "media_type": media_type,
            "report": report,
        }
    
    def archive_daily_report(self) -> dict[str, Any]:
        """
        Generate and archive daily KPI report in both JSON and CSV formats.
        
        Returns:
            Dict with archive results
        """
        results = []
        
        # Generate JSON report
        try:
            json_report = self.generate_report(format="json", lookback_days=30)
            results.append({
                "format": "json",
                "filepath": json_report["filepath"],
                "status": "success",
            })
        except Exception as e:
            logger.error(f"Failed to generate JSON report: {e}", exc_info=True)
            results.append({
                "format": "json",
                "status": "error",
                "error": str(e),
            })
        
        # Generate CSV report
        try:
            csv_report = self.generate_report(format="csv", lookback_days=30)
            results.append({
                "format": "csv",
                "filepath": csv_report["filepath"],
                "status": "success",
            })
        except Exception as e:
            logger.error(f"Failed to generate CSV report: {e}", exc_info=True)
            results.append({
                "format": "csv",
                "status": "error",
                "error": str(e),
            })
        
        return {
            "status": "success",
            "archived_at": datetime.utcnow().isoformat(),
            "results": results,
        }
    
    def get_latest_report(self, format: str = "json") -> dict[str, Any] | None:
        """
        Get the latest archived report.
        
        Args:
            format: Report format ("json" or "csv")
        
        Returns:
            Dict with report data or None if not found
        """
        pattern = f"kpis_report_*.{format}"
        reports = list(self.reports_dir.glob(pattern))
        
        if not reports:
            return None
        
        # Sort by modification time (most recent first)
        latest = max(reports, key=lambda p: p.stat().st_mtime)
        
        try:
            if format == "json":
                with open(latest, "r") as f:
                    return json.load(f)
            elif format == "csv":
                # Read CSV and convert to dict
                with open(latest, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    # Convert to dict format
                    report_dict = {}
                    for row in rows:
                        if len(row) >= 2:
                            key = row["Metric"]
                            value = row["Value"]
                            # Try to convert numeric values
                            try:
                                if "." in value:
                                    value = float(value)
                                else:
                                    value = int(value)
                            except ValueError:
                                pass
                            report_dict[key.lower().replace(" ", "_")] = value
                    return report_dict
        except Exception as e:
            logger.error(f"Failed to read latest report {latest}: {e}", exc_info=True)
            return None
    
    def send_report_by_email(
        self,
        to_address: str | None = None,
        lookback_days: int = 30,
    ) -> dict[str, Any]:
        """
        Send daily KPI report by email (optional).
        
        Args:
            to_address: Email address to send to (if None, uses ALERT_TO env var)
            lookback_days: Number of days to look back (default: 30)
        
        Returns:
            Dict with send status
        """
        import os
        
        # Get email configuration
        smtp_host = os.getenv("SMTP_HOST")
        if not smtp_host:
            return {"status": "not_configured", "reason": "SMTP_HOST not configured"}
        
        to_addr = to_address or os.getenv("ALERT_TO")
        if not to_addr:
            return {"status": "not_configured", "reason": "ALERT_TO not configured and no address provided"}
        
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASS")
        port = int(os.getenv("SMTP_PORT", "587"))
        from_addr = os.getenv("ALERT_FROM", user)
        
        if not all([user, password]):
            return {"status": "not_configured", "reason": "SMTP credentials not configured"}
        
        try:
            # Generate report
            kpis = self.calculate_daily_kpis(lookback_days=lookback_days)
            
            # Format email body
            body_lines = [
                "Daily KPI Report",
                "=" * 50,
                f"Report Date: {kpis['report_date']}",
                f"Lookback Period: {kpis['lookback_days']} days",
                "",
                "Key Metrics:",
                f"  Win Rate (30d): {kpis['win_rate_30d']:.2f}%",
                f"  Avg Risk/Reward Ratio: {kpis['avg_risk_reward_ratio']:.2f}",
                f"  Current Drawdown: {kpis['drawdown_pct']:.2f}%",
                f"  HOLD Count: {kpis['hold_count']}",
                "",
                "Trade Statistics:",
                f"  Total Recommendations: {kpis['total_recommendations']}",
                f"  Closed Trades: {kpis['closed_trades']}",
                f"  Winning Trades: {kpis['winning_trades']}",
                f"  Losing Trades: {kpis['losing_trades']}",
                "",
                "Generated by One Smart Trade",
            ]
            body = "\n".join(body_lines)
            
            # Send email
            from email.mime.text import MIMEText
            import smtplib
            
            msg = MIMEText(body)
            msg["Subject"] = f"Daily KPI Report - {datetime.utcnow().strftime('%Y-%m-%d')}"
            msg["From"] = from_addr
            msg["To"] = to_addr
            
            with smtplib.SMTP(smtp_host, port) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
            
            logger.info(f"Daily KPI report sent by email to {to_addr}")
            return {
                "status": "sent",
                "to": to_addr,
                "sent_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to send KPI report by email: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

