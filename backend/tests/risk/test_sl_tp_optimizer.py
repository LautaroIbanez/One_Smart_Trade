import json
from pathlib import Path

import pandas as pd
import pytest

from app.risk import StopLossTakeProfitOptimizer
from app.services.strategy_service import StrategyService


def _sample_trades(num_days: int = 260) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=num_days, freq="D", tz="UTC")
    data = {
        "timestamp": timestamps,
        "symbol": ["BTCUSDT"] * num_days,
        "entry_price": 30000 + pd.Series(range(num_days)) * 5,
        "direction": ["BUY" if i % 3 else "SELL" for i in range(num_days)],
        "atr": pd.Series(200 + (i % 20) for i in range(num_days)),
        "mae": pd.Series(50 + (i % 30) for i in range(num_days)),
        "mfe": pd.Series(80 + (i % 40) for i in range(num_days)),
        "pnl": pd.Series((-1) ** i * 0.5 for i in range(num_days)),
    }
    df = pd.DataFrame(data)
    df["regime"] = ["calm" if i % 2 == 0 else "stress" for i in range(num_days)]
    return df


def test_optimizer_persists_configs(tmp_path: Path) -> None:
    trades = _sample_trades()
    optimizer = StopLossTakeProfitOptimizer(artifacts_dir=tmp_path / "sl_tp")
    configs = optimizer.optimize(
        trades,
        symbol="BTCUSDT",
        search_space={
            "atr_multiplier_sl": [1.0, 1.5],
            "atr_multiplier_tp": [2.0],
            "tp_ratio": [1.2, 1.5],
        },
    )
    assert configs, "Expected configs per regime"
    for regime in configs:
        path = tmp_path / "sl_tp" / "BTCUSDT" / regime / "config.json"
        assert path.exists(), f"Missing artifact for regime {regime}"
        payload = json.loads(path.read_text())
        assert "best_params" in payload
        assert payload["rr_threshold"] >= optimizer.rr_floor


class _DummyOptimizer:
    def load_config(self, symbol: str, regime: str, **_: object) -> dict[str, object]:
        return {
            "symbol": symbol,
            "regime": regime,
            "rr_threshold": 1.2,
            "best_params": {
                "atr_multiplier_sl": 1.5,
                "atr_multiplier_tp": 2.0,
                "tp_ratio": 1.8,
            },
            "metadata": {"updated_at": "2024-01-01T00:00:00+00:00"},
        }


class _DummyOrderbookRepo:
    async def load(self, *args, **kwargs):  # noqa: ANN001, ANN003
        return []


@pytest.mark.asyncio
async def test_strategy_service_applies_optimizer(monkeypatch):
    service = StrategyService(
        optimizer=_DummyOptimizer(),
        orderbook_repo=_DummyOrderbookRepo(),
    )

    async def _no_liquidity(*args, **kwargs):
        return False

    monkeypatch.setattr(service, "_detect_regime", lambda df: "calm")
    monkeypatch.setattr(service, "_stop_in_liquidity_zone", _no_liquidity)

    signal = {"signal": "BUY", "entry_range": {"optimal": 100.0}}
    market_df = pd.DataFrame(
        {
            "close": [100, 101, 102],
            "atr_14": [5.0, 5.1, 5.2],
            "volume": [1_000, 1_100, 1_200],
        }
    )

    enriched = await service.apply_sl_tp_policy(signal, market_df)
    sl_tp = enriched.get("stop_loss_take_profit")
    assert sl_tp is not None
    assert sl_tp["stop_loss"] < sl_tp["take_profit"]
    assert enriched["risk_metrics"]["risk_reward_ratio"] > 0

