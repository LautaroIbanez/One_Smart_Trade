"""Guard to evaluate parameter sensitivity and stability before champion promotion."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from app.core.logging import logger


class StabilityStatus(str, Enum):
    """Stability assessment status."""

    STABLE = "STABLE"
    UNSTABLE = "UNSTABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class StabilityReport:
    """Report from stability evaluation."""

    status: StabilityStatus
    campaign_id: str
    base_calmar: float | None = None
    base_sharpe: float | None = None
    base_max_dd: float | None = None
    
    # Degradation metrics
    max_calmar_degradation_pct: float | None = None
    max_sharpe_degradation_pct: float | None = None
    max_dd_increase_pct: float | None = None
    
    # Variance metrics
    calmar_std: float | None = None
    sharpe_std: float | None = None
    max_dd_std: float | None = None
    
    # ANOVA results
    anova_p_value: float | None = None
    anova_significant: bool | None = None
    
    # Reasons for rejection
    rejection_reasons: list[str] = None
    
    def __post_init__(self):
        if self.rejection_reasons is None:
            self.rejection_reasons = []


class SensitivityGuard:
    """
    Evaluates parameter sensitivity and stability from sensitivity analysis results.
    
    Validates that strategies remain stable under ±20% parameter variations before
    champion promotion.
    """

    def __init__(
        self,
        *,
        max_degradation_pct: float = 20.0,
        max_dd_increase_pct: float = 25.0,
        min_sharpe_threshold: float = 1.0,
        anova_alpha: float = 0.05,
        min_valid_runs: int = 10,
    ) -> None:
        """
        Initialize sensitivity guard.
        
        Args:
            max_degradation_pct: Maximum allowed degradation in Calmar/Sharpe (default: 20%)
            max_dd_increase_pct: Maximum allowed increase in max drawdown (default: 25%)
            min_sharpe_threshold: Minimum Sharpe ratio threshold (default: 1.0)
            anova_alpha: Significance level for ANOVA test (default: 0.05)
            min_valid_runs: Minimum number of valid runs required (default: 10)
        """
        self.max_degradation_pct = max_degradation_pct
        self.max_dd_increase_pct = max_dd_increase_pct
        self.min_sharpe_threshold = min_sharpe_threshold
        self.anova_alpha = anova_alpha
        self.min_valid_runs = min_valid_runs

    def evaluate(
        self,
        results_df: pd.DataFrame,
        campaign_id: str | None = None,
        base_params_id: str | None = None,
    ) -> StabilityReport:
        """
        Evaluate stability from sensitivity analysis results.
        
        Args:
            results_df: DataFrame from SensitivityRunner.run() with columns:
                - params_id, calmar, sharpe, max_dd, valid, and parameter columns
            campaign_id: Optional campaign ID for reporting
            base_params_id: Optional params_id of the base configuration
                (if None, uses the params_id with best calmar)
        
        Returns:
            StabilityReport with status and detailed metrics
        """
        if results_df.empty:
            return StabilityReport(
                status=StabilityStatus.INSUFFICIENT_DATA,
                campaign_id=campaign_id or "unknown",
                rejection_reasons=["No results provided"],
            )
        
        # Filter valid results
        valid_df = results_df[results_df.get("valid", True) == True].copy()
        
        if len(valid_df) < self.min_valid_runs:
            return StabilityReport(
                status=StabilityStatus.INSUFFICIENT_DATA,
                campaign_id=campaign_id or "unknown",
                rejection_reasons=[f"Insufficient valid runs: {len(valid_df)} < {self.min_valid_runs}"],
            )
        
        # Identify base configuration
        if base_params_id is None:
            # Use the configuration with best Calmar as base
            base_idx = valid_df["calmar"].idxmax()
            base_params_id = valid_df.loc[base_idx, "params_id"]
        else:
            base_idx = valid_df[valid_df["params_id"] == base_params_id].index
            if len(base_idx) == 0:
                logger.warning(f"Base params_id {base_params_id} not found, using best Calmar")
                base_idx = valid_df["calmar"].idxmax()
                base_params_id = valid_df.loc[base_idx, "params_id"]
            else:
                base_idx = base_idx[0]
        
        base_metrics = {
            "calmar": valid_df.loc[base_idx, "calmar"],
            "sharpe": valid_df.loc[base_idx, "sharpe"],
            "max_dd": valid_df.loc[base_idx, "max_dd"],
        }
        
        # Calculate degradation metrics
        calmar_degradations = ((base_metrics["calmar"] - valid_df["calmar"]) / base_metrics["calmar"]) * 100
        sharpe_degradations = ((base_metrics["sharpe"] - valid_df["sharpe"]) / base_metrics["sharpe"]) * 100
        dd_increases = ((valid_df["max_dd"] - base_metrics["max_dd"]) / base_metrics["max_dd"]) * 100
        
        max_calmar_degradation = calmar_degradations.max()
        max_sharpe_degradation = sharpe_degradations.max()
        max_dd_increase = dd_increases.max()
        
        # Calculate variance metrics
        calmar_std = valid_df["calmar"].std()
        sharpe_std = valid_df["sharpe"].std()
        max_dd_std = valid_df["max_dd"].std()
        
        # ANOVA analysis on Calmar
        anova_p_value, anova_significant = self._anova_analysis(valid_df, "calmar")
        
        # Build rejection reasons
        rejection_reasons = []
        
        if max_calmar_degradation > self.max_degradation_pct:
            rejection_reasons.append(
                f"Calmar degradation exceeds threshold: {max_calmar_degradation:.2f}% > {self.max_degradation_pct}%"
            )
        
        if max_sharpe_degradation > self.max_degradation_pct:
            rejection_reasons.append(
                f"Sharpe degradation exceeds threshold: {max_sharpe_degradation:.2f}% > {self.max_degradation_pct}%"
            )
        
        if max_dd_increase > self.max_dd_increase_pct:
            rejection_reasons.append(
                f"Max DD increase exceeds threshold: {max_dd_increase:.2f}% > {self.max_dd_increase_pct}%"
            )
        
        if (valid_df["sharpe"] < self.min_sharpe_threshold).any():
            min_sharpe = valid_df["sharpe"].min()
            rejection_reasons.append(
                f"Some variations have Sharpe < {self.min_sharpe_threshold}: min={min_sharpe:.3f}"
            )
        
        if anova_significant:
            rejection_reasons.append(
                f"ANOVA indicates excessive sensitivity (p={anova_p_value:.4f} < {self.anova_alpha})"
            )
        
        # Determine status
        if rejection_reasons:
            status = StabilityStatus.UNSTABLE
        else:
            status = StabilityStatus.STABLE
        
        return StabilityReport(
            status=status,
            campaign_id=campaign_id or "unknown",
            base_calmar=base_metrics["calmar"],
            base_sharpe=base_metrics["sharpe"],
            base_max_dd=base_metrics["max_dd"],
            max_calmar_degradation_pct=max_calmar_degradation,
            max_sharpe_degradation_pct=max_sharpe_degradation,
            max_dd_increase_pct=max_dd_increase,
            calmar_std=calmar_std,
            sharpe_std=sharpe_std,
            max_dd_std=max_dd_std,
            anova_p_value=anova_p_value,
            anova_significant=anova_significant,
            rejection_reasons=rejection_reasons,
        )

    def _anova_analysis(self, df: pd.DataFrame, target_metric: str) -> tuple[float, bool]:
        """
        Perform ANOVA analysis to detect excessive parameter sensitivity.
        
        Groups results by each parameter and tests if parameter values significantly
        affect the target metric.
        
        Args:
            df: DataFrame with results
            target_metric: Metric to analyze (e.g., "calmar")
            
        Returns:
            Tuple of (p_value, is_significant)
        """
        # Get parameter columns (exclude metric and metadata columns)
        exclude_cols = {
            "params_id", "calmar", "max_dd", "sharpe", "cagr", "win_rate",
            "profit_factor", "score", "valid", "total_trades",
            "longest_losing_streak", "risk_of_ruin", "campaign_id",
            "base_params", "start_date", "end_date", "created_at",
        }
        param_cols = [c for c in df.columns if c not in exclude_cols]
        
        if not param_cols:
            return 1.0, False
        
        # Perform ANOVA for each parameter
        min_p_value = 1.0
        for param in param_cols:
            try:
                # Group by parameter value
                groups = [group[target_metric].values for name, group in df.groupby(param)]
                if len(groups) < 2:
                    continue
                
                # Filter out groups with < 2 observations
                groups = [g for g in groups if len(g) >= 2]
                if len(groups) < 2:
                    continue
                
                f_stat, p_value = stats.f_oneway(*groups)
                min_p_value = min(min_p_value, p_value)
            except Exception as exc:
                logger.warning(f"ANOVA failed for parameter {param}: {exc}")
                continue
        
        is_significant = min_p_value < self.anova_alpha
        return min_p_value, is_significant

    def load_and_evaluate(
        self,
        results_path: Path | str,
        campaign_id: str | None = None,
        base_params_id: str | None = None,
    ) -> StabilityReport:
        """
        Load results from file and evaluate stability.
        
        Args:
            results_path: Path to parquet file with sensitivity results
            campaign_id: Optional campaign ID
            base_params_id: Optional base params_id
            
        Returns:
            StabilityReport
        """
        path = Path(results_path)
        if not path.exists():
            return StabilityReport(
                status=StabilityStatus.INSUFFICIENT_DATA,
                campaign_id=campaign_id or "unknown",
                rejection_reasons=[f"Results file not found: {path}"],
            )
        
        try:
            df = pd.read_parquet(path)
            if campaign_id is None and "campaign_id" in df.columns:
                campaign_id = df["campaign_id"].iloc[0]
            return self.evaluate(df, campaign_id=campaign_id, base_params_id=base_params_id)
        except Exception as exc:
            logger.exception(f"Failed to load and evaluate results from {path}")
            return StabilityReport(
                status=StabilityStatus.INSUFFICIENT_DATA,
                campaign_id=campaign_id or "unknown",
                rejection_reasons=[f"Failed to load results: {exc}"],
            )

