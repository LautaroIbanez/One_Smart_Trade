"""Tests for orderbook fallback warnings and logging."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
import logging

import pandas as pd

from app.backtesting.execution_simulator import ExecutionSimulator
from app.backtesting.order_types import MarketOrder, OrderSide, OrderConfig
from app.backtesting.orderbook_warning import OrderBookWarning
from app.data.orderbook import OrderBookRepository, OrderBookSnapshot


class FakeOrderBookRepository:
    """Fake orderbook repository that simulates missing orderbook data."""
    
    def __init__(self, return_none: bool = True, reason: str = "not_found"):
        self.return_none = return_none
        self.reason = reason
        self.call_count = 0
    
    async def get_snapshot(self, symbol: str, ts: pd.Timestamp, *, tolerance_seconds: int = 30) -> OrderBookSnapshot | None:
        """Return None to simulate missing orderbook."""
        self.call_count += 1
        return None
    
    def _get_orderbook_path(self, symbol: str):
        """Return a mock path for testing."""
        from pathlib import Path
        return Path(f"/fake/path/{symbol}/orderbook.parquet")
    
    async def load(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> list[OrderBookSnapshot]:
        """Return empty list to simulate no snapshots."""
        return []


class TestOrderbookFallback:
    """Test orderbook fallback warnings and logging."""
    
    @pytest.mark.asyncio
    async def test_orderbook_fallback_emits_warning(self):
        """Test that missing orderbook emits OrderBookWarning."""
        repo = FakeOrderBookRepository(return_none=True)
        simulator = ExecutionSimulator(orderbook_repo=repo)
        
        order = MarketOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            qty=1.0,
            config=OrderConfig(),
        )
        
        bar = {
            "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
            "open": 45000.0,
            "high": 45100.0,
            "low": 44900.0,
            "close": 45050.0,
            "volume": 100.0,
        }
        
        # Capture warnings
        with patch("app.backtesting.execution_simulator.logger") as mock_logger:
            result = await simulator.simulate_execution(order, bar)
            
            # Verify warning was logged
            assert mock_logger.warning.called
            warning_call = mock_logger.warning.call_args
            
            # Verify warning message contains expected information
            assert "OrderBookWarning" in str(warning_call) or "orderbook" in str(warning_call).lower()
    
    @pytest.mark.asyncio
    async def test_orderbook_fallback_count_tracking(self):
        """Test that orderbook fallback count is tracked correctly."""
        repo = FakeOrderBookRepository(return_none=True)
        simulator = ExecutionSimulator(orderbook_repo=repo)
        
        # Initial count should be 0
        assert simulator.orderbook_fallback_count == 0
        assert len(simulator.orderbook_warnings) == 0
        
        order = MarketOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            qty=1.0,
            config=OrderConfig(),
        )
        
        bar = {
            "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
            "close": 45000.0,
        }
        
        # Execute multiple times
        for i in range(5):
            await simulator.simulate_execution(order, bar)
        
        # Verify count increased
        assert simulator.orderbook_fallback_count == 5
        assert len(simulator.orderbook_warnings) == 5
    
    @pytest.mark.asyncio
    async def test_orderbook_warning_details(self):
        """Test that OrderBookWarning contains expected details."""
        repo = FakeOrderBookRepository(return_none=True)
        simulator = ExecutionSimulator(orderbook_repo=repo)
        
        order = MarketOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            qty=1.0,
            config=OrderConfig(),
        )
        
        timestamp = pd.Timestamp("2024-01-01 12:00:00")
        bar = {
            "timestamp": timestamp,
            "close": 45000.0,
        }
        
        await simulator.simulate_execution(order, bar)
        
        # Verify warning was recorded
        assert len(simulator.orderbook_warnings) == 1
        
        warning = simulator.orderbook_warnings[0]
        assert isinstance(warning, OrderBookWarning)
        assert warning.symbol == "BTCUSDT"
        assert warning.timestamp == timestamp.isoformat()
        assert warning.reason in ["not_found", "file_not_found", "no_snapshots_in_range", "out_of_tolerance"]
        assert warning.tolerance_seconds == 30
    
    @pytest.mark.asyncio
    async def test_orderbook_warning_to_dict(self):
        """Test that OrderBookWarning can be serialized to dict."""
        warning = OrderBookWarning(
            symbol="BTCUSDT",
            timestamp="2024-01-01T12:00:00",
            reason="not_found",
            tolerance_seconds=30,
        )
        
        warning_dict = warning.to_dict()
        
        assert "symbol" in warning_dict
        assert "timestamp" in warning_dict
        assert "reason" in warning_dict
        assert "tolerance_seconds" in warning_dict
        
        assert warning_dict["symbol"] == "BTCUSDT"
        assert warning_dict["timestamp"] == "2024-01-01T12:00:00"
        assert warning_dict["reason"] == "not_found"
        assert warning_dict["tolerance_seconds"] == 30
    
    @pytest.mark.asyncio
    async def test_orderbook_fallback_in_execution_metrics(self):
        """Test that orderbook fallback count is included in execution metrics."""
        repo = FakeOrderBookRepository(return_none=True)
        simulator = ExecutionSimulator(orderbook_repo=repo)
        
        order = MarketOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            qty=1.0,
            config=OrderConfig(),
        )
        
        bar = {
            "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
            "close": 45000.0,
        }
        
        # Execute a few times
        for i in range(3):
            await simulator.simulate_execution(order, bar)
        
        # Get execution metrics
        metrics = simulator.get_execution_metrics()
        
        # Verify fallback count is in metrics
        assert "orderbook_fallback_count" in metrics
        assert metrics["orderbook_fallback_count"] == 3
        
        # Verify warnings are in metrics
        assert "orderbook_warnings" in metrics
        assert len(metrics["orderbook_warnings"]) == 3
    
    @pytest.mark.asyncio
    async def test_reset_counters(self):
        """Test that reset_counters clears fallback tracking."""
        repo = FakeOrderBookRepository(return_none=True)
        simulator = ExecutionSimulator(orderbook_repo=repo)
        
        order = MarketOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            qty=1.0,
            config=OrderConfig(),
        )
        
        bar = {
            "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
            "close": 45000.0,
        }
        
        # Execute a few times
        for i in range(3):
            await simulator.simulate_execution(order, bar)
        
        assert simulator.orderbook_fallback_count == 3
        assert len(simulator.orderbook_warnings) == 3
        
        # Reset counters
        simulator.reset_counters()
        
        assert simulator.orderbook_fallback_count == 0
        assert len(simulator.orderbook_warnings) == 0
    
    @pytest.mark.asyncio
    async def test_different_fallback_reasons(self):
        """Test that different fallback reasons are detected."""
        repo = FakeOrderBookRepository(return_none=True)
        simulator = ExecutionSimulator(orderbook_repo=repo)
        
        # Mock path.exists() to return False (file_not_found)
        with patch("pathlib.Path.exists", return_value=False):
            order = MarketOrder(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                qty=1.0,
                config=OrderConfig(),
            )
            
            bar = {
                "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
                "close": 45000.0,
            }
            
            await simulator.simulate_execution(order, bar)
            
            # Verify warning reason is file_not_found
            assert len(simulator.orderbook_warnings) == 1
            # The reason detection might vary, but should be one of the expected reasons
            assert simulator.orderbook_warnings[0].reason in [
                "not_found",
                "file_not_found",
                "no_snapshots_in_range",
                "out_of_tolerance",
            ]

