"""FastAPI application entry point."""

import asyncio
from contextlib import suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import analytics, diagnostics, execution, export, knowledge, market, observability, operational, orderbook, orders, performance, positions, recommendation, risk, user_risk
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging import setup_logging
from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion
from app.db.crud import log_run
from app.middleware.exception_handler import ExceptionHandlerMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.observability.metrics import RequestMetricsMiddleware, metrics_router
from app.services.preflight import run_preflight
from app.analytics.ruin import SurvivalSimulator
from app.analytics.livelihood_report import LivelihoodReport
from app.db.models import PerformancePeriodicORM, PeriodicHorizon
from sqlalchemy import select
import os

# Initialize logging
setup_logging()

app = FastAPI(
    title="One Smart Trade API",
    description="API cuantitativa para recomendaciones de trading BTC",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ExceptionHandlerMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=300)
app.add_middleware(RequestMetricsMiddleware)
app.include_router(metrics_router)

app.include_router(recommendation.router, prefix="/api/v1/recommendation", tags=["recommendation"])
app.include_router(export.router, prefix="/api/v1/recommendation", tags=["recommendation"])
app.include_router(diagnostics.router, prefix="/api/v1/diagnostics", tags=["diagnostics"])
app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
app.include_router(performance.router, prefix="/api/v1/performance", tags=["performance"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(observability.router, prefix="/api/v1/observability", tags=["observability"])
app.include_router(risk.router, prefix="/api/v1/risk", tags=["risk"])
app.include_router(orderbook.router, prefix="/api/v1/orderbook", tags=["orderbook"])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["positions"])
app.include_router(execution.router, prefix="/api/v1/execution", tags=["execution"])
app.include_router(operational.router, prefix="/api/v1/operational", tags=["operational"])
app.include_router(user_risk.router, prefix="/api/v1/user-risk", tags=["user-risk"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "One Smart Trade API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Detailed health check."""
    return {"status": "healthy"}


# Initialize DB
Base.metadata.create_all(bind=engine)


scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)
_preflight_task: asyncio.Task | None = None


@scheduler.scheduled_job("cron", minute="*/15", id="ingest_klines")
async def job_ingest_all() -> None:
    """Scheduled job to ingest data for all timeframes."""
    import time

    from app.observability.metrics import record_ingestion

    ingestion = DataIngestion()
    start_time = time.time()

    try:
        results = await ingestion.ingest_all_timeframes()
        duration = time.time() - start_time
        total_rows = sum(item.get("rows", 0) for item in results)

        db = SessionLocal()
        try:
            log_run(db, "ingestion", "success", f"Fetched {total_rows} rows", {"results": results})
        finally:
            db.close()

        for res in results:
            interval = res.get("interval", "unknown")
            success = res.get("status") == "success"
            record_ingestion(interval, duration / max(len(results), 1), success, res.get("status"))
        record_ingestion("multiple", duration, True)
    except Exception as exc:  # rate limits, timeouts, etc.
        duration = time.time() - start_time
        db = SessionLocal()
        try:
            log_run(db, "ingestion", "failed", str(exc))
        finally:
            db.close()
        record_ingestion("multiple", duration, False, str(type(exc).__name__))


@scheduler.scheduled_job("cron", hour=12, minute=0, id="generate_signal")
async def job_generate_signal() -> None:
    """Scheduled job to generate daily trading signal."""
    import time

    from app.core.logging import logger
    from app.data.ingestion import INTERVALS
    from app.observability.metrics import record_signal_generation
    from app.services.recommendation_service import RecommendationService

    curation = DataCuration()
    start_time = time.time()

    # Regenerate curated datasets before calculating signals
    for interval in INTERVALS:
        try:
            curation.curate_interval(interval)
        except FileNotFoundError:
            logger.warning("Skipping interval %s because raw data is missing", interval)

    db = SessionLocal()
    try:
        service = RecommendationService(session=db)
        # Generate recommendation (will use curated data)
        recommendation = await service.generate_recommendation()
        if recommendation is None:
            raise ValueError("Failed to generate recommendation")

        duration = time.time() - start_time

        log_run(
            db,
            "signal_generation",
            "success",
            "Signal generated",
        )

        record_signal_generation(duration, True)
    except Exception as exc:
        duration = time.time() - start_time
        logger.exception("Signal generation failed")
        log_run(
            db,
            "signal_generation",
            "failed",
            str(exc),
        )
        record_signal_generation(duration, False, str(type(exc).__name__))
    finally:
        db.close()


@scheduler.scheduled_job("cron", hour="*/1", minute=0, id="monitor_performance")
async def job_monitor_performance() -> None:
    """Scheduled job to update performance metrics and check alerts."""
    from app.core.logging import logger
    from app.services.monitoring_service import ContinuousMonitoringService
    
    try:
        monitor = ContinuousMonitoringService(asset="BTCUSDT", venue="binance")
        result = await monitor.update_metrics(lookback_days=365 * 2)
        if result.get("status") == "ok":
            alerts = result.get("alerts", [])
            if alerts:
                logger.warning(
                    "Performance alerts detected",
                    extra={"asset": "BTCUSDT", "alerts_count": len(alerts), "alerts": alerts},
                )
        else:
            logger.debug("Performance monitoring skipped", extra={"reason": result.get("error", "unknown")})
    except Exception as exc:
        logger.exception("Performance monitoring failed", extra={"error": str(exc)})


@scheduler.scheduled_job("cron", hour=1, minute=15, id="analytics_alerts")
async def job_analytics_alerts() -> None:
    """Check survival metrics for recent runs and send alerts if thresholds are breached."""
    from app.core.logging import logger
    try:
        with SessionLocal() as db:
            q = (
                select(PerformancePeriodicORM.run_id)
                .where(PerformancePeriodicORM.horizon == PeriodicHorizon.monthly)
                .group_by(PerformancePeriodicORM.run_id)
                .order_by(PerformancePeriodicORM.created_at.desc())
                .limit(20)
            )
            run_ids = [row[0] for row in db.execute(q).all()]
            if not run_ids:
                return
            # Thresholds
            max_ruin = float(os.getenv("ALERT_MAX_RUIN_PROB", "0.1"))
            max_negative_month = float(os.getenv("ALERT_MAX_NEG_MONTH", "0.5"))
            # Evaluate
            alerts: list[str] = []
            for run_id in run_ids:
                # Load monthly returns
                stmt = (
                    select(PerformancePeriodicORM)
                    .where(PerformancePeriodicORM.run_id == run_id)
                    .where(PerformancePeriodicORM.horizon == PeriodicHorizon.monthly)
                    .order_by(PerformancePeriodicORM.period.asc())
                )
                rows = list(db.execute(stmt).scalars().all())
                if not rows:
                    continue
                import pandas as pd
                returns = pd.Series([r.mean for r in rows])
                sim = SurvivalSimulator(trials=5000, horizon_months=36, ruin_threshold=0.7)
                survival = sim.monte_carlo(returns)
                neg_month_prob = float((returns < 0).mean())
                if survival["ruin_probability"] > max_ruin or neg_month_prob > max_negative_month:
                    alerts.append(
                        f"run_id={run_id} ruin_prob={survival['ruin_probability']:.3f} neg_month_prob={neg_month_prob:.3f}"
                    )
            if alerts:
                message = "Survival metrics degraded:\n" + "\n".join(alerts)
                logger.warning(message)
                # Send webhook if configured
                webhook_url = os.getenv("ALERT_WEBHOOK_URL")
                if webhook_url:
                    import httpx
                    try:
                        httpx.post(webhook_url, json={"text": f"Risk Alerts: {message}"}, timeout=10.0)
                    except Exception:
                        logger.exception("Failed to send webhook alert")
                # Send email if configured
                smtp_host = os.getenv("SMTP_HOST")
                if smtp_host:
                    try:
                        from email.mime.text import MIMEText
                        import smtplib
                        to_addr = os.getenv("ALERT_TO")
                        user = os.getenv("SMTP_USER")
                        password = os.getenv("SMTP_PASS")
                        port = int(os.getenv("SMTP_PORT", "587"))
                        if to_addr and user and password:
                            msg = MIMEText(message)
                            msg["Subject"] = "One Smart Trade Risk Alerts"
                            msg["From"] = os.getenv("ALERT_FROM", user)
                            msg["To"] = to_addr
                            with smtplib.SMTP(smtp_host, port) as server:
                                server.starttls()
                                server.login(user, password)
                                server.sendmail(msg["From"], [to_addr], msg.as_string())
                    except Exception:
                        logger.exception("Failed to send email alert")
    except Exception as exc:
        logger.exception("Analytics alerts job failed", extra={"error": str(exc)})

@scheduler.scheduled_job("cron", minute="*/5", id="auto_close_trades")
async def job_auto_close_trades() -> None:
    """Scheduled job to close open trades when TP/SL levels are hit."""
    from app.services.recommendation_service import RecommendationService

    service = RecommendationService()
    await service.auto_close_open_trade()


@app.on_event("startup")
async def on_startup():
    # Jobs are already scheduled via decorators
    scheduler.start()
    if settings.PRESTART_MAINTENANCE:
        global _preflight_task
        _preflight_task = asyncio.create_task(run_preflight())


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)
    if _preflight_task is not None and not _preflight_task.done():
        _preflight_task.cancel()
        with suppress(asyncio.CancelledError):
            await _preflight_task

