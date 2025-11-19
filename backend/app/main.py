"""FastAPI application entry point."""

import asyncio
from contextlib import suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import analytics, diagnostics, execution, export, knowledge, market, observability, operational, orderbook, orders, performance, positions, recommendation, risk, sltp_validation, transparency, user_risk
from app.services.transparency_service import TransparencyService
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging import setup_logging
from app.core.exceptions import RecommendationGenerationError
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
app.include_router(transparency.router, prefix="/api/v1/transparency", tags=["transparency"])
app.include_router(risk.router, prefix="/api/v1/risk", tags=["risk"])
app.include_router(orderbook.router, prefix="/api/v1/orderbook", tags=["orderbook"])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["positions"])
app.include_router(execution.router, prefix="/api/v1/execution", tags=["execution"])
app.include_router(operational.router, prefix="/api/v1/operational", tags=["operational"])
app.include_router(user_risk.router, prefix="/api/v1/user-risk", tags=["user-risk"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(sltp_validation.router, prefix="/api/v1/sltp-validation", tags=["sltp-validation"])


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


@scheduler.scheduled_job("cron", hour="*", minute=0, id="transparency_checks")
async def job_transparency_checks() -> None:
    """Scheduled job to run transparency checks hourly."""
    from app.core.logging import logger
    from app.core.exceptions import RecommendationGenerationError
    
    try:
        transparency_service = TransparencyService()
        semaphore = transparency_service.run_checks()
        
        # Log semaphore status
        logger.info(
            "Transparency checks completed",
            extra={
                "overall_status": semaphore.overall_status.value,
                "hash_verification": semaphore.hash_verification.value,
                "tracking_error_status": semaphore.tracking_error_status.value,
                "drawdown_divergence_status": semaphore.drawdown_divergence_status.value,
                "last_verification": semaphore.last_verification,
            },
        )
        
        # Alert if status is FAIL
        if semaphore.overall_status.value == "fail":
            logger.warning(
                "Transparency checks failed",
                extra={
                    "details": semaphore.details,
                    "overall_status": semaphore.overall_status.value,
                },
            )
    except Exception as exc:
        logger.error(f"Error running transparency checks: {exc}", exc_info=True)


@scheduler.scheduled_job("cron", hour=12, minute=0, id="daily_pipeline")
async def job_daily_pipeline() -> None:
    """
    Deterministic daily pipeline: ingestion → checks → signal generation.
    
    This is the single source of truth for daily signal generation.
    Runs at a fixed time (12:00 UTC) and logs complete outcome with run_id.
    """
    import time
    import uuid
    from datetime import datetime

    from app.core.logging import logger
    from app.data.ingestion import INTERVALS, DataIngestion
    from app.observability.metrics import record_signal_generation
    from app.services.recommendation_service import RecommendationService

    # Generate unique run_id for this pipeline execution
    run_id = str(uuid.uuid4())
    pipeline_start = datetime.utcnow()
    start_time = time.time()
    
    db = SessionLocal()
    outcome_details: dict[str, Any] = {
        "run_id": run_id,
        "pipeline_start": pipeline_start.isoformat(),
        "steps": {},
    }
    
    try:
        logger.info(f"Starting daily pipeline run_id={run_id}")
        
        # Step 1: Data ingestion
        ingestion_start = time.time()
        ingestion = DataIngestion()
        try:
            ingestion_results = await ingestion.ingest_all_timeframes()
            ingestion_duration = time.time() - ingestion_start
            total_rows = sum(item.get("rows", 0) for item in ingestion_results)
            outcome_details["steps"]["ingestion"] = {
                "status": "success",
                "duration_seconds": round(ingestion_duration, 2),
                "total_rows": total_rows,
                "results": ingestion_results,
            }
            logger.info(f"Pipeline {run_id}: Ingestion completed - {total_rows} rows in {ingestion_duration:.2f}s")
        except Exception as exc:
            ingestion_duration = time.time() - ingestion_start
            outcome_details["steps"]["ingestion"] = {
                "status": "failed",
                "duration_seconds": round(ingestion_duration, 2),
                "error": str(exc),
            }
            logger.error(f"Pipeline {run_id}: Ingestion failed - {exc}", exc_info=True)
            raise
        
        # Step 2: Data curation
        curation_start = time.time()
        curation = DataCuration()
        curation_results = {}
        for interval in INTERVALS:
            try:
                curation.curate_interval(interval)
                curation_results[interval] = "success"
            except FileNotFoundError:
                logger.warning(f"Pipeline {run_id}: Skipping interval {interval} - raw data missing")
                curation_results[interval] = "skipped_no_data"
            except Exception as exc:
                logger.warning(f"Pipeline {run_id}: Curation failed for {interval} - {exc}")
                curation_results[interval] = f"error: {str(exc)}"
        curation_duration = time.time() - curation_start
        outcome_details["steps"]["curation"] = {
            "status": "completed",
            "duration_seconds": round(curation_duration, 2),
            "results": curation_results,
        }
        logger.info(f"Pipeline {run_id}: Curation completed in {curation_duration:.2f}s")
        
        # Step 3: Signal generation
        signal_start = time.time()
        service = RecommendationService(session=db)
        try:
            recommendation = await service.generate_recommendation()
            signal_duration = time.time() - signal_start
            
            if recommendation is None:
                raise ValueError("generate_recommendation returned None")
            
            valid_signals = {"BUY", "SELL", "HOLD"}
            failure_statuses = {
                "capital_missing",
                "data_stale",
                "data_gaps",
                "backtest_failed",
                "backtest_error",
                "audit_failed",
                "invalid",
            }
            
            status_value = recommendation.get("status")
            normalized_status = status_value.lower() if isinstance(status_value, str) else None
            signal_value = recommendation.get("signal")
            
            if normalized_status and normalized_status in failure_statuses:
                raise RecommendationGenerationError(
                    status=status_value,
                    reason=recommendation.get("reason") or "Recommendation reported a failure status",
                    details={
                        "failed_status": status_value,
                        "failed_reason": recommendation.get("reason"),
                        "payload": recommendation,
                    },
                )
            
            if not isinstance(signal_value, str) or signal_value.upper() not in valid_signals:
                raise RecommendationGenerationError(
                    status=status_value or "invalid_signal",
                    reason=f"Recommendation returned invalid signal: {signal_value}",
                    details={"failed_status": status_value, "failed_signal": signal_value, "payload": recommendation},
                )
            
            signal = signal_value.upper()
            confidence = recommendation.get("confidence", 0.0)
            
            outcome_details["steps"]["signal_generation"] = {
                "status": "success",
                "duration_seconds": round(signal_duration, 2),
                "signal": signal,
                "confidence": confidence,
                "recommendation_id": recommendation.get("id"),
            }
            
            logger.info(
                f"Pipeline {run_id}: Signal generated - {signal} (confidence: {confidence:.1f}%) in {signal_duration:.2f}s"
            )
            
            record_signal_generation(signal_duration, True)
            
        except Exception as exc:
            signal_duration = time.time() - signal_start
            # Include additional details for RecommendationGenerationError
            error_details = {
                "status": "failed",
                "duration_seconds": round(signal_duration, 2),
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
            # Add recommendation generation error details if available
            if hasattr(exc, "status") and hasattr(exc, "details"):
                from app.core.exceptions import RecommendationGenerationError
                if isinstance(exc, RecommendationGenerationError):
                    error_details["recommendation_status"] = exc.status
                    error_details["recommendation_details"] = exc.details
            
            outcome_details["steps"]["signal_generation"] = error_details
            logger.error(f"Pipeline {run_id}: Signal generation failed - {exc}", exc_info=True)
            record_signal_generation(signal_duration, False, str(type(exc).__name__))
            raise
        
        # Pipeline completed successfully
        total_duration = time.time() - start_time
        outcome_details["pipeline_end"] = datetime.utcnow().isoformat()
        outcome_details["total_duration_seconds"] = round(total_duration, 2)
        outcome_details["overall_status"] = "success"
        
        log_run(
            db,
            "daily_pipeline",
            "success",
            f"Daily pipeline completed successfully - run_id={run_id}",
            details=outcome_details,
            run_id=run_id,
            started_at=pipeline_start,
        )
        
        logger.info(f"Pipeline {run_id}: Completed successfully in {total_duration:.2f}s")
        
    except Exception as exc:
        total_duration = time.time() - start_time
        outcome_details["pipeline_end"] = datetime.utcnow().isoformat()
        outcome_details["total_duration_seconds"] = round(total_duration, 2)
        outcome_details["overall_status"] = "failed"
        outcome_details["error"] = str(exc)
        outcome_details["error_type"] = type(exc).__name__
        
        log_run(
            db,
            "daily_pipeline",
            "failed",
            f"Daily pipeline failed - run_id={run_id} - {str(exc)}",
            details=outcome_details,
            run_id=run_id,
            started_at=pipeline_start,
        )
        
        logger.error(f"Pipeline {run_id}: Failed after {total_duration:.2f}s - {exc}", exc_info=True)
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


@scheduler.scheduled_job("cron", hour="*/1", minute=30, id="monitor_tracking_errors")
async def job_monitor_tracking_errors() -> None:
    """Scheduled job to monitor and calculate tracking errors for closed recommendations."""
    from app.core.logging import logger
    from app.services.tracking_error_service import TrackingErrorService
    
    try:
        service = TrackingErrorService()
        result = await service.monitor_tracking_errors()
        if result.get("status") == "success":
            updated = result.get("updated", 0)
            alerts = result.get("alerts", [])
            if updated > 0:
                logger.info(f"Tracking error monitoring: updated {updated} recommendations")
            if alerts:
                logger.warning(
                    f"Tracking error monitoring: {len(alerts)} recommendations exceeded threshold",
                    extra={"alerts_count": len(alerts), "alerts": alerts},
                )
    except Exception as exc:
        logger.error(f"Tracking error monitoring job failed: {exc}", exc_info=True)


@scheduler.scheduled_job("cron", hour=0, minute=0, id="generate_daily_kpis_report")
async def job_generate_daily_kpis_report() -> None:
    """Scheduled job to generate and archive daily KPI reports."""
    from app.core.logging import logger
    from app.services.kpis_reporting_service import KPIsReportingService
    import os
    
    try:
        service = KPIsReportingService()
        
        # Archive reports (JSON and CSV)
        result = service.archive_daily_report()
        if result.get("status") == "success":
            logger.info(
                f"Daily KPI report archived successfully",
                extra={"results": result.get("results")},
            )
        else:
            logger.warning(f"Daily KPI report archiving completed with errors: {result}")
        
        # Send email if configured
        if os.getenv("SMTP_HOST") and os.getenv("ALERT_TO"):
            try:
                email_result = service.send_report_by_email()
                if email_result.get("status") == "sent":
                    logger.info(f"Daily KPI report sent by email to {email_result.get('to')}")
                elif email_result.get("status") != "not_configured":
                    logger.warning(f"Failed to send KPI report by email: {email_result.get('error')}")
            except Exception as e:
                logger.warning(f"Email sending failed (non-critical): {e}", exc_info=True)
    except Exception as exc:
        logger.error(f"Daily KPI report generation job failed: {exc}", exc_info=True)


@scheduler.scheduled_job("cron", hour=0, minute=0, id="generate_risk_reports")
async def job_generate_risk_reports() -> None:
    """Scheduled job to generate daily risk reports for all users."""
    from app.core.logging import logger
    from app.services.risk_reporting_service import RiskReportingService
    
    try:
        service = RiskReportingService()
        results = service.generate_all_user_reports()
        logger.info(f"Generated {len(results)} risk reports", extra={"reports": results})
    except Exception as exc:
        logger.exception("Failed to generate risk reports", extra={"error": str(exc)})


@scheduler.scheduled_job("cron", minute="*/15", id="check_exposure_alerts")
async def job_check_exposure_alerts() -> None:
    """Scheduled job to check exposure alerts for all users."""
    from app.core.logging import logger
    from app.core.config import settings
    from app.services.exposure_alert_service import ExposureAlertService
    
    try:
        service = ExposureAlertService()
        # For now, single-user system
        user_id = settings.DEFAULT_USER_ID
        result = service.check_exposure_alerts(
            user_id,
            alert_threshold_pct=settings.EXPOSURE_ALERT_THRESHOLD_PCT,
            persistence_minutes=settings.EXPOSURE_ALERT_PERSISTENCE_MINUTES,
        )
        if result.get("alert_active"):
            logger.warning(
                "Exposure alert active",
                extra={"user_id": user_id, "result": result}
            )
    except Exception as exc:
        logger.exception("Failed to check exposure alerts", extra={"error": str(exc)})


@scheduler.scheduled_job("cron", hour="*/1", minute=0, id="verify_transparency")
async def job_verify_transparency() -> None:
    """Scheduled job to verify transparency checks and send alerts if needed."""
    from app.core.logging import logger
    import os
    
    try:
        service = TransparencyService()
        status = service.run_checks()
        
        # Log semaphore status
        logger.info(
            "Transparency verification completed",
            extra={
                "overall_status": status.overall_status.value,
                "hash_status": status.hash_verification.value,
                "dataset_status": status.dataset_verification.value,
                "params_status": status.params_verification.value,
                "tracking_error_status": status.tracking_error_status.value,
                "drawdown_status": status.drawdown_divergence_status.value,
                "audit_status": status.audit_status.value,
            }
        )
        
        # Send alerts if status is not PASS
        if status.overall_status.value != "pass":
            alerts = []
            if status.hash_verification.value != "pass":
                alerts.append(f"Hash verification: {status.hash_verification.value}")
            if status.dataset_verification.value != "pass":
                alerts.append(f"Dataset verification: {status.dataset_verification.value}")
            if status.params_verification.value != "pass":
                alerts.append(f"Params verification: {status.params_verification.value}")
            if status.tracking_error_status.value != "pass":
                alerts.append(f"Tracking error: {status.tracking_error_status.value}")
            if status.drawdown_divergence_status.value != "pass":
                alerts.append(f"Drawdown divergence: {status.drawdown_divergence_status.value}")
            if status.audit_status.value != "pass":
                alerts.append(f"Audit status: {status.audit_status.value}")
            
            message = f"Transparency verification failed: {', '.join(alerts)}"
            logger.warning(message, extra={"semaphore": status.overall_status.value})
            
            # Send webhook if configured
            webhook_url = os.getenv("ALERT_WEBHOOK_URL")
            if webhook_url:
                import httpx
                try:
                    from dataclasses import asdict
                    httpx.post(
                        webhook_url,
                        json={
                            "text": f"Transparency Alert: {message}",
                            "status": status.overall_status.value,
                            "details": asdict(status),
                        },
                        timeout=10.0
                    )
                except Exception:
                    logger.exception("Failed to send transparency webhook alert")
    except Exception as exc:
        logger.exception("Failed to verify transparency", extra={"error": str(exc)})


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

