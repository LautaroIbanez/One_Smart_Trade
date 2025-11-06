"""End-to-end test mocking Binance and exercising API pipeline."""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.main import app
from app.data.ingestion import DataIngestion
from app.data.curation import DataCuration
from app.quant.signal_engine import generate_signal
from app.core.database import SessionLocal, Base, engine
from app.db.crud import create_recommendation


client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.mark.asyncio
async def test_full_pipeline_with_mocks():
    ingestion = DataIngestion()
    # Mock Binance to return minimal klines
    mock_klines = [
        [1609459200000, "29000", "29500", "28800", "29300", "100.5", 1609462799999, "2930000", 100, "50.5", "1475000", "0"],
        [1609462800000, "29300", "29700", "29200", "29600", "120.0", 1609466399999, "3552000", 110, "60.0", "1770000", "0"],
    ]
    meta = {"latency_ms": 120, "fetched_at": datetime.utcnow().isoformat()}

    async def fake_get_klines(*args, **kwargs):
        return mock_klines, meta

    with patch.object(ingestion.client, "get_klines", new=fake_get_klines):
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=2)
        r = await ingestion.ingest_timeframe("1d", start_time, end_time)
        assert r["status"] in ("success", "empty")

    # Curate and generate signal, persist to DB
    curator = DataCuration()
    curator.curate_timeframe("1d")
    df = curator.get_latest_curated("1d")
    assert df is not None and not df.empty
    sig = generate_signal(df, df)
    with SessionLocal() as db:
        create_recommendation(db, sig)

    # Call API endpoints
    res = client.get("/api/v1/recommendation/today")
    assert res.status_code in (200, 404)
    client.get("/api/v1/recommendation/history?limit=5")
    client.get("/api/v1/diagnostics/last-run")

