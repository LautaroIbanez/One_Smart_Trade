"""Unit tests for performance service fallback metrics in low-trade scenarios."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

import pandas as pd

from app.services.performance_service import PerformanceService
from app.backtesting.metrics import calculate_metrics


@pytest.fixture
def performance_service():
    """Create PerformanceService instance."""
    return PerformanceService()


@pytest.mark.asyncio
async def test_fallback_metrics_status_never_unknown(performance_service):
    """
    Test that metrics_status is never UNKNOWN - always maps to deterministic fallback.
    
    Acceptance: /api/v1/performance/summary?allow_stale_inputs=true returns metrics_status 
    in {PASS, FALLBACK_NO_TRADES, DEV_FALLBACK} with explanatory message, never UNKNOWN.
    """
    # Create a backtest result with missing metrics_status (simulating old cached data)
    backtest_result = {
        "start_date": "2020-01-01T00:00:00Z",
        "end_date": "2024-01-01T00:00:00Z",
        "trades": [],
        "equity_theoretical": [10000.0] * 100,
        "equity_realistic": [10000.0] * 100,
        "equity_curve": [{"timestamp": "2020-01-01T00:00:00Z", "equity_theoretical": 10000.0, "equity_realistic": 10000.0}],
        "no_trade_diagnostics": {
            "root_cause": "no_signals_generated",
            "reason": "Strategy did not generate any signals during the backtest period.",
            "signal_counts": {"total": 0, "enter": 0, "hold": 0},
        },
    }
    
    # Calculate metrics (which won't have metrics_status set)
    metrics = calculate_metrics(backtest_result)
    # Ensure metrics_status is not set (simulating old cached data)
    if "metrics_status" in metrics:
        del metrics["metrics_status"]
    
    # Mock the service to return this result
    with patch.object(performance_service, "_get_db_cached_success_summary", return_value={
        "status": "success",
        "metrics": metrics,
        "period": {"start": "2020-01-01T00:00:00Z", "end": "2024-01-01T00:00:00Z"},
        "cached_at": datetime.utcnow().isoformat(),
    }):
        summary = await performance_service.get_summary(allow_stale_inputs=True)
        
        # Verify metrics_status is never UNKNOWN
        metrics_status = summary.get("metrics_status")
        assert metrics_status is not None, "metrics_status should not be None"
        assert metrics_status != "UNKNOWN", f"metrics_status should never be UNKNOWN, got {metrics_status}"
        assert metrics_status in ("PASS", "FALLBACK_NO_TRADES", "DEV_FALLBACK", "NO_TRADES", "INSUFFICIENT_DATA"), \
            f"metrics_status should be in allowed set, got {metrics_status}"
        
        # Verify explanatory message is present
        if metrics_status != "PASS":
            assert "message" in summary or "degraded_reason" in summary.get("metadata", {}), \
                "Non-PASS status should have explanatory message"


@pytest.mark.asyncio
async def test_conservative_tp_probability_when_trade_count_low(performance_service):
    """
    Test that conservative TP probability and expected return are computed when trade count < N.
    
    Acceptance: Compute conservative TP probability/expected return when trade count < N 
    instead of returning UNKNOWN.
    """
    # Create a backtest result with low trade count (< 10)
    backtest_result = {
        "start_date": "2020-01-01T00:00:00Z",
        "end_date": "2024-01-01T00:00:00Z",
        "trades": [
            {"pnl": 100.0, "return_pct": 1.0},
            {"pnl": -50.0, "return_pct": -0.5},
            {"pnl": 75.0, "return_pct": 0.75},
        ],  # Only 3 trades (< 10 threshold)
        "equity_theoretical": [10000.0] * 100,
        "equity_realistic": [10000.0] * 100,
        "equity_curve": [{"timestamp": "2020-01-01T00:00:00Z", "equity_theoretical": 10000.0, "equity_realistic": 10000.0}],
        "initial_capital": 10000.0,
    }
    
    # Calculate metrics
    metrics = calculate_metrics(backtest_result)
    
    # Generate fallback metrics (should compute conservative estimates)
    total_days = (datetime.fromisoformat(backtest_result["end_date"].replace("Z", "+00:00")) - 
                  datetime.fromisoformat(backtest_result["start_date"].replace("Z", "+00:00"))).days
    
    fallback_metrics = performance_service._generate_fallback_metrics(
        metrics,
        trade_count=len(backtest_result["trades"]),
        total_days=total_days,
    )
    
    # Verify conservative TP probability is computed
    assert "conservative_tp_probability" in fallback_metrics, \
        "Fallback metrics should include conservative_tp_probability when trade_count < 10"
    assert fallback_metrics["conservative_tp_probability"] is not None, \
        "conservative_tp_probability should not be None"
    assert 0.0 <= fallback_metrics["conservative_tp_probability"] <= 1.0, \
        f"conservative_tp_probability should be between 0 and 1, got {fallback_metrics['conservative_tp_probability']}"
    
    # Verify conservative expected return is computed
    assert "conservative_expected_return" in fallback_metrics, \
        "Fallback metrics should include conservative_expected_return when trade_count < 10"
    assert fallback_metrics["conservative_expected_return"] is not None, \
        "conservative_expected_return should not be None"
    
    # Verify reason is included
    assert "conservative_estimates_reason" in fallback_metrics, \
        "Fallback metrics should include conservative_estimates_reason"
    assert "trade count" in fallback_metrics["conservative_estimates_reason"].lower(), \
        "conservative_estimates_reason should mention trade count"


@pytest.mark.asyncio
async def test_no_conservative_estimates_when_trade_count_high(performance_service):
    """
    Test that conservative estimates are NOT computed when trade count >= N.
    """
    # Create a backtest result with sufficient trade count (>= 10)
    backtest_result = {
        "start_date": "2020-01-01T00:00:00Z",
        "end_date": "2024-01-01T00:00:00Z",
        "trades": [{"pnl": 100.0, "return_pct": 1.0}] * 15,  # 15 trades (>= 10 threshold)
        "equity_theoretical": [10000.0] * 100,
        "equity_realistic": [10000.0] * 100,
        "equity_curve": [{"timestamp": "2020-01-01T00:00:00Z", "equity_theoretical": 10000.0, "equity_realistic": 10000.0}],
        "initial_capital": 10000.0,
    }
    
    # Calculate metrics
    metrics = calculate_metrics(backtest_result)
    
    # Generate fallback metrics (should NOT compute conservative estimates)
    total_days = (datetime.fromisoformat(backtest_result["end_date"].replace("Z", "+00:00")) - 
                  datetime.fromisoformat(backtest_result["start_date"].replace("Z", "+00:00"))).days
    
    fallback_metrics = performance_service._generate_fallback_metrics(
        metrics,
        trade_count=len(backtest_result["trades"]),
        total_days=total_days,
    )
    
    # Verify conservative estimates are NOT included when trade_count >= 10
    assert "conservative_tp_probability" not in fallback_metrics or fallback_metrics.get("conservative_tp_probability") is None, \
        "Fallback metrics should NOT include conservative_tp_probability when trade_count >= 10"
    assert "conservative_expected_return" not in fallback_metrics or fallback_metrics.get("conservative_expected_return") is None, \
        "Fallback metrics should NOT include conservative_expected_return when trade_count >= 10"


@pytest.mark.asyncio
async def test_guardrail_bypass_surfaced_in_metadata(performance_service):
    """
    Test that guardrail bypass is explicitly surfaced in API metadata.
    
    Acceptance: Surface guardrail bypass explicitly in API metadata.
    """
    # Create a backtest result with insufficient trades in dev mode
    backtest_result = {
        "start_date": "2020-01-01T00:00:00Z",
        "end_date": "2024-01-01T00:00:00Z",
        "trades": [{"pnl": 100.0, "return_pct": 1.0}] * 5,  # 5 trades (< 50 threshold)
        "equity_theoretical": [10000.0] * 100,
        "equity_realistic": [10000.0] * 100,
        "equity_curve": [{"timestamp": "2020-01-01T00:00:00Z", "equity_theoretical": 10000.0, "equity_realistic": 10000.0}],
        "initial_capital": 10000.0,
    }
    
    # Mock dev mode
    with patch("app.core.config.settings.is_dev_mode", return_value=True):
        # Mock the backtest execution
        with patch.object(performance_service.engine, "run_backtest", new_callable=AsyncMock) as mock_backtest:
            mock_backtest.return_value = backtest_result
            
            # Mock strategy resolution
            with patch.object(performance_service, "_resolve_strategy") as mock_strategy:
                mock_strategy.return_value = Mock()
                
                # Run get_summary
                summary = await performance_service.get_summary(allow_stale_inputs=False)
                
                # Verify guardrail bypass is surfaced in metadata
                metadata = summary.get("metadata", {})
                if summary.get("metrics_status") == "DEV_FALLBACK":
                    assert metadata.get("guardrail_bypass") is True, \
                        "guardrail_bypass should be True when metrics_status is DEV_FALLBACK"
                    assert "guardrail_bypass_reason" in metadata, \
                        "guardrail_bypass_reason should be present in metadata"
                    assert "guardrail_bypass_details" in metadata, \
                        "guardrail_bypass_details should be present in metadata"
                    assert metadata["guardrail_bypass_details"].get("trade_count") is not None, \
                        "guardrail_bypass_details should include trade_count"


@pytest.mark.asyncio
async def test_fallback_no_trades_status_with_explanatory_message(performance_service):
    """
    Test that FALLBACK_NO_TRADES status includes explanatory message.
    
    Acceptance: /api/v1/performance/summary?allow_stale_inputs=true returns metrics_status 
    in {PASS, FALLBACK_NO_TRADES, DEV_FALLBACK} with explanatory message.
    """
    # Create a backtest result with zero trades
    backtest_result = {
        "start_date": "2020-01-01T00:00:00Z",
        "end_date": "2024-01-01T00:00:00Z",
        "trades": [],
        "equity_theoretical": [10000.0] * 100,
        "equity_realistic": [10000.0] * 100,
        "equity_curve": [{"timestamp": "2020-01-01T00:00:00Z", "equity_theoretical": 10000.0, "equity_realistic": 10000.0}],
        "no_trade_diagnostics": {
            "root_cause": "no_signals_generated",
            "reason": "Strategy did not generate any signals during the backtest period.",
            "signal_counts": {"total": 0, "enter": 0, "hold": 0},
        },
    }
    
    # Mock the backtest execution
    with patch.object(performance_service.engine, "run_backtest", new_callable=AsyncMock) as mock_backtest:
        mock_backtest.return_value = backtest_result
        
        # Mock strategy resolution
        with patch.object(performance_service, "_resolve_strategy") as mock_strategy:
            mock_strategy.return_value = Mock()
            
            # Run get_summary
            summary = await performance_service.get_summary(allow_stale_inputs=False)
            
            # Verify metrics_status is FALLBACK_NO_TRADES or NO_TRADES (not UNKNOWN)
            metrics_status = summary.get("metrics_status")
            assert metrics_status is not None, "metrics_status should not be None"
            assert metrics_status != "UNKNOWN", f"metrics_status should never be UNKNOWN, got {metrics_status}"
            assert metrics_status in ("FALLBACK_NO_TRADES", "NO_TRADES"), \
                f"metrics_status should be FALLBACK_NO_TRADES or NO_TRADES for zero trades, got {metrics_status}"
            
            # Verify explanatory message is present
            metadata = summary.get("metadata", {})
            assert metadata.get("no_trade_reason") or metadata.get("degraded_reason"), \
                "FALLBACK_NO_TRADES status should have explanatory message in metadata"


@pytest.mark.asyncio
async def test_no_trades_vs_fallback_no_trades_distinction(performance_service):
    """
    Test BE-METRICS-01: Distinguish between NO_TRADES and FALLBACK_NO_TRADES.
    
    ROOT CAUSE: Performance summary was returning FALLBACK_NO_TRADES despite has_metrics=true
    when metrics_status was missing from cache, even though only minimal metrics existed.
    
    Acceptance:
    - NO_TRADES: When only minimal metrics exist (total_trades=0, winning_trades=0, losing_trades=0)
    - FALLBACK_NO_TRADES: When fallback/synthetic metrics exist (has CAGR, Sharpe, etc.)
    """
    # Test case 1: Minimal metrics only (should be NO_TRADES)
    minimal_metrics = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        # No metrics_status, no fallback metrics
    }
    
    # Mock cached summary with minimal metrics and missing metrics_status
    with patch.object(performance_service, "_get_db_cached_success_summary", return_value={
        "status": "success",
        "metrics": minimal_metrics,
        "period": {"start": "2020-01-01T00:00:00Z", "end": "2024-01-01T00:00:00Z"},
        "cached_at": datetime.utcnow().isoformat(),
        "metrics_status": None,  # Simulating missing status from cache
    }):
        summary = await performance_service.get_summary(allow_stale_inputs=True)
        
        # Should be NO_TRADES, not FALLBACK_NO_TRADES
        metrics_status = summary.get("metrics_status")
        assert metrics_status == "NO_TRADES", \
            f"Minimal metrics should map to NO_TRADES, got {metrics_status}"
        
        # Verify metrics are truly minimal (only trade counts)
        metrics = summary.get("metrics", {})
        assert metrics.get("total_trades") == 0
        assert "cagr" not in metrics or metrics.get("cagr") is None, \
            "Minimal metrics should not have synthetic values like CAGR"
        assert "sharpe_ratio" not in metrics or metrics.get("sharpe_ratio") is None, \
            "Minimal metrics should not have synthetic values like Sharpe ratio"
    
    # Test case 2: Fallback metrics exist (should be FALLBACK_NO_TRADES)
    fallback_metrics = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "cagr": 0.0,  # Fallback metric
        "sharpe_ratio": 0.0,  # Fallback metric
        "max_drawdown": 0.0,  # Fallback metric
        # No metrics_status - simulating missing status from cache
    }
    
    # Mock cached summary with fallback metrics and missing metrics_status
    with patch.object(performance_service, "_get_db_cached_success_summary", return_value={
        "status": "success",
        "metrics": fallback_metrics,
        "period": {"start": "2020-01-01T00:00:00Z", "end": "2024-01-01T00:00:00Z"},
        "cached_at": datetime.utcnow().isoformat(),
        "metrics_status": None,  # Simulating missing status from cache
    }):
        summary = await performance_service.get_summary(allow_stale_inputs=True)
        
        # Should be FALLBACK_NO_TRADES, not NO_TRADES
        metrics_status = summary.get("metrics_status")
        assert metrics_status == "FALLBACK_NO_TRADES", \
            f"Fallback metrics should map to FALLBACK_NO_TRADES, got {metrics_status}"
        
        # Verify fallback metrics are present
        metrics = summary.get("metrics", {})
        assert metrics.get("cagr") is not None, \
            "Fallback metrics should have synthetic values like CAGR"
        assert metrics.get("sharpe_ratio") is not None, \
            "Fallback metrics should have synthetic values like Sharpe ratio"
    
    # Test case 3: Explicitly set NO_TRADES status should be preserved
    minimal_metrics_with_status = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "metrics_status": "NO_TRADES",  # Explicitly set
    }
    
    with patch.object(performance_service, "_get_db_cached_success_summary", return_value={
        "status": "success",
        "metrics": minimal_metrics_with_status,
        "period": {"start": "2020-01-01T00:00:00Z", "end": "2024-01-01T00:00:00Z"},
        "cached_at": datetime.utcnow().isoformat(),
        "metrics_status": "NO_TRADES",  # Explicitly set
    }):
        summary = await performance_service.get_summary(allow_stale_inputs=True)
        
        # Should preserve NO_TRADES status
        metrics_status = summary.get("metrics_status")
        assert metrics_status == "NO_TRADES", \
            f"Explicit NO_TRADES status should be preserved, got {metrics_status}"