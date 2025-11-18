# Risk Management Tests

This directory contains automated tests for the risk management system.

## Test Files

### `test_user_specific_sizing.py`

Tests that position sizing changes proportionally with different equity/drawdown scenarios.

**Test Cases:**
- `test_sizing_proportional_to_equity`: Verifies sizing scales proportionally with equity (1k, 5k, 10k, 50k)
- `test_sizing_reduces_with_drawdown`: Verifies sizing reduces as drawdown increases (0%, 10%, 25%, 40%)
- `test_sizing_with_zero_equity_returns_missing_equity`: Verifies proper handling when equity is zero
- `test_sizing_with_high_drawdown_blocks_trade`: Verifies sizing is blocked when drawdown > 50%
- `test_sizing_scales_with_risk_budget`: Verifies sizing scales with risk budget percentage (0.5%, 1%, 1.5%, 2%)

**Run:**
```bash
pytest tests/risk/test_user_specific_sizing.py -v
```

### `test_ruin_blocks.py`

Tests that signals are blocked when `risk_of_ruin > 0.05`.

**Test Cases:**
- `test_low_ruin_risk_allows_trade`: Verifies trades with low ruin risk (< 5%) are allowed
- `test_high_ruin_risk_blocks_trade`: Verifies trades with high ruin risk (> 10%) are blocked
- `test_ruin_risk_reduces_sizing`: Verifies sizing is reduced when ruin risk is between 5% and 10%
- `test_ruin_simulator_calculates_high_risk`: Verifies RuinSimulator correctly calculates high risk for poor metrics
- `test_ruin_block_message_format`: Verifies ruin block messages are properly formatted
- `test_ruin_risk_with_no_trade_history`: Verifies conservative defaults when no trade history available

**Run:**
```bash
pytest tests/risk/test_ruin_blocks.py -v
```

### `test_exposure_limits.py`

Tests that exposure and concentration limits block trades when exceeded.

**Test Cases:**
- `test_exposure_limit_blocks_when_exceeded`: Verifies aggregate exposure limit (2× equity) blocks trades
- `test_concentration_limit_blocks_when_exceeded`: Verifies concentration limit (30% per symbol) blocks trades
- `test_correlation_limit_blocks_highly_correlated_positions`: Verifies correlation limit (> 0.7) blocks correlated positions
- `test_exposure_allows_when_below_limit`: Verifies trades are allowed when exposure is below limit
- `test_exposure_validation_calculates_correctly`: Verifies exposure validation calculates beta-adjusted notional correctly

**Run:**
```bash
pytest tests/risk/test_exposure_limits.py -v
```

## Running All Risk Tests

```bash
# Run all risk tests
pytest tests/risk/ -v

# Run with coverage
pytest tests/risk/ --cov=app.services.recommendation_service --cov=app.backtesting.unified_risk_manager --cov=app.services.exposure_ledger_service -v

# Run specific test
pytest tests/risk/test_user_specific_sizing.py::TestUserSpecificSizing::test_sizing_proportional_to_equity -v
```

## Test Fixtures

All tests use pytest fixtures for:
- `sample_recommendation`: Sample recommendation data structure
- `risk_service`: RecommendationService instance
- `exposure_ledger`: ExposureLedgerService instance

## Mocking

Tests use `unittest.mock.patch` to mock:
- `UserRiskProfileService.get_context()`: To simulate different user equity/drawdown scenarios
- `UserRiskProfileService.get_open_positions()`: To simulate existing positions for exposure limit tests

## Expected Behavior

### User-Specific Sizing
- Sizing should scale proportionally with equity
- Sizing should reduce as drawdown increases
- Zero equity should return `missing_equity` status
- High drawdown (> 50%) should block or severely reduce sizing

### Ruin Risk Blocks
- Low ruin risk (< 5%): Trade allowed
- Moderate ruin risk (5-10%): Sizing reduced
- High ruin risk (> 10% or multiplier < 0.2): Trade blocked

### Exposure Limits
- Aggregate exposure > 2× equity: Trade blocked
- Concentration > 30% per symbol: Trade blocked
- Correlation > 0.7 in same direction: Trade blocked
- All limits below thresholds: Trade allowed

