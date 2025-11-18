# SL/TP Optimization Pipeline

## Overview

The Stop Loss / Take Profit (SL/TP) optimization pipeline uses walk-forward validation to find optimal risk management parameters per symbol and market regime. It evaluates combinations of ATR multipliers, TP ratios, and breakeven buffers, selecting parameters that maximize Calmar ratio and profit factor while maintaining acceptable drawdowns.

## Architecture

### Components

1. **StopLossTakeProfitOptimizer** (`backend/app/risk/sl_tp_optimizer.py`)
   - Performs walk-forward optimization
   - Searches parameter space (grid or Bayesian)
   - Evaluates metrics per window
   - Persists configurations to JSON artifacts

2. **SLTPReportGenerator** (`backend/app/risk/sl_tp_reporting.py`)
   - Generates markdown reports
   - Calculates MAE/MFE distributions
   - Compares RR vs benchmark
   - Tracks trailing stop performance

3. **StrategyService** (`backend/app/services/strategy_service.py`)
   - Loads optimized configurations
   - Applies parameters to signals
   - Enforces guardrails (RR, liquidity zones)

4. **CLI Script** (`scripts/sl_tp/optimize.py`)
   - Command-line interface for optimization
   - Supports custom search spaces
   - Generates reports

## Walk-Forward Validation

### Process

1. **Window Construction**: Rolling windows of train (90 days) / test (30 days)
2. **Parameter Search**: Grid or Bayesian search on training data
3. **Evaluation**: Test best parameters on out-of-sample test window
4. **Consensus**: Derive consensus parameters across all windows
5. **Persistence**: Save configuration to `artifacts/sl_tp/{symbol}/{regime}/config.json`

### Metrics Evaluated

- **Calmar Ratio**: Return / Max Drawdown
- **Profit Factor**: Gross Profit / Gross Loss
- **Hit Rate**: Percentage of winning trades
- **Average RR**: Mean Risk-Reward ratio
- **Expectancy (R)**: Expected return per unit risk
- **Max Drawdown**: Maximum peak-to-trough decline

## Usage

### CLI Command

```bash
# Basic optimization for a specific regime
python scripts/sl_tp/optimize.py \
  --symbol BTCUSDT \
  --regime trend \
  --trades data/backtest_reports/trades.parquet \
  --generate-report

# Optimize all regimes (requires price data for classification)
python scripts/sl_tp/optimize.py \
  --symbol BTCUSDT \
  --trades data/backtest_reports/trades.parquet \
  --price-data data/curated/1d.parquet \
  --generate-report

# Custom search space
python scripts/sl_tp/optimize.py \
  --symbol BTCUSDT \
  --regime trend \
  --trades trades.parquet \
  --atr-sl 1.5 2.0 2.5 \
  --atr-tp 2.0 3.0 4.0 \
  --tp-ratio 1.5 2.0 2.5

# Bayesian optimization
python scripts/sl_tp/optimize.py \
  --symbol BTCUSDT \
  --regime trend \
  --trades trades.parquet \
  --method bayesian
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--symbol` | Trading symbol (required) | - |
| `--regime` | Market regime (optional, optimizes all if not specified) | None |
| `--trades` | Path to trades file (required) | - |
| `--price-data` | Path to price data for regime classification | None |
| `--artifacts-dir` | Directory for optimization artifacts | `artifacts/sl_tp` |
| `--reports-dir` | Directory for generated reports | `reports` |
| `--train-days` | Training window size in days | 90 |
| `--test-days` | Test window size in days | 30 |
| `--rr-floor` | Minimum RR ratio threshold | 1.2 |
| `--method` | Optimization method (`grid` or `bayesian`) | `grid` |
| `--atr-sl` | ATR multiplier values for stop loss | Default search space |
| `--atr-tp` | ATR multiplier values for take profit | Default search space |
| `--tp-ratio` | TP ratio values | Default search space |
| `--benchmark-rr` | Benchmark RR for comparison | 1.5 |
| `--generate-report` | Generate markdown report after optimization | False |

### Input Data Requirements

**Trades File** (Parquet or CSV):
- Required columns: `timestamp`, `mae`, `mfe`
- Optional columns: `regime`, `symbol`, `entry_price`, `exit_price`, `pnl`

**Price Data** (Parquet or CSV):
- Required for regime classification if not present in trades
- Should have OHLCV columns and timestamp index

## Configuration Artifacts

### Structure

```
artifacts/sl_tp/
  {symbol}/
    {regime}/
      config.json
```

### Config JSON Schema

```json
{
  "symbol": "BTCUSDT",
  "regime": "trend",
  "rr_threshold": 1.5,
  "search_space": {
    "atr_multiplier_sl": [1.25, 1.5, 2.0],
    "atr_multiplier_tp": [2.0, 2.5, 3.0],
    "tp_ratio": [1.4, 1.8, 2.2]
  },
  "windows": [
    {
      "index": 0,
      "train_range": ["2024-01-01T00:00:00Z", "2024-04-01T00:00:00Z"],
      "test_range": ["2024-04-01T00:00:00Z", "2024-05-01T00:00:00Z"],
      "params": {
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.0,
        "tp_ratio": 2.0
      },
      "train_metrics": {
        "calmar": 2.5,
        "profit_factor": 1.6,
        "hit_rate": 0.55,
        "avg_rr": 1.8,
        "expectancy_r": 0.45,
        "max_drawdown": 0.12
      },
      "test_metrics": {
        "calmar": 2.3,
        "profit_factor": 1.5,
        "hit_rate": 0.52,
        "avg_rr": 1.7,
        "expectancy_r": 0.42,
        "max_drawdown": 0.15
      }
    }
  ],
  "aggregates": {
    "calmar": 2.4,
    "profit_factor": 1.55,
    "hit_rate": 0.535,
    "avg_rr": 1.75,
    "expectancy_r": 0.435,
    "max_drawdown": 0.14
  },
  "best_params": {
    "atr_multiplier_sl": 2.0,
    "atr_multiplier_tp": 3.0,
    "tp_ratio": 2.0,
    "breakeven_buffer_pct": 0.15
  },
  "metadata": {
    "method": "grid",
    "updated_at": "2024-05-01T12:00:00Z",
    "train_days": 90,
    "test_days": 30
  }
}
```

