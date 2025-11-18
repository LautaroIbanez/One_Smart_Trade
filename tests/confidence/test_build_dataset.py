from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.dataset as pa_ds
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from scripts.confidence.build_dataset import ConfidenceDatasetBuilder, DatasetFilters

from app.core.database import Base
from app.db.models import SignalOutcomeORM


@pytest.fixture()
def sqlite_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path/'confidence.db'}")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _insert_signal(
    session: Session,
    *,
    strategy: str,
    regime: str | None,
    vol_bucket: str | None,
    confidence: float,
    pnl_pct: float,
    outcome: str,
    minutes: int,
) -> None:
    session.add(
        SignalOutcomeORM(
            strategy_id=strategy,
            signal="BUY",
            decision_timestamp=datetime.utcnow(),
            confidence_raw=confidence,
            market_regime=regime,
            vol_bucket=vol_bucket,
            horizon_minutes=minutes,
            pnl_pct=pnl_pct,
            outcome=outcome,
        )
    )
    session.commit()


def test_build_dataset_produces_partitioned_parquet(sqlite_session: Session, tmp_path: Path) -> None:
    _insert_signal(sqlite_session, strategy="strat_a", regime="calm", vol_bucket="low", confidence=65.0, pnl_pct=4.0, outcome="win", minutes=1440)
    _insert_signal(sqlite_session, strategy="strat_b", regime="stress", vol_bucket="high", confidence=30.0, pnl_pct=-2.0, outcome="loss", minutes=720)

    builder = ConfidenceDatasetBuilder(sqlite_session, output_dir=tmp_path / "out", manifest_path=tmp_path / "datasets.json")
    metadata = builder.build(DatasetFilters())

    assert (tmp_path / "datasets.json").exists()
    manifest = json.loads((tmp_path / "datasets.json").read_text(encoding="utf-8"))
    assert manifest["datasets"], "Manifest should include at least one dataset entry"
    assert metadata["rows"] == 2

    dataset_dir = Path(metadata["path"])
    assert dataset_dir.exists()

    dataset = pa_ds.dataset(str(dataset_dir), format="parquet")
    df = dataset.to_table().to_pandas()
    assert sorted(df["market_regime"].unique()) == ["calm", "stress"]
    assert {"hit", "confidence_norm", "horizon_return_pct"}.issubset(df.columns)


def test_normalize_dataframe_derives_hit_using_pnl(sqlite_session: Session, tmp_path: Path) -> None:
    now = datetime.utcnow()
    rows = [
        SignalOutcomeORM(
            id=1,
            strategy_id="s1",
            signal="BUY",
            decision_timestamp=now,
            confidence_raw=55.0,
            market_regime="balanced",
            vol_bucket=None,
            horizon_minutes=60,
            pnl_pct=None,
            outcome=None,
        ),
        SignalOutcomeORM(
            id=2,
            strategy_id="s2",
            signal="SELL",
            decision_timestamp=now + timedelta(minutes=10),
            confidence_raw=80.0,
            market_regime=None,
            vol_bucket="high",
            horizon_minutes=180,
            pnl_pct=-0.5,
            outcome="loss",
        ),
    ]

    builder = ConfidenceDatasetBuilder(sqlite_session, output_dir=tmp_path / "o", manifest_path=tmp_path / "m.json")
    df = builder._normalize_dataframe(rows)

    assert list(df["hit"]) == [1, 0], "Hit debe considerar pnl >= 0 aun sin outcome"
    assert df.loc[0, "vol_bucket"] == "unknown"
    assert df.loc[1, "vol_bucket"] == "high"
    assert df.loc[0, "confidence_norm"] == pytest.approx(0.55)
    assert df.loc[1, "confidence_calibrated_norm"] == pytest.approx(0.8)

