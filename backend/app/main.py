"""FastAPI application entry point."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import diagnostics, market, performance, recommendation
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging import setup_logging
from app.data.curation import DataCuration
from app.data.ingestion import DataIngestion
from app.db.crud import log_run
from app.middleware.exception_handler import ExceptionHandlerMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.observability.metrics import RequestMetricsMiddleware, metrics_router

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


@app.on_event("startup")
async def on_startup():
    # Jobs are already scheduled via decorators
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)

