"""Test script to verify zero stop_loss_distance diagnostics in backtest engine."""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any
from app.backtesting.engine import BacktestEngine, StrategyProtocol


class TestStrategyWithZeroStopLoss(StrategyProtocol):
    """Test strategy that generates enter signals with stop_loss_distance=0."""
    
    def __init__(self):
        self.bar_count = 0
    
    def on_bar(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate enter signal with zero stop_loss_distance."""
        self.bar_count += 1
        
        # Generate enter signal on first few bars with invalid stop loss
        if self.bar_count <= 3:
            bar = context.get("bar", {})
            current_price = float(bar.get("close", 50000.0))
            
            # Signal with stop_loss_distance=0 (entry_price == stop_loss)
            return {
                "action": "enter",
                "side": "BUY",
                "entry_price": current_price,
                "stop_loss": current_price,  # Same as entry = zero distance
                "take_profit": current_price * 1.05,
            }
        
        # After that, generate hold signals
        return {"action": "hold"}


async def test_zero_stop_loss_diagnostics():
    """Test that zero stop_loss_distance is properly diagnosed."""
    print("=" * 80)
    print("Testing zero stop_loss_distance diagnostics")
    print("=" * 80)
    
    # Create synthetic data
    start_date = datetime(2024, 1, 1, tzinfo=pd.UTC)
    end_date = start_date + timedelta(days=5)
    
    # Generate hourly data
    dates_1h = pd.date_range(start_date, end_date, freq="1h", tz="UTC")
    np.random.seed(42)
    base_price = 50000.0
    prices = base_price + np.cumsum(np.random.randn(len(dates_1h)) * 100)
    
    df_1h = pd.DataFrame({
        "timestamp": dates_1h,
        "open": prices + np.random.uniform(-50, 50, len(dates_1h)),
        "high": prices + np.abs(np.random.uniform(50, 150, len(dates_1h))),
        "low": prices - np.abs(np.random.uniform(50, 150, len(dates_1h))),
        "close": prices,
        "volume": np.random.uniform(100, 1000, len(dates_1h)),
    }).set_index("timestamp")
    
    # Generate daily data (simplified, just use hourly aggregated)
    dates_1d = pd.date_range(start_date, end_date, freq="1d", tz="UTC")
    df_1d = pd.DataFrame({
        "timestamp": dates_1d,
        "open": [df_1h.loc[df_1h.index.date == d.date(), "open"].iloc[0] if len(df_1h.loc[df_1h.index.date == d.date()]) > 0 else base_price for d in dates_1d],
        "high": [df_1h.loc[df_1h.index.date == d.date(), "high"].max() if len(df_1h.loc[df_1h.index.date == d.date()]) > 0 else base_price * 1.01 for d in dates_1d],
        "low": [df_1h.loc[df_1h.index.date == d.date(), "low"].min() if len(df_1h.loc[df_1h.index.date == d.date()]) > 0 else base_price * 0.99 for d in dates_1d],
        "close": [df_1h.loc[df_1h.index.date == d.date(), "close"].iloc[-1] if len(df_1h.loc[df_1h.index.date == d.date()]) > 0 else base_price for d in dates_1d],
        "volume": np.random.uniform(1000, 5000, len(dates_1d)),
    }).set_index("timestamp")
    
    # Create strategy
    strategy = TestStrategyWithZeroStopLoss()
    
    # Create engine
    engine = BacktestEngine(
        commission_rate=0.001,
        slippage_model="fixed",
        fixed_slippage_bps=5.0,
        use_orderbook=False,
    )
    
    # Run backtest
    print(f"\nRunning backtest from {start_date} to {end_date}")
    print(f"Data points: {len(df_1h)} hourly, {len(df_1d)} daily")
    
    # Mock the data loading to use our synthetic data
    original_load = engine._load_candle_series
    
    async def mock_load_candle_series(request):
        """Mock data loader to return synthetic data."""
        from app.backtesting.engine import CandleSeries
        if request.timeframe == "1h":
            return CandleSeries(
                symbol=request.instrument,
                timeframe=request.timeframe,
                data=df_1h.loc[request.start_date:request.end_date].copy(),
            )
        else:
            return CandleSeries(
                symbol=request.instrument,
                timeframe=request.timeframe,
                data=df_1d.loc[request.start_date:request.end_date].copy(),
            )
    
    engine._load_candle_series = mock_load_candle_series
    
    result = await engine.run_backtest(
        start_date=start_date,
        end_date=end_date,
        instrument="BTCUSDT",
        timeframe="1h",
        strategy=strategy,
        initial_capital=10000.0,
    )
    
    # Verify results
    print("\n" + "=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)
    print(f"Total trades: {len(result.get('trades', []))}")
    print(f"Final capital: {result.get('final_capital', 0):.2f}")
    
    # Check no_trade_diagnostics
    no_trade_diagnostics = result.get("no_trade_diagnostics")
    if no_trade_diagnostics:
        print("\n" + "=" * 80)
        print("NO TRADE DIAGNOSTICS")
        print("=" * 80)
        print(f"Root cause: {no_trade_diagnostics.get('root_cause')}")
        print(f"Reason: {no_trade_diagnostics.get('reason')}")
        print(f"Signals with zero size: {no_trade_diagnostics.get('signals_with_zero_size', 0)}")
        print(f"Invalid stop loss count: {no_trade_diagnostics.get('invalid_stop_loss_count', 0)}")
        print(f"Rejected orders count: {no_trade_diagnostics.get('rejected_orders_count', 0)}")
        
        # Check signals_with_zero_size_details
        zero_size_details = no_trade_diagnostics.get("signals_with_zero_size_details", [])
        if zero_size_details:
            print(f"\nZero size signal details ({len(zero_size_details)}):")
            for i, detail in enumerate(zero_size_details[:5], 1):  # Show first 5
                print(f"  {i}. Timestamp: {detail.get('timestamp')}")
                print(f"     Entry price: {detail.get('entry_price')}")
                print(f"     Stop loss: {detail.get('stop_loss')}")
                print(f"     Stop loss distance: {detail.get('stop_loss_distance')}")
                print(f"     Rejection reason: {detail.get('rejection_reason')}")
                print(f"     Equity: {detail.get('equity')}")
                print(f"     Drawdown: {detail.get('drawdown')}")
        
        # Check rejected orders
        rejected_orders = no_trade_diagnostics.get("rejected_orders", [])
        if rejected_orders:
            print(f"\nRejected orders ({len(rejected_orders)}):")
            for i, order in enumerate(rejected_orders[:5], 1):  # Show first 5
                print(f"  {i}. Timestamp: {order.get('timestamp')}")
                print(f"     Side: {order.get('order_side')}")
                print(f"     Qty: {order.get('order_qty')}")
                print(f"     Status: {order.get('status')}")
                print(f"     Fill ratio: {order.get('fill_ratio')}")
        
        # Verify expected behavior
        print("\n" + "=" * 80)
        print("VERIFICATION")
        print("=" * 80)
        
        root_cause = no_trade_diagnostics.get("root_cause")
        invalid_stop_loss_count = no_trade_diagnostics.get("invalid_stop_loss_count", 0)
        
        if root_cause == "invalid_stop_loss":
            print("✓ PASS: Root cause correctly identified as 'invalid_stop_loss'")
        elif root_cause == "enter_signals_zero_size":
            print("✓ PASS: Root cause identified as 'enter_signals_zero_size'")
        else:
            print(f"✗ FAIL: Unexpected root cause: {root_cause}")
        
        if invalid_stop_loss_count > 0:
            print(f"✓ PASS: Found {invalid_stop_loss_count} signals with invalid stop loss")
        else:
            print("✗ FAIL: No invalid stop loss signals detected")
        
        if len(result.get("trades", [])) == 0:
            print("✓ PASS: No trades executed (as expected with invalid stop loss)")
        else:
            print(f"✗ FAIL: Unexpected trades executed: {len(result.get('trades', []))}")
        
        if zero_size_details:
            print(f"✓ PASS: Zero size details captured with timestamps ({len(zero_size_details)} records)")
        else:
            print("✗ FAIL: No zero size details captured")
    else:
        print("\n✗ FAIL: No no_trade_diagnostics found (expected when trade_count=0)")
    
    print("\n" + "=" * 80)
    print("Test completed")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_zero_stop_loss_diagnostics())

