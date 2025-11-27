"""FastAPI application entry point."""

import asyncio
from contextlib import suppress
from typing import Any

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
import pandas as pd
from app.core import pipeline_state

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
    from app.core import pipeline_state
    from fastapi.responses import JSONResponse
    
    # If the startup pipeline is warming up, return a fast 202 so diagnostic tools
    # can detect that the backend is running but still processing.
    if pipeline_state.is_running():
        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "reason": "Startup pipeline en ejecución. Vuelve a intentar en unos momentos.",
                "pipeline": pipeline_state.get_status().to_dict(),
            },
        )
    
    return {"status": "healthy"}


# Initialize DB
Base.metadata.create_all(bind=engine)


# Configure scheduler with defaults tuned for cold start tolerance.
# On cold start, heavy initialization (preflight, initial pipeline) can cause jobs
# to miss their scheduled time. These defaults allow jobs to catch up without warnings.
# Individual jobs can still override these via the decorator parameters.
scheduler = AsyncIOScheduler(
    timezone=settings.SCHEDULER_TIMEZONE,
    job_defaults={
        # Allow 15 minutes of delay before a run is considered a misfire.
        # This tolerates cold start delays from heavy initialization work (preflight,
        # initial pipeline, backtest runs). Jobs scheduled during startup will catch up
        # without generating misfire warnings.
        "misfire_grace_time": 900,  # 15 minutes - increased from 5 minutes for cold start tolerance
        # Prevent unbounded overlap; critical jobs may override as needed
        "max_instances": 1,
        # Coalesce missed runs: if a job misses multiple scheduled times, only run once
        # with the latest scheduled time. This prevents queuing up multiple missed runs
        # during cold start and reduces redundant work.
        "coalesce": True,  # Changed from False to prevent queued misfires on startup
    },
)
_preflight_task: asyncio.Task | None = None


