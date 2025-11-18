from pathlib import Path
import sys

import pandas as pd
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from app.analytics.trade_efficiency import TradeEfficiencyAnalyzer
from app.backtesting.trade_analytics import TradeAnalyticsRepository, TradeAnalyticsRecord


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> TradeAnalyticsRepository:
    repo = TradeAnalyticsRepository(base_path=tmp_path)
    records = [
        TradeAnalyticsRecord(
            run_id="test",
            trade_id=f"t{i}",
            symbol="BTCUSDT",
            side="BUY",
            opened_at=pd.Timestamp("2024-01-01"),
            closed_at=pd.Timestamp("2024-01-02"),
            mae=5 + i,
            mfe=15 + i,
            mae_pct=1 + i,
            mfe_pct=3 + i,
        )
        for i in range(5)
    ]
    repo.save_records(records, filename="sample")
    return repo


def _basic_signal(risk: float = 10.0, reward: float = 20.0) -> dict:
    entry = 100.0
    return {
        "symbol": "BTCUSDT",
        "entry_range": {"optimal": entry},
        "stop_loss_take_profit": {
            "stop_loss": entry - risk,
            "take_profit": entry + reward,
        },
        "factors": {},
    }


def test_evaluator_accepts_when_mae_within_risk(tmp_repo: TradeAnalyticsRepository):
    analyzer = TradeEfficiencyAnalyzer(repository=tmp_repo)
    signal = _basic_signal(risk=20.0)

    evaluation = analyzer.evaluate_signal(signal, symbol="BTCUSDT")
    assert evaluation.accepted is True
    assert "MAE" in evaluation.summary or "RR" in evaluation.summary


def test_evaluator_rejects_when_mae_exceeds_risk(tmp_repo: TradeAnalyticsRepository):
    analyzer = TradeEfficiencyAnalyzer(repository=tmp_repo)
    signal = _basic_signal(risk=1.0)

    evaluation = analyzer.evaluate_signal(signal, symbol="BTCUSDT")
    assert evaluation.accepted is False
    assert any("MAE" in reason for reason in evaluation.reasons)


def test_evaluator_rejects_when_rr_too_low(tmp_repo: TradeAnalyticsRepository, monkeypatch: pytest.MonkeyPatch):
    analyzer = TradeEfficiencyAnalyzer(repository=tmp_repo, rr_floor=2.0)
    signal = _basic_signal(risk=10.0, reward=5.0)

    evaluation = analyzer.evaluate_signal(signal, symbol="BTCUSDT")
    assert evaluation.accepted is False
    assert any("RR esperado" in r for r in evaluation.reasons)

