import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd

APP_PATH = Path(__file__).resolve().parents[2] / "backend" / "app"


def _register_dependency_stubs() -> None:
    app_module = sys.modules.setdefault("app", types.ModuleType("app"))
    if not hasattr(app_module, "__path__"):
        app_module.__path__ = []  # type: ignore[attr-defined]

    data_module = sys.modules.setdefault("app.data", types.ModuleType("app.data"))
    data_module.__path__ = []  # type: ignore[attr-defined]
    setattr(app_module, "data", data_module)

    fill_model_module = types.ModuleType("app.data.fill_model")

    class FillModel:  # pragma: no cover - stub only
        def __call__(self, *_args: object, **_kwargs: object) -> None:
            return None

    class FillSimulator:  # pragma: no cover - stub only
        def simulate(self, *_args: object, **_kwargs: object) -> None:
            return None

    fill_model_module.FillModel = FillModel
    fill_model_module.FillSimulator = FillSimulator
    sys.modules.setdefault("app.data.fill_model", fill_model_module)
    setattr(data_module, "fill_model", fill_model_module)

    orderbook_module = types.ModuleType("app.data.orderbook")

    class OrderBookSnapshot:  # pragma: no cover - stub only
        best_bid: float | None = None
        best_ask: float | None = None

    orderbook_module.OrderBookSnapshot = OrderBookSnapshot
    sys.modules.setdefault("app.data.orderbook", orderbook_module)
    setattr(data_module, "orderbook", orderbook_module)

    backtesting_module = sys.modules.setdefault("app.backtesting", types.ModuleType("app.backtesting"))
    backtesting_module.__path__ = []  # type: ignore[attr-defined]
    setattr(app_module, "backtesting", backtesting_module)


def _load_module(module_name: str, relative_path: str):
    module_path = APP_PATH / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


_register_dependency_stubs()
_load_module("app.backtesting.order_types", "backtesting/order_types.py")
position_module = _load_module("app.backtesting.position", "backtesting/position.py")

Position = position_module.Position
PositionConfig = position_module.PositionConfig
PositionSide = position_module.PositionSide


def test_trailing_stop_hits_breakeven_and_trails():
    config = PositionConfig(
        risk_per_unit=5,
        reward_per_unit=10,
        trailing_stop=True,
        trailing_sl=3,
        breakeven_trigger=4,
    )
    position = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        config=config,
        initial_fill_price=100.0,
        initial_qty=1.0,
        opened_at=pd.Timestamp("2024-01-01T00:00:00Z"),
    )

    # Initial SL should be entry - risk (95)
    assert position.stop_loss == 95.0

    # Price moves favorably but not enough to trigger breakeven
    position.update_price(103.0, timestamp=pd.Timestamp("2024-01-01T01:00:00Z"))
    assert position.stop_loss == 95.0

    # Hit breakeven trigger (4 points)
    position.update_price(104.5, timestamp=pd.Timestamp("2024-01-01T02:00:00Z"))
    assert position.stop_loss == position.avg_entry

    # Strong move activates trailing stop (distance = 3)
    position.update_price(118.0, timestamp=pd.Timestamp("2024-01-01T03:00:00Z"))
    assert position.stop_loss == 115.0
    assert position.trailing_sl == 115.0
    analytics = position.get_trade_analytics()
    assert analytics["mfe"] == 18.0


def test_partial_take_profits_reduce_position_and_log_events():
    config = PositionConfig(
        risk_per_unit=5,
        reward_per_unit=10,
        trailing_stop=True,
        trailing_sl=4,
        breakeven_trigger=2,
        partial_take_profits=[
            {"price": 108.0, "qty_pct": 0.5},
            {"price": 115.0, "qty_pct": 0.5},
        ],
    )
    position = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        config=config,
        initial_fill_price=100.0,
        initial_qty=1.0,
        opened_at=pd.Timestamp("2024-01-01T00:00:00Z"),
    )

    # Drive MAE lower before moving up
    position.update_price(96.5, timestamp=pd.Timestamp("2024-01-01T00:30:00Z"))
    analytics = position.get_trade_analytics()
    assert analytics["mae"] == 3.5

    # Trigger first partial take profit
    events = position.update_price(109.0, timestamp=pd.Timestamp("2024-01-01T01:00:00Z"))
    assert len(events) == 1
    assert events[0]["partial_take_profit"] is True
    assert events[0]["closed_qty"] == 0.5
    assert position.size == 0.5

    # Trigger second partial, position should close
    events = position.update_price(116.0, timestamp=pd.Timestamp("2024-01-01T02:00:00Z"))
    assert events
    assert position.size == 0.0
    analytics = position.get_trade_analytics()
    assert analytics["mfe"] == 16.0


