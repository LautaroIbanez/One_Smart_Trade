"""Comprehensive sensitivity analysis with statistical testing and visualization."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.model_selection import ParameterGrid

from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import calculate_metrics
from app.backtesting.objectives import Objective
from app.core.logging import logger


@dataclass
class SensitivityResult:
    """Result from a single parameter combination evaluation."""

    params: dict[str, Any]
    metrics: dict[str, float]
    score: float
    valid: bool
    params_id: str


class SensitivityRunner:
    """Systematic parameter grid sweeps with statistical analysis."""

    def __init__(
        self,
        objective: Objective | None = None,
    ) -> None:
        """
        Initialize sensitivity runner.
        
        Args:
            objective: Objective function for scoring (default: CalmarUnderDrawdown)
        """
        from app.backtesting.objectives import CalmarUnderDrawdown
        self.objective = objective or CalmarUnderDrawdown()

    @staticmethod
    def default_param_grid() -> dict[str, Sequence[Any]]:
        """
        Generate default parameter grid for sensitivity analysis.
        
        Returns:
            Dict with parameter names and value sequences for strategy_overrides
        """
        return {
            "breakout.lookback": [10, 15, 20, 25, 30],
            "volatility.low_threshold": [0.15, 0.2, 0.25],
            "volatility.high_threshold": [0.45, 0.5, 0.55],
            "aggregate.vector_bias.momentum_bias_weight": [0.15, 0.2, 0.25, 0.3],
            "aggregate.vector_bias.breakout_slope_weight": [0.05, 0.1, 0.15],
        }

    @staticmethod
    def param_grid_to_overrides(param_grid: dict[str, Sequence[Any]]) -> list[dict[str, dict[str, Any]]]:
        """
        Convert flat parameter grid to nested strategy_overrides format.
        
        Args:
            param_grid: Dict with keys like "breakout.lookback" and value sequences
            
        Returns:
            List of strategy_overrides dicts
        """
        grid = ParameterGrid(param_grid)
        overrides_list = []
        
        for combo in grid:
            strategy_overrides = {}
            for key, value in combo.items():
                parts = key.split(".")
                current = strategy_overrides
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
            overrides_list.append({"strategy_overrides": strategy_overrides})
        
        return overrides_list

    @staticmethod
    def generate_param_grid_from_yaml(
        base_params: dict[str, Any],
        *,
        lookback_range: tuple[int, int, int] = (10, 30, 5),
        vol_threshold_range: tuple[float, float, float] = (0.15, 0.6, 0.1),
        weight_ranges: dict[str, tuple[float, float, int]] | None = None,
    ) -> dict[str, Sequence[Any]]:
        """
        Generate parameter grid from YAML params with ranges.
        
        Args:
            base_params: Base parameters from params.yaml
            lookback_range: (start, end, step) for lookback parameters
            vol_threshold_range: (start, end, step) for volatility thresholds
            weight_ranges: Dict of weight param names to (start, end, steps) tuples
            
        Returns:
            Parameter grid dict
        """
        param_grid = {}
        
        lookback_start, lookback_end, lookback_step = lookback_range
        param_grid["breakout_lookback"] = list(range(lookback_start, lookback_end + 1, lookback_step))
        
        vol_start, vol_end, vol_step = vol_threshold_range
        vol_values = [round(v, 2) for v in np.arange(vol_start, vol_end + vol_step, vol_step)]
        param_grid["vol_threshold_low"] = [v for v in vol_values if v < 0.4]
        param_grid["vol_threshold_high"] = [v for v in vol_values if v > 0.4]
        
        if weight_ranges is None:
            weight_ranges = {
                "momentum_bias_weight": (0.15, 0.3, 4),
                "breakout_slope_weight": (0.05, 0.15, 3),
            }
        
        for param_name, (start, end, steps) in weight_ranges.items():
            param_grid[param_name] = list(np.linspace(start, end, steps).round(3))
        
        return param_grid

    def run(
        self,
        param_grid: dict[str, Sequence[Any]],
        *,
        start_date: Any,
        end_date: Any,
        base_params: dict[str, Any] | None = None,
        use_nested_override: bool = True,
    ) -> pd.DataFrame:
        """
        Run systematic parameter sweep.
        
        Args:
            param_grid: Dict of parameter names to sequences of values.
                Supports flat keys (e.g., "breakout_lookback") or nested keys (e.g., "breakout.lookback").
                If use_nested_override=True, nested keys are converted to strategy_overrides.
            start_date: Backtest start date
            end_date: Backtest end date
            base_params: Base parameters to merge with each variant
            use_nested_override: If True, convert nested keys to strategy_overrides format
            
        Returns:
            DataFrame with parameter combinations and results (calmar, max_dd, etc.)
        """
        base = base_params or {}
        runs = []
        
        if use_nested_override and any("." in k for k in param_grid.keys()):
            override_list = self.param_grid_to_overrides(param_grid)
            grid_size = len(override_list)
        else:
            grid = ParameterGrid(param_grid)
            grid_size = len(list(grid))
            override_list = [{"strategy_overrides": {k: v} for k, v in combo.items()} for combo in grid]
        
        logger.info(
            "Starting sensitivity analysis",
            extra={
                "param_grid_size": grid_size,
                "params": list(param_grid.keys()),
            },
        )
        
        for idx, override_dict in enumerate(override_list, start=1):
            params = {**base, **override_dict}
            flat_params = self._flatten_overrides(override_dict.get("strategy_overrides", {}))
            params_id = self._generate_params_id(params)
            
            try:
                result = self._evaluate_params(params, start_date, end_date)
                
                runs.append({
                    **flat_params,
                    "params_id": params_id,
                    "calmar": result.metrics.get("calmar", 0.0),
                    "max_dd": result.metrics.get("max_drawdown", 0.0),
                    "sharpe": result.metrics.get("sharpe", 0.0),
                    "cagr": result.metrics.get("cagr", 0.0),
                    "win_rate": result.metrics.get("win_rate", 0.0),
                    "profit_factor": result.metrics.get("profit_factor", 0.0),
                    "score": result.score,
                    "valid": result.valid,
                    "total_trades": result.metrics.get("total_trades", 0),
                    "longest_losing_streak": result.metrics.get("longest_losing_streak", 0),
                    "risk_of_ruin": result.metrics.get("risk_of_ruin", 0.0),
                })
            except Exception as exc:
                logger.warning(
                    "Sensitivity run failed",
                    extra={"params_id": params_id, "error": str(exc)},
                )
                runs.append({
                    **flat_params,
                    "params_id": params_id,
                    "calmar": 0.0,
                    "max_dd": 100.0,
                    "sharpe": 0.0,
                    "cagr": 0.0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "score": float("-inf"),
                    "valid": False,
                    "total_trades": 0,
                    "longest_losing_streak": 0,
                    "risk_of_ruin": 1.0,
                })
        
        df = pd.DataFrame(runs)
        logger.info("Sensitivity analysis completed", extra={"total_runs": len(df), "valid_runs": df["valid"].sum()})
        return df

    def _flatten_overrides(self, overrides: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        """Flatten nested dict to flat keys with dots."""
        result = {}
        for key, value in overrides.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_overrides(value, full_key))
            else:
                result[full_key] = value
        return result

    def _evaluate_params(
        self,
        params: dict[str, Any],
        start_date: Any,
        end_date: Any,
    ) -> SensitivityResult:
        """
        Evaluate a single parameter combination.
        
        Supports both engine parameters (position_size_pct, commission, slippage)
        and strategy parameters via temporary params.yaml override.
        """
        engine_args = params.get("engine_args", {})
        execution_overrides = params.get("execution_overrides", {})
        strategy_overrides = params.get("strategy_overrides", {})
        
        original_params = None
        if strategy_overrides:
            try:
                from app.quant.strategies import PARAMS, PARAMS_PATH
                import yaml
                original_params = PARAMS.copy()
                
                merged_params = self._deep_merge(PARAMS.copy(), strategy_overrides)
                with PARAMS_PATH.open("w") as fh:
                    yaml.dump(merged_params, fh, default_flow_style=False)
                
                from importlib import reload
                import app.quant.strategies
                reload(app.quant.strategies)
            except Exception as exc:
                logger.warning("Failed to apply strategy overrides", extra={"error": str(exc)})
        
        try:
            engine = BacktestEngine(**execution_overrides)
            backtest_result = engine.run_backtest(start_date, end_date, **engine_args)
            
            if "error" in backtest_result:
                return SensitivityResult(
                    params=params,
                    metrics={},
                    score=float("-inf"),
                    valid=False,
                    params_id=self._generate_params_id(params),
                )
            
            metrics = calculate_metrics(backtest_result)
            score = self.objective.score(metrics)
            valid = self.objective.is_valid(metrics)
            
            return SensitivityResult(
                params=params,
                metrics=metrics,
                score=score,
                valid=valid,
                params_id=self._generate_params_id(params),
            )
        finally:
            if original_params and strategy_overrides:
                try:
                    from app.quant.strategies import PARAMS_PATH
                    import yaml
                    with PARAMS_PATH.open("w") as fh:
                        yaml.dump(original_params, fh, default_flow_style=False)
                    from importlib import reload
                    import app.quant.strategies
                    reload(app.quant.strategies)
                except Exception as exc:
                    logger.warning("Failed to restore original params", extra={"error": str(exc)})

    def _deep_merge(self, base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in overrides.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _generate_params_id(self, params: dict[str, Any]) -> str:
        """Generate deterministic ID from parameters."""
        serialized = json.dumps(params, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode()).hexdigest()[:8]

    def analyze_dominance(
        self,
        results_df: pd.DataFrame,
        *,
        target_metric: str = "calmar",
        method: str = "anova",
    ) -> dict[str, Any]:
        """
        Analyze which parameters dominate performance variance.
        
        Args:
            results_df: DataFrame from run() method
            target_metric: Metric to analyze (default: "calmar")
            method: Analysis method ("anova" or "correlation")
            
        Returns:
            Dict with parameter importance scores and statistical tests
        """
        if results_df.empty or target_metric not in results_df.columns:
            return {"error": "Invalid results dataframe or target metric"}
        
        valid_df = results_df[results_df["valid"] == True].copy()
        if valid_df.empty:
            return {"error": "No valid results found"}
        
        param_cols = [c for c in valid_df.columns if c not in [
            "params_id", "calmar", "max_dd", "sharpe", "cagr", "win_rate",
            "profit_factor", "score", "valid", "total_trades",
            "longest_losing_streak", "risk_of_ruin",
        ]]
        
        if method == "anova":
            return self._anova_analysis(valid_df, param_cols, target_metric)
        elif method == "correlation":
            return self._correlation_analysis(valid_df, param_cols, target_metric)
        else:
            return {"error": f"Unsupported method: {method}"}

    def _anova_analysis(
        self,
        df: pd.DataFrame,
        param_cols: list[str],
        target_metric: str,
    ) -> dict[str, Any]:
        """ANOVA analysis to identify parameter dominance."""
        results = {
            "method": "anova",
            "target_metric": target_metric,
            "parameter_importance": {},
        }
        
        for param in param_cols:
            try:
                groups = [group[target_metric].values for name, group in df.groupby(param)]
                if len(groups) < 2:
                    continue
                
                f_stat, p_value = stats.f_oneway(*groups)
                
                means = df.groupby(param)[target_metric].mean()
                stds = df.groupby(param)[target_metric].std()
                
                results["parameter_importance"][param] = {
                    "f_statistic": float(f_stat),
                    "p_value": float(p_value),
                    "significant": p_value < 0.05,
                    "means": means.to_dict(),
                    "stds": stds.to_dict(),
                    "range": float(means.max() - means.min()),
                }
            except Exception as exc:
                logger.warning("ANOVA failed for parameter", extra={"param": param, "error": str(exc)})
        
        sorted_importance = sorted(
            results["parameter_importance"].items(),
            key=lambda x: x[1]["range"],
            reverse=True,
        )
        results["parameter_rank"] = [p[0] for p in sorted_importance]
        
        return results

    def _correlation_analysis(
        self,
        df: pd.DataFrame,
        param_cols: list[str],
        target_metric: str,
    ) -> dict[str, Any]:
        """Correlation analysis to identify parameter importance."""
        results = {
            "method": "correlation",
            "target_metric": target_metric,
            "parameter_importance": {},
        }
        
        for param in param_cols:
            try:
                param_values = pd.to_numeric(df[param], errors="coerce")
                metric_values = df[target_metric].values
                
                valid_mask = ~(param_values.isna() | np.isnan(metric_values))
                if valid_mask.sum() < 3:
                    continue
                
                corr, p_value = stats.pearsonr(param_values[valid_mask], metric_values[valid_mask])
                
                results["parameter_importance"][param] = {
                    "correlation": float(corr),
                    "p_value": float(p_value),
                    "significant": p_value < 0.05,
                    "abs_correlation": float(abs(corr)),
                }
            except Exception as exc:
                logger.warning("Correlation failed for parameter", extra={"param": param, "error": str(exc)})
        
        sorted_importance = sorted(
            results["parameter_importance"].items(),
            key=lambda x: x[1]["abs_correlation"],
            reverse=True,
        )
        results["parameter_rank"] = [p[0] for p in sorted_importance]
        
        return results

    def bootstrap_analysis(
        self,
        results_df: pd.DataFrame,
        *,
        target_metric: str = "calmar",
        n_bootstrap: int = 1000,
        confidence_level: float = 0.95,
    ) -> dict[str, Any]:
        """
        Bootstrap analysis to estimate parameter effect distributions.
        
        Args:
            results_df: DataFrame from run() method
            target_metric: Metric to analyze
            n_bootstrap: Number of bootstrap samples
            confidence_level: Confidence level for intervals
            
        Returns:
            Dict with bootstrap statistics and confidence intervals
        """
        if results_df.empty or target_metric not in results_df.columns:
            return {"error": "Invalid results dataframe or target metric"}
        
        valid_df = results_df[results_df["valid"] == True].copy()
        if valid_df.empty:
            return {"error": "No valid results found"}
        
        param_cols = [c for c in valid_df.columns if c not in [
            "params_id", "calmar", "max_dd", "sharpe", "cagr", "win_rate",
            "profit_factor", "score", "valid", "total_trades",
            "longest_losing_streak", "risk_of_ruin",
        ]]
        
        results = {
            "target_metric": target_metric,
            "n_bootstrap": n_bootstrap,
            "confidence_level": confidence_level,
            "parameter_effects": {},
        }
        
        rng = np.random.default_rng()
        
        for param in param_cols:
            try:
                unique_values = sorted(valid_df[param].unique())
                if len(unique_values) < 2:
                    continue
                
                bootstrap_effects = []
                metric_values = valid_df[target_metric].values
                
                for _ in range(n_bootstrap):
                    indices = rng.choice(len(valid_df), size=len(valid_df), replace=True)
                    bootstrap_df = valid_df.iloc[indices]
                    
                    group_means = bootstrap_df.groupby(param)[target_metric].mean()
                    if len(group_means) >= 2:
                        effect = float(group_means.max() - group_means.min())
                        bootstrap_effects.append(effect)
                
                if bootstrap_effects:
                    alpha = 1 - confidence_level
                    lower = np.percentile(bootstrap_effects, 100 * alpha / 2)
                    upper = np.percentile(bootstrap_effects, 100 * (1 - alpha / 2))
                    median = np.median(bootstrap_effects)
                    
                    results["parameter_effects"][param] = {
                        "median_effect": float(median),
                        "ci_lower": float(lower),
                        "ci_upper": float(upper),
                        "mean_effect": float(np.mean(bootstrap_effects)),
                        "std_effect": float(np.std(bootstrap_effects)),
                    }
            except Exception as exc:
                logger.warning("Bootstrap failed for parameter", extra={"param": param, "error": str(exc)})
        
        return results

    def identify_safe_zones(
        self,
        results_df: pd.DataFrame,
        *,
        target_metric: str = "calmar",
        min_score: float | None = None,
        max_dd_threshold: float = 15.0,
    ) -> dict[str, Any]:
        """
        Identify safe operating zones (parameter combinations with good performance).
        
        Args:
            results_df: DataFrame from run() method
            target_metric: Metric to optimize (default: "calmar")
            min_score: Minimum acceptable score (default: objective-dependent)
            max_dd_threshold: Maximum drawdown threshold (default: 15%)
            
        Returns:
            Dict with safe zones, parameter ranges, and recommendations
        """
        if results_df.empty or target_metric not in results_df.columns:
            return {"error": "Invalid results dataframe or target metric"}
        
        valid_df = results_df[
            (results_df["valid"] == True) &
            (results_df["max_dd"] <= max_dd_threshold)
        ].copy()
        
        if valid_df.empty:
            return {"error": "No valid results within constraints"}
        
        if min_score is None:
            min_score = valid_df[target_metric].quantile(0.5)
        
        safe_df = valid_df[valid_df[target_metric] >= min_score].copy()
        
        if safe_df.empty:
            return {"error": f"No results above minimum score {min_score}"}
        
        param_cols = [c for c in safe_df.columns if c not in [
            "params_id", "calmar", "max_dd", "sharpe", "cagr", "win_rate",
            "profit_factor", "score", "valid", "total_trades",
            "longest_losing_streak", "risk_of_ruin",
        ]]
        
        safe_zones = {}
        for param in param_cols:
            try:
                param_values = safe_df[param].values
                safe_zones[param] = {
                    "min": float(np.min(param_values)),
                    "max": float(np.max(param_values)),
                    "mean": float(np.mean(param_values)),
                    "median": float(np.median(param_values)),
                    "optimal_range": self._find_optimal_range(safe_df, param, target_metric),
                }
            except Exception:
                pass
        
        best_params = safe_df.loc[safe_df[target_metric].idxmax()].to_dict()
        
        return {
            "safe_zones": safe_zones,
            "best_params": {k: v for k, v in best_params.items() if k in param_cols},
            "best_metrics": {
                "calmar": float(best_params.get("calmar", 0.0)),
                "max_dd": float(best_params.get("max_dd", 0.0)),
                "sharpe": float(best_params.get("sharpe", 0.0)),
            },
            "min_score": min_score,
            "max_dd_threshold": max_dd_threshold,
            "safe_combinations_count": len(safe_df),
            "total_valid_count": len(valid_df),
        }

    def _find_optimal_range(
        self,
        df: pd.DataFrame,
        param: str,
        target_metric: str,
        percentile: float = 0.75,
    ) -> dict[str, float]:
        """Find optimal parameter range (top percentile of results)."""
        threshold = df[target_metric].quantile(percentile)
        top_df = df[df[target_metric] >= threshold]
        param_values = top_df[param].values
        
        return {
            "min": float(np.min(param_values)),
            "max": float(np.max(param_values)),
            "mean": float(np.mean(param_values)),
        }

    def export_results(
        self,
        results_df: pd.DataFrame,
        analysis: dict[str, Any],
        *,
        output_dir: Path | str = "data/sensitivity",
    ) -> dict[str, str]:
        """
        Export sensitivity analysis results to files.
        
        Args:
            results_df: DataFrame from run()
            analysis: Analysis results from analyze_dominance()
            output_dir: Output directory for files
            
        Returns:
            Dict with file paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        
        csv_path = output_path / f"sensitivity_results_{timestamp}.csv"
        results_df.to_csv(csv_path, index=False)
        
        json_path = output_path / f"sensitivity_analysis_{timestamp}.json"
        with json_path.open("w") as f:
            json.dump(analysis, f, indent=2, default=str)
        
        return {
            "results_csv": str(csv_path),
            "analysis_json": str(json_path),
        }

