import numpy as np
import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics

ENTRY_INDEX = 205


class DummySplitter:
    def __init__(self, data: pd.DataFrame):
        self.data = data

    def materialize(self, window, *, interval=None):
        mask = (self.data["open_time"] >= window.start) & (self.data["open_time"] <= window.end)
        return self.data.loc[mask].copy()


def _build_price_frame() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=220, freq="D", tz="UTC")
    base_prices = 100 + np.linspace(0, 5, len(dates))
    df = pd.DataFrame(
        {
            "open_time": dates,
            "open": base_prices,
            "high": base_prices + 2,
            "low": base_prices - 2,
            "close": base_prices + 0.5,
            "volume": np.full(len(dates), 1_000_000.0),
            "atr": np.full(len(dates), 1.5),
            "bid_depth": np.full(len(dates), 500_000.0),
            "ask_depth": np.full(len(dates), 500_000.0),
            "taker_buy_base": np.full(len(dates), 500_000.0),
        }
    )
    return df


@pytest.fixture
def base_data():
    df_1d = _build_price_frame()
    df_1h = df_1d.copy()
    return df_1d, df_1h


def _patch_curation(engine: BacktestEngine, df_1d: pd.DataFrame, df_1h: pd.DataFrame, monkeypatch):
    monkeypatch.setattr(
        engine.curation,
        "get_historical_curated",
        lambda interval, **kwargs: df_1h if interval == "1h" else df_1d,
    )
    monkeypatch.setattr(
        engine.curation,
        "get_latest_curated",
        lambda interval: df_1h if interval == "1h" else df_1d,
    )
    engine._splitter = DummySplitter(df_1d)


def _patch_signal(monkeypatch, stop_loss: float, take_profit: float):
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx == ENTRY_INDEX:
            optimal = float(df_slice.iloc[-1]["close"])
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": stop_loss, "take_profit": take_profit},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }

    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)


def test_conservative_intrabar_sl_before_tp(monkeypatch, base_data):
    df_1d, df_1h = base_data
    stop = float(df_1d.iloc[ENTRY_INDEX]["close"] - 4)
    take = float(df_1d.iloc[ENTRY_INDEX]["close"] + 6)
    next_bar = df_1d.iloc[ENTRY_INDEX + 1]
    df_1d.iloc[ENTRY_INDEX + 1, df_1d.columns.get_loc("low")] = stop - 2
    df_1d.iloc[ENTRY_INDEX + 1, df_1d.columns.get_loc("high")] = take + 2
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    _patch_signal(monkeypatch, stop, take)

    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    trades = result["trades"]
    assert trades, "Expected at least one trade"
    trade = trades[-1]
    assert trade["exit_reason"].startswith("SL"), "Stop loss should trigger before take profit intrabar"
    assert trade["exit_time"] >= trade["entry_time"]


def test_gap_exit_records_penalty(monkeypatch, base_data):
    df_1d, df_1h = base_data
    stop = float(df_1d.iloc[ENTRY_INDEX]["close"] - 3)
    take = float(df_1d.iloc[ENTRY_INDEX]["close"] + 6)
    df_1d.iloc[ENTRY_INDEX + 1, df_1d.columns.get_loc("open")] = stop * 0.9
    df_1d.iloc[ENTRY_INDEX + 1, df_1d.columns.get_loc("low")] = stop * 0.9
    df_1d.iloc[ENTRY_INDEX + 1, df_1d.columns.get_loc("high")] = take
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    _patch_signal(monkeypatch, stop, take)

    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    trades = result["trades"]
    assert trades, "Expected at least one trade"
    trade = trades[-1]
    assert trade["exit_reason"] == "SL_GAP"
    assert result["gap_events"], "Gap events should be recorded"
    gap_event = result["gap_events"][-1]
    assert gap_event["type"] == "SL_GAP"
    assert gap_event["exec_price"] < stop


def test_random_walk_metrics_behaviour():
    np.random.seed(42)
    n = 500
    return_pct = np.random.normal(0.0, 1.0, n)
    capital = 10_000.0
    equity = [capital]
    trades = []
    dates = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    for idx, r in enumerate(return_pct):
        pnl = capital * (r / 100)
        capital += pnl
        equity.append(capital)
        trades.append(
            {
                "entry_time": dates[idx],
                "exit_time": dates[idx],
                "pnl": pnl,
                "return_pct": r,
            }
        )
    backtest_result = {
        "trades": trades,
        "equity_curve": equity,
        "initial_capital": 10_000.0,
        "final_capital": capital,
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
    }
    metrics = calculate_metrics(backtest_result)
    assert abs(metrics["sharpe"]) < 1.5
    assert 0 <= metrics["risk_of_ruin"] <= 1
    assert metrics["longest_losing_streak"] >= 0



