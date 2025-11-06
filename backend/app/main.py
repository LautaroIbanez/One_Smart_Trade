"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
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
    di = DataIngestion()
    try:
        await di.ingest_all_timeframes()
        with SessionLocal() as db:
            log_run(db, "ingestion", "success")
    except Exception as e:
        with SessionLocal() as db:
            log_run(db, "ingestion", "error", str(e))


async def job_generate_signal():
    dc = DataCuration()
    df_1d = dc.get_latest_curated("1d")
    df_1h = dc.get_latest_curated("1h")
    if df_1d is None or df_1h is None or df_1d.empty or df_1h.empty:
        return
    payload = generate_signal(df_1h, df_1d)
    with SessionLocal() as db:
        create_recommendation(db, payload)
        log_run(db, "signal", "success")


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

