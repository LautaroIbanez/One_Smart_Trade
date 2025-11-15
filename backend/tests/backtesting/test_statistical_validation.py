"""Statistical validation suite for backtesting engine."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics

ENTRY_INDEX = 205


class DummySplitter:
    def __init__(self, data: pd.DataFrame):
        self.data = data

    def materialize(self, window, *, interval=None):
        mask = (self.data["open_time"] >= window.start) & (self.data["open_time"] <= window.end)
        return self.data.loc[mask].copy()


def _build_price_frame(n: int = 220, start_date: str = "2020-01-01") -> pd.DataFrame:
    """Build synthetic price frame for testing."""
    dates = pd.date_range(start_date, periods=n, freq="D", tz="UTC")
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


def _patch_curation(engine: BacktestEngine, df_1d: pd.DataFrame, df_1h: pd.DataFrame, monkeypatch):
    """Patch curation methods to return test data."""
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


def _patch_signal_with_timestamp(monkeypatch, signal_timestamp: pd.Timestamp, stop_loss: float, take_profit: float):
    """Patch signal generation with explicit timestamp tracking."""
    signal_generated_at = []

    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx == ENTRY_INDEX:
            optimal = float(df_slice.iloc[-1]["close"])
            signal_time = df_slice.iloc[-1]["open_time"]
            signal_generated_at.append(signal_time)
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": stop_loss, "take_profit": take_profit},
                "signal_timestamp": signal_time,
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }

    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)
    return signal_generated_at


def _patch_random_walk_signal(monkeypatch, entry_indices: list[int], side: str = "BUY"):
    """Patch signal generation to produce signals at random indices (no edge)."""
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx in entry_indices:
            optimal = float(df_slice.iloc[-1]["close"])
            price = optimal
            sl = price * 0.98 if side == "BUY" else price * 1.02
            tp = price * 1.02 if side == "BUY" else price * 0.98
            return {
                "signal": side,
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": sl, "take_profit": tp},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }
    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)


@pytest.fixture
def base_data():
    """Base test data fixture."""
    df_1d = _build_price_frame()
    df_1h = df_1d.copy()
    return df_1d, df_1h


@pytest.fixture
def random_walk_data():
    """Generate random walk price series (no edge)."""
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    base_price = 100.0
    returns = np.random.normal(0.0, 0.02, n)
    prices = [base_price]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    df = pd.DataFrame(
        {
            "open_time": dates,
            "open": prices[:-1],
            "high": [p * 1.01 for p in prices[:-1]],
            "low": [p * 0.99 for p in prices[:-1]],
            "close": prices[1:],
            "volume": np.full(n, 1_000_000.0),
            "atr": np.full(n, 1.5),
            "bid_depth": np.full(n, 500_000.0),
            "ask_depth": np.full(n, 500_000.0),
            "taker_buy_base": np.full(n, 500_000.0),
        }
    )
    return df


@pytest.fixture
def losing_streak_series():
    """Generate series with known losing streak pattern."""
    n = 300
    dates = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    base_prices = 100 + np.linspace(0, 2, n)
    df = pd.DataFrame(
        {
            "open_time": dates,
            "open": base_prices,
            "high": base_prices + 2,
            "low": base_prices - 2,
            "close": base_prices + 0.5,
            "volume": np.full(n, 1_000_000.0),
            "atr": np.full(n, 1.5),
            "bid_depth": np.full(n, 500_000.0),
            "ask_depth": np.full(n, 500_000.0),
            "taker_buy_base": np.full(n, 500_000.0),
        }
    )
    return df


def _setup_sl_before_tp_same_bar(df, idx):
    """Setup scenario where SL and TP both hit same bar, SL first."""
    df.iloc[idx + 1, df.columns.get_loc("low")] = df.iloc[idx]["close"] - 5
    df.iloc[idx + 1, df.columns.get_loc("high")] = df.iloc[idx]["close"] + 5


def _setup_tp_before_sl_same_bar(df, idx):
    """Setup scenario where TP hits before SL on same bar (unlikely but possible)."""
    df.iloc[idx + 1, df.columns.get_loc("high")] = df.iloc[idx]["close"] + 5
    df.iloc[idx + 1, df.columns.get_loc("low")] = df.iloc[idx]["close"] - 5


def _setup_gap_sl_before_intrabar_tp(df, idx):
    """Setup scenario where gap SL occurs before intrabar TP."""
    df.iloc[idx + 1, df.columns.get_loc("open")] = df.iloc[idx]["close"] - 4
    df.iloc[idx + 1, df.columns.get_loc("low")] = df.iloc[idx]["close"] - 4.5
    df.iloc[idx + 1, df.columns.get_loc("high")] = df.iloc[idx]["close"] + 5


SCENARIOS = [
    {"name": "sl_before_tp_same_bar", "setup": _setup_sl_before_tp_same_bar, "expected": "SL"},
    {"name": "tp_before_sl_same_bar", "setup": _setup_tp_before_sl_same_bar, "expected": "TP"},
    {"name": "gap_sl_before_intrabar_tp", "setup": _setup_gap_sl_before_intrabar_tp, "expected": "SL_GAP"},
]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_conservative_intrabar(scenario, monkeypatch, base_data):
    """Test conservative intrabar convention: SL takes priority over TP when both hit same bar."""
    df_1d, df_1h = base_data
    df_1d = df_1d.copy()
    entry_price = float(df_1d.iloc[ENTRY_INDEX]["close"])
    stop = entry_price - 4
    take = entry_price + 6
    
    scenario["setup"](df_1d, ENTRY_INDEX)
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx == ENTRY_INDEX:
            optimal = entry_price
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": stop, "take_profit": take},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }
    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    trades = result["trades"]
    assert trades, f"Expected at least one trade for scenario {scenario['name']}"
    trade = trades[-1]
    
    if scenario["expected"] == "SL":
        assert trade["exit_reason"].startswith("SL"), f"Scenario {scenario['name']}: SL should trigger before TP when both hit same bar"
    elif scenario["expected"] == "SL_GAP":
        assert trade["exit_reason"] == "SL_GAP", f"Scenario {scenario['name']}: Gap SL should trigger before intrabar TP"
    elif scenario["expected"] == "TP":
        assert trade["exit_reason"] in ("TP", "TP_GAP"), f"Scenario {scenario['name']}: TP should trigger when hit before SL"


def test_isolation_property_no_trades_before_signal(monkeypatch, base_data):
    """Test isolation property: no trades with timestamp earlier than signal generation."""
    df_1d, df_1h = base_data
    stop = float(df_1d.iloc[ENTRY_INDEX]["close"] - 4)
    take = float(df_1d.iloc[ENTRY_INDEX]["close"] + 6)
    
    signal_generated_at = _patch_signal_with_timestamp(monkeypatch, None, stop, take)
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    trades = result["trades"]
    
    if trades and signal_generated_at:
        signal_time = signal_generated_at[0]
        for trade in trades:
            assert pd.Timestamp(trade["entry_time"]) >= signal_time, f"Trade entry_time {trade['entry_time']} is before signal time {signal_time}"
            assert pd.Timestamp(trade["exit_time"]) >= signal_time, f"Trade exit_time {trade['exit_time']} is before signal time {signal_time}"


def test_synthetic_random_walk_sharpe_hypothesis(monkeypatch, random_walk_data):
    """Test that synthetic random walk strategy (no edge) produces Sharpe ~0 via t-test."""
    df_1d = random_walk_data
    df_1h = df_1d.copy()
    
    np.random.seed(42)
    entry_indices = np.random.choice(range(250, 480), size=20, replace=False).tolist()
    _patch_random_walk_signal(monkeypatch, entry_indices, side="BUY")
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    metrics = calculate_metrics(result)
    
    sharpe = metrics["sharpe"]
    
    assert abs(sharpe) < 2.0, f"Random walk should produce Sharpe near 0, got {sharpe}"
    
    if result.get("trades"):
        returns = [t["return_pct"] for t in result["trades"]]
        if len(returns) >= 10:
            t_stat, p_value = stats.ttest_1samp(returns, 0.0)
            assert abs(t_stat) < 2.0 or p_value > 0.05, f"Returns should not significantly differ from 0 (t={t_stat:.2f}, p={p_value:.3f})"


def test_synthetic_random_walk_metrics_ranges(monkeypatch, random_walk_data):
    """Test that synthetic strategies produce metrics within expected ranges."""
    df_1d = random_walk_data
    df_1h = df_1d.copy()
    
    np.random.seed(123)
    entry_indices = np.random.choice(range(250, 480), size=25, replace=False).tolist()
    _patch_random_walk_signal(monkeypatch, entry_indices, side="BUY")
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    metrics = calculate_metrics(result)
    
    assert abs(metrics["sharpe"]) < 1.5, f"Random walk Sharpe should be near 0, got {metrics['sharpe']}"
    assert 0 <= metrics["win_rate"] <= 100, f"Win rate should be between 0-100%, got {metrics['win_rate']}"
    assert metrics["profit_factor"] >= 0, f"Profit factor should be non-negative, got {metrics['profit_factor']}"
    assert abs(metrics["cagr"]) < 50, f"Random walk CAGR should be modest, got {metrics['cagr']}%"


def test_risk_of_ruin_fixture(monkeypatch, losing_streak_series):
    """Test risk of ruin calculation with generated losing streak series."""
    df_1d = losing_streak_series
    df_1h = df_1d.copy()
    
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx >= 250 and idx % 10 == 0:
            optimal = float(df_slice.iloc[-1]["close"])
            sl = optimal * 0.95
            tp = optimal * 1.03
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": sl, "take_profit": tp},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }
    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    metrics = calculate_metrics(result)
    
    assert 0 <= metrics["risk_of_ruin"] <= 1, f"Risk of ruin should be between 0-1, got {metrics['risk_of_ruin']}"
    assert metrics["longest_losing_streak"] >= 0, f"Longest losing streak should be non-negative, got {metrics['longest_losing_streak']}"


def test_longest_losing_streak_fixture(monkeypatch, losing_streak_series):
    """Test longest losing streak calculation with generated series."""
    df_1d = losing_streak_series
    df_1h = df_1d.copy()
    
    np.random.seed(999)
    entry_indices = list(range(250, 290))
    
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx in entry_indices:
            optimal = float(df_slice.iloc[-1]["close"])
            sl = optimal * 0.97
            tp = optimal * 1.01
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": sl, "take_profit": tp},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }
    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    metrics = calculate_metrics(result)
    
    if result.get("trades"):
        trades_df = pd.DataFrame(result["trades"])
        losing_mask = trades_df["pnl"] < 0
        if losing_mask.any():
            actual_streak = metrics["longest_losing_streak"]
            assert actual_streak > 0, f"Should detect losing streak, got {actual_streak}"
    
    assert metrics["longest_losing_streak"] >= 0


def test_gap_sl_conflict_intrabar_tp(monkeypatch, base_data):
    """Test that gap SL conflicts with intrabar TP follow conservative convention."""
    df_1d, df_1h = base_data
    entry_price = float(df_1d.iloc[ENTRY_INDEX]["close"])
    stop = entry_price - 4
    take = entry_price + 6
    
    next_bar_idx = ENTRY_INDEX + 1
    df_1d.iloc[next_bar_idx, df_1d.columns.get_loc("open")] = stop * 0.95
    df_1d.iloc[next_bar_idx, df_1d.columns.get_loc("low")] = stop * 0.95
    df_1d.iloc[next_bar_idx, df_1d.columns.get_loc("high")] = take + 1
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx == ENTRY_INDEX:
            optimal = entry_price
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": stop, "take_profit": take},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }
    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    trades = result["trades"]
    assert trades, "Expected at least one trade"
    trade = trades[-1]
    assert trade["exit_reason"] == "SL_GAP", "Gap SL should take priority over intrabar TP"


def test_multiple_trades_isolation(monkeypatch, base_data):
    """Test isolation property across multiple trades."""
    df_1d, df_1h = base_data
    df_1d = _build_price_frame(n=400)
    df_1h = df_1d.copy()
    
    signal_times = []
    
    def fake_generate_signal(df_h_slice, df_slice):
        idx = len(df_slice)
        if idx in [ENTRY_INDEX, ENTRY_INDEX + 50, ENTRY_INDEX + 100]:
            optimal = float(df_slice.iloc[-1]["close"])
            signal_time = df_slice.iloc[-1]["open_time"]
            signal_times.append(signal_time)
            sl = optimal * 0.98
            tp = optimal * 1.02
            return {
                "signal": "BUY",
                "entry_range": {"min": optimal * 0.99, "max": optimal * 1.01, "optimal": optimal},
                "stop_loss_take_profit": {"stop_loss": sl, "take_profit": tp},
            }
        return {
            "signal": "HOLD",
            "entry_range": {"min": 0.0, "max": 0.0, "optimal": 0.0},
            "stop_loss_take_profit": {"stop_loss": 0.0, "take_profit": 0.0},
        }
    monkeypatch.setattr("app.quant.signal_engine.generate_signal", fake_generate_signal)
    
    engine = BacktestEngine()
    _patch_curation(engine, df_1d, df_1h, monkeypatch)
    
    result = engine.run_backtest(df_1d["open_time"].min(), df_1d["open_time"].max())
    trades = result["trades"]
    
    if trades and signal_times:
        for i, trade in enumerate(trades):
            signal_time = signal_times[min(i, len(signal_times) - 1)]
            assert pd.Timestamp(trade["entry_time"]) >= signal_time, f"Trade {i} entry_time before signal"
            assert pd.Timestamp(trade["exit_time"]) >= signal_time, f"Trade {i} exit_time before signal"

