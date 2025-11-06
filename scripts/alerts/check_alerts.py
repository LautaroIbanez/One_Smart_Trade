#!/usr/bin/env python3
"""Check system health and send alerts if needed."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.database import SessionLocal
from app.db.crud import get_last_run
from app.observability.metrics import LAST_INGESTION_TIME, LAST_SIGNAL_TIME
import time


def check_ingestion(max_age_minutes: int = 30):
    """Check if ingestion ran recently."""
    with SessionLocal() as db:
        last_run = get_last_run(db, "ingestion")
        if not last_run:
            return False, "No ingestion runs found"
        
        if last_run.status != "success":
            return False, f"Last ingestion failed: {last_run.message}"
        
        age = (datetime.utcnow() - last_run.finished_at).total_seconds() / 60
        if age > max_age_minutes:
            return False, f"Last ingestion {age:.1f} minutes ago (threshold: {max_age_minutes})"
        
        return True, f"Last ingestion {age:.1f} minutes ago"


def check_signal(max_age_hours: int = 25):
    """Check if signal was generated recently."""
    with SessionLocal() as db:
        last_run = get_last_run(db, "signal")
        if not last_run:
            return False, "No signal runs found"
        
        if last_run.status != "success":
            return False, f"Last signal generation failed: {last_run.message}"
        
        age = (datetime.utcnow() - last_run.finished_at).total_seconds() / 3600
        if age > max_age_hours:
            return False, f"Last signal {age:.1f} hours ago (threshold: {max_age_hours})"
        
        return True, f"Last signal {age:.1f} hours ago"


def check_latency(max_latency_seconds: float = 30.0):
    """Check if API latency is acceptable."""
    # This would query Prometheus metrics in production
    # For now, return OK
    return True, "Latency check not implemented (requires Prometheus query)"


def main():
    """Run all health checks and send alerts if needed."""
    alerts = []
    
    # Check ingestion
    ok, msg = check_ingestion()
    if not ok:
        alerts.append(f"INGESTION: {msg}")
    
    # Check signal
    ok, msg = check_signal()
    if not ok:
        alerts.append(f"SIGNAL: {msg}")
    
    # Check latency (optional)
    # ok, msg = check_latency()
    # if not ok:
    #     alerts.append(f"LATENCY: {msg}")
    
    if alerts:
        alert_text = "\n".join(alerts)
        print(f"ALERTS DETECTED:\n{alert_text}", file=sys.stderr)
        
        # Send webhook if configured
        webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
        if webhook_url:
            os.environ["ALERT_MESSAGE"] = alert_text
            os.environ["ALERT_TITLE"] = "One Smart Trade Health Check Failed"
            from webhook_alert import main as send_webhook
            send_webhook()
        
        # Send email if configured
        smtp_host = os.environ.get("SMTP_HOST")
        if smtp_host:
            os.environ["ALERT_BODY"] = alert_text
            from email_alert import main as send_email
            send_email()
        
        sys.exit(1)
    else:
        print("All checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()