## Reports

### Markdown Reports

Reports are generated in `reports/sl_tp_walkforward_{symbol}_{regime}_{timestamp}.md` and include:

- **Consensus Parameters**: Best parameters across all windows
- **Aggregate Metrics**: Average performance metrics
- **MAE/MFE Distributions**: Percentiles (P50, P70, P90, P95)
- **Trailing Stop Performance**: Hit rate if available
- **RR vs Benchmark**: Comparison with benchmark RR
- **Walk-Forward Windows**: Detailed results per window

### Report Generation

```bash
# Generate report after optimization
python scripts/sl_tp/optimize.py \
  --symbol BTCUSDT \
  --regime trend \
  --trades trades.parquet \
  --generate-report
```

## Integration with Strategy Service

The `StrategyService` automatically loads optimized configurations:

```python
from app.services.strategy_service import StrategyService

service = StrategyService()
signal = await service.apply_sl_tp_policy(signal, price_data)
```

The service:
1. Detects current market regime
2. Loads optimized config for symbol/regime
3. Applies parameters to signal
4. Enforces guardrails (RR threshold, liquidity zones)
5. Falls back to conservative defaults if config missing

## Quality Gates (CI Tests)

### Test Suite

Tests in `backend/tests/risk/test_sl_tp_quality.py` validate:

1. **RR Threshold**: `optimized_rr >= 1.2`
2. **MAE P95**: `mae_p95 <= stop_distance`
3. **Drawdown Limit**: `walkforward_dd <= 0.25` (25%)
4. **Window Consistency**: All windows meet minimum RR
5. **Parameter Validity**: Consensus params present and valid

### Running CI Tests

```bash
# Run quality gate tests
pytest backend/tests/risk/test_sl_tp_quality.py -v

# Run specific test
pytest backend/tests/risk/test_sl_tp_quality.py::TestOptimizationQuality::test_optimized_rr_above_threshold -v
```

### CI Integration

Add to your CI pipeline:

```yaml
# .github/workflows/sl_tp_quality.yml
name: SL/TP Quality Gates

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  quality-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/risk/test_sl_tp_quality.py::test_ci_quality_gates -v
```

## Go/No-Go Checklist

Before deploying optimized parameters to production:

### Data Quality
- [ ] Sufficient historical trades (minimum 120 days for 90/30 split)
- [ ] Trades include MAE/MFE columns
- [ ] Regime labels accurate or price data available for classification
- [ ] No data gaps or anomalies

### Optimization Results
- [ ] At least 3 walk-forward windows completed
- [ ] Consensus parameters consistent across windows
- [ ] Aggregate metrics meet thresholds:
  - [ ] `avg_rr >= 1.2`
  - [ ] `max_drawdown <= 0.25`
  - [ ] `calmar >= 1.5`
  - [ ] `profit_factor >= 1.2`
- [ ] All windows meet minimum RR (>= 1.0)

### Validation
- [ ] MAE P95 < stop_distance (derived from params)
- [ ] RR improvement vs benchmark > 0%
- [ ] No excessive drawdown in any window (> 30%)
- [ ] CI quality gates pass

### Documentation
- [ ] Report generated and reviewed
- [ ] Parameters documented in config JSON
- [ ] Changes logged in CHANGELOG

### Deployment
- [ ] Config artifacts in correct location
- [ ] StrategyService can load config
- [ ] Fallback defaults tested
- [ ] Monitoring alerts configured

## Troubleshooting

### Issue: No optimization results

**Symptoms**: Empty results dictionary

**Causes**:
- Insufficient trades for regime
- No valid windows constructed
- All parameter combinations failed

**Solutions**:
- Check trade count per regime (need >= train_days + test_days)
- Verify timestamp column format
- Review search space (may be too restrictive)

### Issue: Config not loading

**Symptoms**: StrategyService falls back to defaults

**Causes**:
- Config file missing
- Config file stale (> max_config_age_days)
- Invalid JSON

**Solutions**:
- Verify artifacts directory structure
- Check config age in metadata
- Validate JSON syntax

### Issue: Quality gates failing

**Symptoms**: CI tests fail

**Causes**:
- RR below threshold
- Drawdown too high
- MAE exceeds stop distance

**Solutions**:
- Review optimization results
- Adjust search space
- Increase training window
- Check for data quality issues

## Best Practices

1. **Regular Re-optimization**: Re-run optimization monthly or after significant market regime changes
2. **Multiple Regimes**: Optimize for all relevant regimes (trend, range, volatile)
3. **Validation**: Always review reports before deploying
4. **Monitoring**: Track actual performance vs optimized expectations
5. **Conservative Defaults**: Ensure fallback defaults are conservative
6. **Documentation**: Keep reports and configs versioned

## References

- [Risk Management Documentation](./risk-management.md)
- [Strategy Service Implementation](../backend/app/services/strategy_service.py)
- [Optimizer Implementation](../backend/app/risk/sl_tp_optimizer.py)

