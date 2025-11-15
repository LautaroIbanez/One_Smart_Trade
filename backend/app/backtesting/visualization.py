"""Visualization utilities for sensitivity analysis (tornado charts, response surfaces)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import griddata


def plot_tornado_chart(
    analysis_results: dict[str, Any],
    *,
    target_metric: str = "calmar",
    top_n: int = 10,
    output_path: Path | str | None = None,
) -> None:
    """
    Generate tornado chart showing parameter importance.
    
    Args:
        analysis_results: Results from SensitivityRunner.analyze_dominance()
        target_metric: Metric being analyzed
        top_n: Number of top parameters to show
        output_path: Optional path to save figure
    """
    param_importance = analysis_results.get("parameter_importance", {})
    if not param_importance:
        return
    
    if analysis_results.get("method") == "anova":
        sorted_params = sorted(
            param_importance.items(),
            key=lambda x: x[1]["range"],
            reverse=True,
        )[:top_n]
        labels = [p[0] for p in sorted_params]
        values = [p[1]["range"] for p in sorted_params]
        title = f"Parameter Impact Range ({target_metric})"
    else:
        sorted_params = sorted(
            param_importance.items(),
            key=lambda x: x[1]["abs_correlation"],
            reverse=True,
        )[:top_n]
        labels = [p[0] for p in sorted_params]
        values = [p[1]["abs_correlation"] for p in sorted_params]
        title = f"Parameter Correlation ({target_metric})"
    
    if not labels:
        return
    
    fig, ax = plt.subplots(figsize=(8, max(6, len(labels) * 0.5)))
    y_pos = np.arange(len(labels))
    
    bars = ax.barh(y_pos, values, color="steelblue")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Impact" if analysis_results.get("method") == "anova" else "Absolute Correlation")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.3)
    
    for i, (bar, param_data) in enumerate(zip(bars, sorted_params)):
        significance = param_data[1].get("significant", False)
        if significance:
            bar.set_color("darkred")
            ax.text(
                values[i] * 0.02,
                i,
                "*",
                va="center",
                fontsize=14,
                fontweight="bold",
            )
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_response_surface(
    results_df: pd.DataFrame,
    param_x: str,
    param_y: str,
    *,
    target_metric: str = "calmar",
    output_path: Path | str | None = None,
    resolution: int = 50,
) -> None:
    """
    Generate 2D response surface showing interaction between two parameters.
    
    Args:
        results_df: DataFrame from SensitivityRunner.run()
        param_x: X-axis parameter name
        param_y: Y-axis parameter name
        target_metric: Metric to visualize
        output_path: Optional path to save figure
        resolution: Grid resolution for interpolation
    """
    if param_x not in results_df.columns or param_y not in results_df.columns:
        return
    
    if target_metric not in results_df.columns:
        return
    
    valid_df = results_df[results_df["valid"] == True].copy()
    if valid_df.empty:
        return
    
    try:
        x_vals = pd.to_numeric(valid_df[param_x], errors="coerce").values
        y_vals = pd.to_numeric(valid_df[param_y], errors="coerce").values
        z_vals = valid_df[target_metric].values
        
        valid_mask = ~(np.isnan(x_vals) | np.isnan(y_vals) | np.isnan(z_vals))
        if valid_mask.sum() < 3:
            return
        
        x_vals = x_vals[valid_mask]
        y_vals = y_vals[valid_mask]
        z_vals = z_vals[valid_mask]
        
        x_min, x_max = x_vals.min(), x_vals.max()
        y_min, y_max = y_vals.min(), y_vals.max()
        
        xi = np.linspace(x_min, x_max, resolution)
        yi = np.linspace(y_min, y_max, resolution)
        xi_grid, yi_grid = np.meshgrid(xi, yi)
        
        zi_grid = griddata(
            (x_vals, y_vals),
            z_vals,
            (xi_grid, yi_grid),
            method="cubic",
            fill_value=np.nan,
        )
        
        fig, ax = plt.subplots(figsize=(10, 8))
        contour = ax.contourf(xi_grid, yi_grid, zi_grid, levels=20, cmap="viridis")
        ax.scatter(x_vals, y_vals, c=z_vals, s=20, cmap="viridis", edgecolors="black", linewidths=0.5)
        ax.set_xlabel(param_x)
        ax.set_ylabel(param_y)
        ax.set_title(f"Response Surface: {target_metric} vs {param_x} and {param_y}")
        plt.colorbar(contour, ax=ax, label=target_metric)
        plt.tight_layout()
        
        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
    except Exception as exc:
        print(f"Failed to plot response surface: {exc}")


def plot_parameter_distributions(
    results_df: pd.DataFrame,
    param: str,
    *,
    target_metric: str = "calmar",
    output_path: Path | str | None = None,
) -> None:
    """
    Plot distribution of target metric for different parameter values.
    
    Args:
        results_df: DataFrame from SensitivityRunner.run()
        param: Parameter name to analyze
        target_metric: Metric to plot
        output_path: Optional path to save figure
    """
    if param not in results_df.columns or target_metric not in results_df.columns:
        return
    
    valid_df = results_df[results_df["valid"] == True].copy()
    if valid_df.empty:
        return
    
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        grouped = valid_df.groupby(param)[target_metric]
        unique_vals = sorted(valid_df[param].unique())
        
        means = [grouped.get_group(v).mean() for v in unique_vals]
        stds = [grouped.get_group(v).std() for v in unique_vals]
        counts = [len(grouped.get_group(v)) for v in unique_vals]
        
        ax.errorbar(
            unique_vals,
            means,
            yerr=stds,
            fmt="o-",
            capsize=5,
            capthick=2,
            label="Mean ± Std",
        )
        
        ax.fill_between(
            unique_vals,
            [m - s for m, s in zip(means, stds)],
            [m + s for m, s in zip(means, stds)],
            alpha=0.2,
            label="±1 Std",
        )
        
        ax.set_xlabel(param)
        ax.set_ylabel(target_metric)
        ax.set_title(f"{target_metric} Distribution by {param}")
        ax.grid(alpha=0.3)
        ax.legend()
        
        for i, (val, count) in enumerate(zip(unique_vals, counts)):
            ax.text(val, means[i], f"n={count}", ha="center", va="bottom", fontsize=8)
        
        plt.tight_layout()
        
        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
    except Exception as exc:
        print(f"Failed to plot parameter distribution: {exc}")


