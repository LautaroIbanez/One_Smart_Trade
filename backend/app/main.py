"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.exception_handler import ExceptionHandlerMiddleware
from app.observability.metrics import RequestMetricsMiddleware, metrics_router
from app.api.v1 import recommendation, diagnostics, market, performance
from app.core.config import settings
from app.core.logging import setup_logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, time
from app.core.database import engine, Base
from app.data.ingestion import DataIngestion
from app.data.curation import DataCuration
from app.quant.signal_engine import generate_signal
from app.core.config import settings
from app.db import models
from app.core.database import SessionLocal
from app.db.crud import create_recommendation, log_run

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
app.include_router(diagnostics.router, prefix="/api/v1/diagnostics", tags=["diagnostics"])
app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
app.include_router(performance.router, prefix="/api/v1/performance", tags=["performance"])


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


async def job_ingest_all():
    from app.observability.metrics import record_ingestion
    from app.core.logging import logger
    import time
    import httpx
    
    di = DataIngestion()
    start_time = time.time()
    try:
        logger.info("Starting scheduled ingestion job")
        results = await di.ingest_all_timeframes()
        duration = time.time() - start_time
        
        # Check for failures in results
        failed = [r for r in results if r.get("status") == "error"]
        if failed:
            reason = f"{len(failed)} timeframes failed"
            logger.warning(f"Ingestion completed with {len(failed)} failures", extra={"failed": failed})
            record_ingestion("all", duration, False, reason)
            db = SessionLocal()
            try:
                log_run(db, "ingestion", "error", reason)
            finally:
                db.close()
        else:
            logger.info(f"Ingestion completed successfully in {duration:.2f}s", extra={"duration": duration})
            record_ingestion("all", duration, True)
            db = SessionLocal()
            try:
                log_run(db, "ingestion", "success")
            finally:
                db.close()
    except httpx.HTTPStatusError as e:
        duration = time.time() - start_time
        if e.response.status_code == 429:
            reason = "RateLimited"
            logger.warning("Ingestion rate limited by Binance", extra={"status_code": 429})
        else:
            reason = f"HTTPError_{e.response.status_code}"
            logger.error(f"Ingestion HTTP error: {e.response.status_code}", exc_info=True)
        record_ingestion("all", duration, False, reason)
        db = SessionLocal()
        try:
            log_run(db, "ingestion", "error", f"{reason}: {str(e)}")
        finally:
            db.close()
    except Exception as e:
        duration = time.time() - start_time
        reason = type(e).__name__
        logger.error(f"Ingestion job failed: {reason}", exc_info=True, extra={"error": str(e)})
        record_ingestion("all", duration, False, reason)
        db = SessionLocal()
        try:
            log_run(db, "ingestion", "error", str(e))
        finally:
            db.close()


async def job_generate_signal():
    from app.observability.metrics import record_signal_generation
    from app.core.logging import logger
    import time
    
    start_time = time.time()
    try:
        logger.info("Starting scheduled signal generation job")
        dc = DataCuration()
        df_1d = dc.get_latest_curated("1d")
        df_1h = dc.get_latest_curated("1h")
        
        if df_1d is None or df_1d.empty:
            duration = time.time() - start_time
            reason = "NoData_1d"
            logger.warning("Signal generation failed: no 1d curated data available")
            record_signal_generation(duration, False, reason)
            db = SessionLocal()
            try:
                log_run(db, "signal", "error", "No curated data available for 1d")
            finally:
                db.close()
            return
        
        if df_1h is None or df_1h.empty:
            logger.warning("No 1h data available, using 1d data as fallback")
            df_1h = df_1d
        
        payload = generate_signal(df_1h, df_1d)
        duration = time.time() - start_time
        
        logger.info(
            f"Signal generated: {payload['signal']} (confidence: {payload['confidence']}%)",
            extra={"signal": payload["signal"], "confidence": payload["confidence"], "duration": duration}
        )
        
        record_signal_generation(duration, True)
        db = SessionLocal()
        try:
            # Analysis will be generated in create_recommendation if not present
            create_recommendation(db, payload)
            log_run(db, "signal", "success")
        finally:
            db.close()
    except ValueError as e:
        duration = time.time() - start_time
        reason = "ValueError"
        logger.error(f"Signal generation ValueError: {str(e)}", exc_info=True)
        record_signal_generation(duration, False, reason)
        db = SessionLocal()
        try:
            log_run(db, "signal", "error", f"ValueError: {str(e)}")
        finally:
            db.close()
    except KeyError as e:
        duration = time.time() - start_time
        reason = "KeyError"
        logger.error(f"Signal generation KeyError: {str(e)}", exc_info=True)
        record_signal_generation(duration, False, reason)
        db = SessionLocal()
        try:
            log_run(db, "signal", "error", f"KeyError: {str(e)}")
        finally:
            db.close()
    except Exception as e:
        duration = time.time() - start_time
        reason = type(e).__name__
        logger.error(f"Signal generation failed: {reason}", exc_info=True, extra={"error": str(e)})
        record_signal_generation(duration, False, reason)
        db = SessionLocal()
        try:
            log_run(db, "signal", "error", str(e))
        finally:
            db.close()


@app.on_event("startup")
async def on_startup():
    # Schedule ingestion per cadence
    scheduler.add_job(job_ingest_all, "interval", minutes=15, id="ingest_all")
    # Daily signal at configured time
    hh, mm = [int(x) for x in settings.RECOMMENDATION_UPDATE_TIME.split(":")]
    scheduler.add_job(job_generate_signal, "cron", hour=hh, minute=mm, id="generate_signal_daily")
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)