@scheduler.scheduled_job(
    "cron",
    minute="*/15",
    id="ingest_klines",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_ingest_all() -> None:
    """Scheduled job to ingest data for all timeframes."""
    import time

    from app.observability.metrics import record_ingestion

    ingestion = DataIngestion()
    start_time = time.time()

    try:
        venue = settings.PERFORMANCE_STRATEGY_VENUE or "binance"
        symbol = settings.PERFORMANCE_STRATEGY_SYMBOL or "BTCUSDT"

        results = await ingestion.ingest_all_timeframes(venue=venue, symbol=symbol)
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


@scheduler.scheduled_job(
    "cron",
    hour="*",
    minute=0,
    id="transparency_checks",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_transparency_checks() -> None:
    """Scheduled job to run transparency checks hourly."""
    from app.core.logging import logger, sanitize_log_extra
    from app.core.exceptions import RecommendationGenerationError
    
    try:
        transparency_service = TransparencyService()
        semaphore = await transparency_service.run_checks()
        
        # Log semaphore status
        logger.info(
            "Transparency checks completed",
            extra=sanitize_log_extra({
                "overall_status": semaphore.overall_status.value,
                "hash_verification": semaphore.hash_verification.value,
                "tracking_error_status": semaphore.tracking_error_status.value,
                "drawdown_divergence_status": semaphore.drawdown_divergence_status.value,
                "last_verification": semaphore.last_verification,
            }),
        )
        
        # Alert if status is FAIL
        if semaphore.overall_status.value == "fail":
            logger.warning(
                "Transparency checks failed",
                extra=sanitize_log_extra({
                    "details": semaphore.details,
                    "overall_status": semaphore.overall_status.value,
                }),
            )
    except Exception as exc:
        logger.error(f"Error running transparency checks: {exc}", exc_info=True)


@scheduler.scheduled_job(
    "cron",
    hour=12,
    minute=0,
    id="daily_pipeline",
    misfire_grace_time=3600,  # Daily job: tolerate up to 1h delay without dropping the run
    max_instances=1,
)
async def job_daily_pipeline() -> None:
    """
    Deterministic daily pipeline: ingestion → checks → signal generation.
    
    This is the single source of truth for daily signal generation.
    Runs at a fixed time (12:00 UTC) and logs complete outcome with run_id.
    """
    import time
    import uuid
    from datetime import datetime

    from app.core.logging import logger, sanitize_log_extra
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
            venue = settings.PERFORMANCE_STRATEGY_VENUE or "binance"
            symbol = settings.PERFORMANCE_STRATEGY_SYMBOL or "BTCUSDT"

            ingestion_results = await ingestion.ingest_all_timeframes(
                venue=venue, symbol=symbol
            )
            
            # Step 1.5: Verify 1d data exists, force reingestion if missing (especially critical for dev)
            from app.data.storage import get_raw_path, get_curated_path
            from datetime import datetime, timedelta, timezone
            raw_1d_path = get_raw_path(venue, symbol, "1d").parent
            curated_1d_path = get_curated_path(venue, symbol, "1d")
            
            # Check if 1d data is missing
            raw_1d_exists = raw_1d_path.exists() and any(raw_1d_path.glob("*.parquet"))
            curated_1d_exists = curated_1d_path.exists()
            
            if not raw_1d_exists or not curated_1d_exists:
                logger.warning(
                    f"Pipeline {run_id}: 1d data missing (raw_exists={raw_1d_exists}, curated_exists={curated_1d_exists}), forcing reingestion",
                    extra={"venue": venue, "symbol": symbol, "run_id": run_id},
                )
                try:
                    # Determine start time: use last raw file if exists, otherwise 90 days back for dev
                    if raw_1d_exists:
                        from app.data.storage import read_parquet
                        raw_files = sorted(raw_1d_path.glob("*.parquet"))
                        if raw_files:
                            # Execute blocking file read in thread pool to avoid blocking HTTP requests
                            last_raw = await asyncio.to_thread(read_parquet, raw_files[-1])
                            if not last_raw.empty and "open_time" in last_raw.columns:
                                start_time = last_raw["open_time"].max()
                                if isinstance(start_time, pd.Timestamp):
                                    start_time = start_time.to_pydatetime()
                                if start_time.tzinfo is None:
                                    start_time = start_time.replace(tzinfo=timezone.utc)
                            else:
                                start_time = datetime.now(timezone.utc) - timedelta(days=90)
                        else:
                            start_time = datetime.now(timezone.utc) - timedelta(days=90)
                    else:
                        start_time = datetime.now(timezone.utc) - timedelta(days=90)
                    
                    end_time = datetime.now(timezone.utc)
                    
                    # Force reingest 1d
                    reingest_result = await ingestion.ingest_timeframe(
                        "1d",
                        start=start_time,
                        end=end_time,
                        symbol=symbol,
                        venue=venue,
                    )
                    
                    if reingest_result.get("status") == "success":
                        logger.info(
                            f"Pipeline {run_id}: Successfully reingested 1d data - {reingest_result.get('rows', 0)} rows",
                            extra={"venue": venue, "symbol": symbol, "run_id": run_id},
                        )
                        # Add to ingestion results
                        ingestion_results.append(reingest_result)
                    else:
                        logger.warning(
                            f"Pipeline {run_id}: Failed to reingest 1d data: {reingest_result}",
                            extra={"venue": venue, "symbol": symbol, "run_id": run_id},
                        )
                except Exception as reingest_exc:
                    logger.error(
                        f"Pipeline {run_id}: Error during 1d reingestion: {reingest_exc}",
                        exc_info=True,
                        extra={"venue": venue, "symbol": symbol, "run_id": run_id},
                    )
            
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
            # Dev mode: If DEV_FAKE_DATA is enabled and no local data exists, seed demo data instead of failing
            if settings.DEV_FAKE_DATA:
                from app.data.dev_seeding import has_local_raw_data, seed_demo_klines
                if not has_local_raw_data():
                    logger.warning(f"Pipeline {run_id}: Ingestion failed, but DEV_FAKE_DATA is enabled. Seeding demo data instead.")
                    try:
                        demo_results = seed_demo_klines()
                        demo_total_rows = sum(item.get("rows", 0) for item in demo_results.values() if item.get("status") == "success")
                        outcome_details["steps"]["ingestion"] = {
                            "status": "demo_data_seeded",
                            "duration_seconds": round(ingestion_duration, 2),
                            "total_rows": demo_total_rows,
                            "original_error": str(exc),
                            "results": demo_results,
                            "demo_data": True,
                        }
                        logger.info(f"Pipeline {run_id}: Demo data seeded - {demo_total_rows} rows")
                    except Exception as demo_exc:
                        logger.error(f"Pipeline {run_id}: Failed to seed demo data: {demo_exc}", exc_info=True)
                        outcome_details["steps"]["ingestion"] = {
                            "status": "failed",
                            "duration_seconds": round(ingestion_duration, 2),
                            "error": str(exc),
                            "demo_seed_error": str(demo_exc),
                        }
                        raise
                else:
                    # Local data exists, so ingestion failure is real
                    outcome_details["steps"]["ingestion"] = {
                        "status": "failed",
                        "duration_seconds": round(ingestion_duration, 2),
                        "error": str(exc),
                    }
                    logger.error(f"Pipeline {run_id}: Ingestion failed - {exc}", exc_info=True)
                    raise
            else:
                # Not in dev mode, fail normally
                outcome_details["steps"]["ingestion"] = {
                    "status": "failed",
                    "duration_seconds": round(ingestion_duration, 2),
                    "error": str(exc),
                }
                logger.error(f"Pipeline {run_id}: Ingestion failed - {exc}", exc_info=True)
                raise
        
        # Step 2: Data curation
        # Run curation in thread pool to avoid blocking the event loop
        curation_start = time.time()
        curation = DataCuration()
        curation_results = {}
        for interval in INTERVALS:
            try:
                # Execute blocking curation operations in thread pool to avoid blocking HTTP requests
                await asyncio.to_thread(
                    curation.curate_interval,
                    interval,
                    venue=settings.PERFORMANCE_STRATEGY_VENUE,
                    symbol=settings.PERFORMANCE_STRATEGY_SYMBOL
                )
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
        
        # Step 2.5: Performance backfill (after ingestion/curation, before signal generation)
        # This ensures performance cache is populated even if signal generation fails
        # Respects STARTUP_BACKTEST_BACKFILL_ENABLED flag to skip or limit backfill in dev
        performance_start = time.time()
        dev_mode = settings.is_dev_mode()
        
        # Check if backtest backfill is enabled/limited for startup
        backfill_enabled = settings.STARTUP_BACKTEST_BACKFILL_ENABLED
        lookback_days = None
        if isinstance(backfill_enabled, bool):
            if not backfill_enabled:
                logger.info(f"Pipeline {run_id}: Skipping performance backfill (STARTUP_BACKTEST_BACKFILL_ENABLED=False)")
                outcome_details["steps"]["performance_backfill"] = {
                    "status": "skipped",
                    "duration_seconds": 0,
                    "cache_populated": False,
                    "reason": "STARTUP_BACKTEST_BACKFILL_ENABLED=False",
                }
                backfill_enabled = False
            else:
                # Full backfill enabled
                lookback_days = None  # Use default (5 years)
        elif isinstance(backfill_enabled, int) and backfill_enabled > 0:
            # Limited lookback
            lookback_days = backfill_enabled
            logger.info(
                f"Pipeline {run_id}: Performance backfill limited to {lookback_days} days (STARTUP_BACKTEST_BACKFILL_ENABLED={backfill_enabled})",
                extra={"lookback_days": lookback_days},
            )
            backfill_enabled = True
        else:
            # Default: full backfill
            lookback_days = None
            backfill_enabled = True
        
        if backfill_enabled and dev_mode and settings.AUTO_RUN_PIPELINE_ON_START:
            # In dev mode with auto-run, start backfill as background task to avoid blocking
            logger.info(
                f"Pipeline {run_id}: Starting performance backfill in background (dev mode, non-blocking)",
                extra={"lookback_days": lookback_days} if lookback_days else {},
            )
            from app.services.performance_service import get_performance_service
            perf_service = get_performance_service()
            
            async def background_backfill():
                try:
                    backfill_result = await perf_service._run_backtest_and_cache(
                        allow_stale_inputs=True,
                        lookback_days=lookback_days,
                    )
                    if backfill_result:
                        logger.info(f"Pipeline {run_id}: Background performance backfill completed successfully")
                    else:
                        logger.warning(f"Pipeline {run_id}: Background performance backfill completed but no result generated")
                except Exception as bg_exc:
                    logger.warning(f"Pipeline {run_id}: Background performance backfill failed - {bg_exc}", exc_info=True)
            
            # Start background task without awaiting
            asyncio.create_task(background_backfill())
            outcome_details["steps"]["performance_backfill"] = {
                "status": "queued_background",
                "duration_seconds": 0,
                "cache_populated": False,
                "reason": f"Started in background (dev mode, non-blocking, lookback_days={lookback_days or 'full'})",
                "lookback_days": lookback_days,
            }
        elif backfill_enabled:
            # Production mode or manual pipeline: run synchronously
            try:
                from app.services.performance_service import get_performance_service
                perf_service = get_performance_service()
                logger.info(
                    f"Pipeline {run_id}: Starting performance backfill (warmup)",
                    extra={"lookback_days": lookback_days} if lookback_days else {},
                )
                # Run backtest in foreground to populate cache
                backfill_result = await perf_service._run_backtest_and_cache(
                    allow_stale_inputs=dev_mode,
                    lookback_days=lookback_days,
                )
                performance_duration = time.time() - performance_start
                if backfill_result:
                    outcome_details["steps"]["performance_backfill"] = {
                        "status": "success",
                        "duration_seconds": round(performance_duration, 2),
                        "cache_populated": True,
                    }
                    logger.info(f"Pipeline {run_id}: Performance backfill completed in {performance_duration:.2f}s")
                else:
                    outcome_details["steps"]["performance_backfill"] = {
                        "status": "failed",
                        "duration_seconds": round(performance_duration, 2),
                        "cache_populated": False,
                        "reason": "Backtest completed but no result generated",
                    }
                    logger.warning(f"Pipeline {run_id}: Performance backfill completed but no result generated")
            except Exception as perf_exc:
                performance_duration = time.time() - performance_start
                outcome_details["steps"]["performance_backfill"] = {
                    "status": "failed",
                    "duration_seconds": round(performance_duration, 2),
                    "cache_populated": False,
                    "error": str(perf_exc),
                    "error_type": type(perf_exc).__name__,
                }
                # Don't fail the pipeline if performance backfill fails - log warning and continue
                logger.warning(f"Pipeline {run_id}: Performance backfill failed - {perf_exc}", exc_info=True)
        
        # Step 3: Signal generation
        signal_start = time.time()
        service = RecommendationService(session=db)
        try:
            recommendation = await service.generate_recommendation()
            signal_duration = time.time() - signal_start
            
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
            
            # HOLD signals are valid even when guardrails fail - they should be persisted
            # Only abort on actual failure statuses, not on HOLD signals
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
            
            # Log guardrail failures for HOLD signals (but don't abort - these are valid recommendations)
            if signal == "HOLD" and recommendation.get("risk_metrics", {}).get("guardrail_reason"):
                guardrail_reason = recommendation["risk_metrics"]["guardrail_reason"]
                logger.info(
                    f"Pipeline {run_id}: Signal is HOLD due to guardrail: {guardrail_reason} - recommendation will be persisted"
                )
            
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
                # RecommendationGenerationError is already imported at the top of the file
                if isinstance(exc, RecommendationGenerationError):
                    error_details["recommendation_status"] = exc.status
                    error_details["recommendation_details"] = exc.details
            
            # In dev mode, persist fallback recommendation instead of failing
            dev_mode = settings.is_dev_mode()
            if dev_mode and isinstance(exc, RecommendationGenerationError):
                error_status = exc.status
                if error_status in {"data_stale", "audit_failed", "backtest_failed", "data_gaps", "insufficient_history"}:
                    logger.info(
                        f"Pipeline {run_id}: DEV MODE: Signal generation failed ({error_status}), persisting dev fallback recommendation",
                        extra={"error_status": error_status, "error_reason": exc.reason, "dev_mode": True, "run_id": run_id},
                    )
                    try:
                        from app.services.recommendation_service import RecommendationService
                        fallback_service = RecommendationService(session=db)
                        fallback_recommendation = fallback_service._build_dev_fallback_recommendation(signal="HOLD", error_status=error_status)
                        
                        from app.db.crud import create_recommendation
                        rec = create_recommendation(db, fallback_recommendation)
                        
                        error_details["status"] = "degraded_fallback"
                        error_details["fallback_recommendation_id"] = rec.id
                        error_details["fallback_reason"] = error_status
                        error_details["dev_mode"] = True
                        
                        logger.info(
                            f"Pipeline {run_id}: DEV MODE: Dev fallback recommendation persisted - recommendation_id={rec.id}",
                            extra={"recommendation_id": rec.id, "run_id": run_id, "dev_mode": True},
                        )
                        
                        # Don't raise - allow pipeline to complete with degraded status
                        outcome_details["steps"]["signal_generation"] = error_details
                        record_signal_generation(signal_duration, False, str(type(exc).__name__))
                        # Continue to pipeline completion with degraded status
                    except Exception as fallback_exc:
                        logger.error(
                            f"Pipeline {run_id}: Failed to persist dev fallback recommendation: {fallback_exc}",
                            exc_info=True,
                            extra={"run_id": run_id, "dev_mode": True},
                        )
                        # If fallback persistence fails, raise original exception
                        outcome_details["steps"]["signal_generation"] = error_details
                        logger.error(f"Pipeline {run_id}: Signal generation failed - {exc}", exc_info=True)
                        record_signal_generation(signal_duration, False, str(type(exc).__name__))
                        raise
                else:
                    # Other error types in dev mode - still raise
                    outcome_details["steps"]["signal_generation"] = error_details
                    logger.error(f"Pipeline {run_id}: Signal generation failed - {exc}", exc_info=True)
                    record_signal_generation(signal_duration, False, str(type(exc).__name__))
                    raise
            else:
                # Production mode or non-RecommendationGenerationError - raise normally
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
        # Re-raise the exception so callers (e.g., _run_initial_pipeline_if_needed) can detect failure
        raise
    finally:
        db.close()


@scheduler.scheduled_job(
    "cron",
    hour="*/1",
    minute=0,
    id="monitor_performance",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_monitor_performance() -> None:
    """Scheduled job to update performance metrics and check alerts."""
    from app.core.logging import logger, sanitize_log_extra
    from app.services.monitoring_service import ContinuousMonitoringService
    
    try:
        monitor = ContinuousMonitoringService(asset="BTCUSDT", venue="binance")
        result = await monitor.update_metrics(lookback_days=365 * 2)
        if result.get("status") == "ok":
            alerts = result.get("alerts", [])
            if alerts:
                logger.warning(
                    "Performance alerts detected",
                    extra=sanitize_log_extra({"asset": "BTCUSDT", "alerts_count": len(alerts), "alerts": alerts}),
                )
        else:
            logger.debug("Performance monitoring skipped", extra=sanitize_log_extra({"reason": result.get("error", "unknown")}))
    except Exception as exc:
        logger.exception("Performance monitoring failed", extra=sanitize_log_extra({"error": str(exc)}))


@scheduler.scheduled_job(
    "cron",
    hour=1,
    minute=15,
    id="analytics_alerts",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_analytics_alerts() -> None:
    """Check survival metrics for recent runs and send alerts if thresholds are breached."""
    from app.core.logging import logger, sanitize_log_extra
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
        logger.exception("Analytics alerts job failed", extra=sanitize_log_extra({"error": str(exc)}))

@scheduler.scheduled_job(
    "cron",
    minute="*/5",
    id="auto_close_trades",
    misfire_grace_time=180,  # Allow up to 3 minutes of drift under load
    max_instances=2,  # Permit one overlapping retry if a previous run was slightly slow
)
async def job_auto_close_trades() -> None:
    """Scheduled job to close open trades when TP/SL levels are hit."""
    from datetime import datetime, timedelta
    from app.core.logging import logger, sanitize_log_extra
    from app.services.recommendation_service import RecommendationService
    from app.core.config import settings

    # Check if live execution is disabled
    if settings.DISABLE_LIVE_EXECUTION or settings.DECISION_SUPPORT_ONLY:
        logger.info(
            "Live execution disabled by DECISION_SUPPORT_ONLY/DISABLE_LIVE_EXECUTION, skipping job_auto_close_trades",
            extra=sanitize_log_extra({
                "DECISION_SUPPORT_ONLY": settings.DECISION_SUPPORT_ONLY,
                "DISABLE_LIVE_EXECUTION": settings.DISABLE_LIVE_EXECUTION,
            })
        )
        return

    # Compute how far from the ideal 5-minute boundary this execution is
    now = datetime.utcnow()
    # Nearest past 5-minute boundary
    minute_bucket = (now.minute // 5) * 5
    scheduled = now.replace(minute=minute_bucket, second=0, microsecond=0)
    if scheduled > now:
        scheduled -= timedelta(minutes=5)
    delay_seconds = (now - scheduled).total_seconds()

    logger.info(
        "auto_close_trades job starting",
        extra=sanitize_log_extra(
            {
                "started_at": now.isoformat(),
                "scheduled_bucket": scheduled.isoformat(),
                "start_delay_seconds": round(delay_seconds, 2),
            }
        ),
    )

    service = RecommendationService()
    await service.auto_close_open_trade()


@scheduler.scheduled_job(
    "cron",
    hour="*/1",
    minute=30,
    id="monitor_tracking_errors",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_monitor_tracking_errors() -> None:
    """Scheduled job to monitor and calculate tracking errors for closed recommendations."""
    from app.core.logging import logger, sanitize_log_extra
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
                    extra=sanitize_log_extra({"alerts_count": len(alerts), "alerts": alerts}),
                )
    except Exception as exc:
        logger.error(f"Tracking error monitoring job failed: {exc}", exc_info=True)


@scheduler.scheduled_job(
    "cron",
    hour=0,
    minute=0,
    id="generate_daily_kpis_report",
    misfire_grace_time=3600,  # Daily job: tolerate up to 1h delay
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_generate_daily_kpis_report() -> None:
    """Scheduled job to generate and archive daily KPI reports."""
    from app.core.logging import logger, sanitize_log_extra
    from app.services.kpis_reporting_service import KPIsReportingService
    import os
    
    try:
        service = KPIsReportingService()
        
        # Archive reports (JSON and CSV)
        result = service.archive_daily_report()
        if result.get("status") == "success":
            logger.info(
                f"Daily KPI report archived successfully",
                extra=sanitize_log_extra({"results": result.get("results")}),
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


@scheduler.scheduled_job(
    "cron",
    hour=0,
    minute=0,
    id="generate_risk_reports",
    misfire_grace_time=3600,  # Daily job: tolerate up to 1h delay
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_generate_risk_reports() -> None:
    """Scheduled job to generate daily risk reports for all users."""
    from app.core.logging import logger, sanitize_log_extra
    from app.services.risk_reporting_service import RiskReportingService
    
    try:
        service = RiskReportingService()
        results = service.generate_all_user_reports()
        logger.info(f"Generated {len(results)} risk reports", extra=sanitize_log_extra({"reports": results}))
    except Exception as exc:
        logger.exception("Failed to generate risk reports", extra=sanitize_log_extra({"error": str(exc)}))


@scheduler.scheduled_job(
    "cron",
    minute="*/15",
    id="check_exposure_alerts",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_check_exposure_alerts() -> None:
    """Scheduled job to check exposure alerts for all users."""
    from app.core.logging import logger, sanitize_log_extra
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
                extra=sanitize_log_extra({"user_id": user_id, "result": result})
            )
    except Exception as exc:
        logger.exception("Failed to check exposure alerts", extra=sanitize_log_extra({"error": str(exc)}))


@scheduler.scheduled_job(
    "cron",
    hour="*/1",
    minute=0,
    id="verify_transparency",
    misfire_grace_time=900,  # Tolerate up to 15 minutes delay (covers cold start)
    coalesce=True,  # If multiple runs missed during startup, only run once
)
async def job_verify_transparency() -> None:
    """Scheduled job to verify transparency checks and send alerts if needed."""
    from app.core.logging import logger, sanitize_log_extra
    import os
    
    try:
        service = TransparencyService()
        status = await service.run_checks()
        
        # Log semaphore status
        logger.info(
            "Transparency verification completed",
            extra=sanitize_log_extra({
                "overall_status": status.overall_status.value,
                "hash_status": status.hash_verification.value,
                "dataset_status": status.dataset_verification.value,
                "params_status": status.params_verification.value,
                "tracking_error_status": status.tracking_error_status.value,
                "drawdown_status": status.drawdown_divergence_status.value,
                "audit_status": status.audit_status.value,
            })
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
            logger.warning(message, extra=sanitize_log_extra({"semaphore": status.overall_status.value}))
            
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
        logger.exception("Failed to verify transparency", extra=sanitize_log_extra({"error": str(exc)}))


def _has_recent_recommendation() -> bool:
    """
    Check if there's a recommendation for today.
    
    Returns True if a recommendation exists with today's date, False otherwise.
    """
    from datetime import date
    from sqlalchemy import select
    from app.db.models import RecommendationORM
    
    db = SessionLocal()
    try:
        today = date.today().isoformat()
        stmt = select(RecommendationORM).where(RecommendationORM.date == today).limit(1)
        rec = db.execute(stmt).scalars().first()
        return rec is not None
    finally:
        db.close()


async def _run_initial_pipeline_if_needed() -> dict[str, Any]:
    """
    Run initial pipeline if AUTO_RUN_PIPELINE_ON_START is enabled or no recent recommendation exists.
    
    This ensures dev/demo environments have data available immediately without waiting
    for the scheduled 12:00 UTC cron job. The pipeline will run if:
    - AUTO_RUN_PIPELINE_ON_START is True (default for dev/demo), OR
    - No recommendation exists for today's date
    
    The scheduled 12:00 UTC job will still run normally regardless of this startup trigger.
    
    Returns:
        Dictionary with pipeline execution result, including status and details
    """
    from datetime import date
    from app.core.logging import logger, sanitize_log_extra
    
    should_run = False
    reason = ""
    today = date.today().isoformat()
    
    if settings.AUTO_RUN_PIPELINE_ON_START:
        # Check if we already have today's recommendation
        if _has_recent_recommendation():
            logger.info(f"Skipping initial pipeline: recommendation for {today} already exists")
            return {
                "status": "skipped",
                "reason": f"Recommendation for {today} already exists",
                "date": today,
            }
        should_run = True
        reason = f"AUTO_RUN_PIPELINE_ON_START is enabled and no recommendation for {today} exists"
    elif not _has_recent_recommendation():
        should_run = True
        reason = f"No recommendation exists for today ({today})"
    
    if should_run:
        logger.info(f"Running initial pipeline on startup: {reason}")

        pipeline_state.mark_running(reason=reason, date=today)

        async def _run_pipeline_background() -> None:
            try:
                await job_daily_pipeline()
                logger.info("Initial pipeline completed successfully")
                pipeline_state.mark_completed(reason=reason, date=today)
            except Exception as exc:
                logger.error(f"Initial pipeline failed: {exc}", exc_info=True)
                pipeline_state.mark_failed(str(exc), reason=reason, date=today, error_type=type(exc).__name__)

        # Schedule the heavy pipeline asynchronously to avoid blocking the event loop
        # The pipeline itself uses thread pools for blocking operations (read_parquet, write_parquet, etc.)
        asyncio.create_task(_run_pipeline_background())

        return {
            "status": "scheduled",
            "reason": reason,
            "date": today,
        }
    else:
        logger.info(f"Skipping initial pipeline: recommendation for {today} exists and AUTO_RUN_PIPELINE_ON_START is disabled")
        return {
            "status": "skipped",
            "reason": f"Recommendation for {today} exists and AUTO_RUN_PIPELINE_ON_START is disabled",
            "date": today,
        }


@app.on_event("startup")
async def on_startup():
    from app.core.logging import logger, sanitize_log_extra
    
    # Validate API and CORS configuration
    logger.info(
        "API Configuration",
        extra=sanitize_log_extra({
            "cors_origins": settings.CORS_ORIGINS,
            "cors_origins_count": len(settings.CORS_ORIGINS),
            "dev_mode": settings.is_dev_mode(),
        }),
    )
    
    # In dev mode, assert that common dev ports are present in CORS_ORIGINS so frontend UIs work out of the box.
    # This is a soft assertion: it only logs a warning if ports are missing, and should normally be silent
    # because defaults in Settings already include these ports.
    common_dev_ports = ["5173", "3000", "5174", "5175", "8080"]
    configured_ports = [origin.split(":")[-1] for origin in settings.CORS_ORIGINS if ":" in origin]
    missing_ports = [port for port in common_dev_ports if port not in configured_ports]
    if settings.is_dev_mode():
        if missing_ports:
            logger.warning(
                f"DEV MODE: Common dev ports not in CORS_ORIGINS: {missing_ports}. "
                f"Frontend on these ports may be blocked. Current CORS_ORIGINS: {settings.CORS_ORIGINS}",
                extra=sanitize_log_extra({
                    "missing_ports": missing_ports,
                    "cors_origins": settings.CORS_ORIGINS,
                    "dev_mode": True,
                }),
            )
        else:
            # Lightweight positive assertion for validation/diagnostics
            logger.info(
                "DEV MODE: All common dev ports are present in CORS_ORIGINS",
                extra=sanitize_log_extra({
                    "cors_origins": settings.CORS_ORIGINS,
                    "cors_origins_count": len(settings.CORS_ORIGINS),
                    "checked_ports": common_dev_ports,
                    "dev_mode": True,
                }),
            )
    
    # Start the scheduler. Jobs are already scheduled via decorators.
    # Note: On cold start, heavy initialization (preflight, initial pipeline) may cause
    # jobs to miss their scheduled time. The scheduler is configured with:
    # - misfire_grace_time=900 (15 minutes) to tolerate startup delays
    # - coalesce=True to prevent queuing multiple missed runs
    # Jobs will catch up automatically without generating misfire warnings.
    scheduler.start()
    if settings.PRESTART_MAINTENANCE:
        global _preflight_task
        delay_seconds = settings.PRESTART_MAINTENANCE_DELAY_SECONDS
        # Run preflight as background task with delay and error handling to prevent startup failures
        # The delay allows the app to reach ready state before heavy maintenance work begins
        async def run_preflight_safe():
            try:
                logger.info(f"Preflight maintenance scheduled to run in {delay_seconds} seconds (deferred to avoid startup overload)")
                await asyncio.sleep(delay_seconds)
                logger.info("Starting deferred preflight maintenance")
                await run_preflight()
                logger.info("Deferred preflight maintenance completed")
            except Exception as exc:
                logger.error(
                    f"Preflight maintenance failed: {exc}",
                    exc_info=True,
                    extra=sanitize_log_extra({"error_type": type(exc).__name__, "error": str(exc)}),
                )
                # Don't raise - allow server to start even if preflight fails
                # Preflight is maintenance, not critical for server operation
        
        _preflight_task = asyncio.create_task(run_preflight_safe())
    else:
        logger.info("Preflight maintenance disabled (PRESTART_MAINTENANCE=False)")
    
    # Schedule initial pipeline as background task instead of awaiting it
    # This allows the app to signal readiness immediately while the pipeline runs in the background
    # The function itself will decide whether to run based on AUTO_RUN_PIPELINE_ON_START and existing recommendations
    asyncio.create_task(_run_initial_pipeline_if_needed())
    logger.info("Startup tasks scheduled; application ready")


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)
    if _preflight_task is not None and not _preflight_task.done():
        _preflight_task.cancel()
        with suppress(asyncio.CancelledError):
            await _preflight_task

