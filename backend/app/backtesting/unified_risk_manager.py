"""Unified Risk Manager integrating sizing, drawdown, shutdown, and ruin simulation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.backtesting.auto_shutdown import AutoShutdownManager, AutoShutdownPolicy, StrategyMetrics
from app.backtesting.risk import RuinSimulator
from app.backtesting.risk_sizing import (
    AdaptiveRiskSizer,
    DrawdownController,
    RiskManager,
    RiskSizer,
)
from app.backtesting.volatility_targeting import CombinedSizer, KellySizer, VolatilityTargeting


@dataclass
class RiskMetrics:
    """Current risk metrics snapshot."""

    current_drawdown_pct: float
    peak_equity: float
    current_equity: float
    risk_of_ruin: float
    suggested_fraction: float  # Kelly fraction or risk fraction
    sizing_method: str
    last_update: datetime


class UnifiedRiskManager:
    """
    Unified Risk Manager providing centralized risk management operations.
    
    Integrates:
    - Position sizing (risk-based, Kelly, volatility targeting)
    - Drawdown tracking and adjustment
    - Auto-shutdown checks
    - Ruin simulation
    
    Provides unified interface:
    - size_trade: Calculate position size for a trade
    - update_drawdown: Update drawdown metrics
    - check_shutdown: Check if trading should be shut down
    - simulate_ruin: Estimate risk of ruin
    """

    def __init__(
        self,
        *,
        base_capital: float = 10000.0,
        risk_budget_pct: float = 1.0,
        max_drawdown_pct: float = 50.0,
        shutdown_policy: AutoShutdownPolicy | None = None,
        use_kelly: bool = False,
        kelly_cap: float = 0.5,
        volatility_targeting: bool = False,
        target_volatility: float = 0.10,
        ruin_threshold: float = 0.5,
        ruin_horizon: int = 250,
    ) -> None:
        """
        Initialize unified risk manager.
        
        Args:
            base_capital: Initial capital
            risk_budget_pct: Risk budget as percentage (default: 1.0%)
            max_drawdown_pct: Maximum drawdown for drawdown controller (default: 50%)
            shutdown_policy: Auto-shutdown policy (default: AutoShutdownPolicy())
            use_kelly: Enable Kelly sizing (default: False)
            kelly_cap: Kelly truncation cap (default: 0.5 = 50% of full Kelly)
            volatility_targeting: Enable volatility targeting (default: False)
            target_volatility: Target volatility for vol targeting (default: 0.10 = 10%)
            ruin_threshold: Ruin threshold (default: 0.5 = -50% drawdown)
            ruin_horizon: Ruin simulation horizon in trades (default: 250)
        """
        self.base_capital = base_capital
        self.current_equity = base_capital
        self.peak_equity = base_capital
        self.current_drawdown_pct = 0.0
        
        # Initialize sizing components
        self.risk_sizer = RiskSizer(risk_budget_pct=risk_budget_pct / 100.0)
        self.drawdown_controller = DrawdownController(max_drawdown_pct=max_drawdown_pct)
        self.risk_manager = RiskManager(
            risk_sizer=self.risk_sizer,
            drawdown_controller=self.drawdown_controller,
        )
        
        # Kelly sizing (optional)
        self.use_kelly = use_kelly
        self.kelly_sizer = KellySizer(kelly_cap=kelly_cap) if use_kelly else None
        
        # Volatility targeting (optional)
        self.volatility_targeting_enabled = volatility_targeting
        self.volatility_targeting = VolatilityTargeting(target_volatility=target_volatility) if volatility_targeting else None
        
        # Combined sizer (integrates all methods)
        self.combined_sizer = CombinedSizer(
            risk_sizer=self.risk_sizer,
            kelly_sizer=self.kelly_sizer,
            volatility_targeting=self.volatility_targeting,
        )
        
        # Auto-shutdown
        self.shutdown_policy = shutdown_policy or AutoShutdownPolicy()
        self.shutdown_manager = AutoShutdownManager(policy=self.shutdown_policy)
        
        # Ruin simulation
        self.ruin_simulator = RuinSimulator()
        self.ruin_threshold = ruin_threshold
        self.ruin_horizon = ruin_horizon
        
        # Trade history for ruin simulation
        self.trade_history: list[dict[str, Any]] = []
        
        # Current metrics
        self.current_metrics: RiskMetrics | None = None
        self.last_update = datetime.utcnow()

    def exposure_profile(self) -> float:
        """
        Return a realistic exposure multiplier [0, 1] based on current drawdown policy.
        
        This approximates the effective risk fraction after drawdown controls and size reduction.
        """
        # Base effective risk from drawdown controller
        dd_multiplier = self.drawdown_controller.risk_multiplier(self.current_drawdown_pct)
        # Size reduction from shutdown manager if active
        size_multiplier = self.shutdown_manager.get_size_multiplier() if self.shutdown_manager else 1.0
        # Risk budget fraction (already in decimals)
        base_risk_fraction = self.risk_sizer.risk_budget_pct
        effective_fraction = base_risk_fraction * dd_multiplier * size_multiplier
        # Clamp between 0 and 1
        return float(max(0.0, min(1.0, effective_fraction)))

    def size_trade(
        self,
        entry: float,
        stop: float,
        *,
        win_rate: float | None = None,
        payoff_ratio: float | None = None,
        realized_vol: float | None = None,
        regime_probabilities: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Calculate position size for a trade.
        
        Args:
            entry: Entry price
            stop: Stop loss price
            win_rate: Optional win rate for Kelly sizing
            payoff_ratio: Optional payoff ratio for Kelly sizing
            realized_vol: Optional realized volatility (annualized, e.g., 0.15 for 15%)
            regime_probabilities: Optional regime probabilities
            
        Returns:
            Dict with units, notional, risk_amount, sizing_method, and adjustments
        """
        if entry <= 0 or stop <= 0:
            return {
                "units": 0.0,
                "notional": 0.0,
                "risk_amount": 0.0,
                "sizing_method": "invalid",
                "error": "Invalid entry or stop price",
            }
        
        # Check shutdown status first
        shutdown_status = self.check_shutdown()
        if shutdown_status["shutdown"]:
            return {
                "units": 0.0,
                "notional": 0.0,
                "risk_amount": 0.0,
                "sizing_method": "shutdown",
                "error": shutdown_status["reason"],
            }
        
        # Get size reduction factor if active
        size_reduction = shutdown_status.get("size_reduction_factor", 1.0)
        
        # Convert volatility from percentage to decimal if needed
        if realized_vol is not None and realized_vol > 1.0:
            realized_vol = realized_vol / 100.0
        
        # Use combined sizer if Kelly or volatility targeting enabled
        if self.use_kelly or self.volatility_targeting_enabled:
            result = self.combined_sizer.compute_size(
                capital=self.current_equity,
                entry=entry,
                stop=stop,
                win_rate=win_rate if self.use_kelly else None,
                payoff_ratio=payoff_ratio if self.use_kelly else None,
                realized_vol=realized_vol if self.volatility_targeting_enabled else None,
                current_dd_pct=self.current_drawdown_pct,
                drawdown_controller=self.drawdown_controller,
                regime_probabilities=regime_probabilities,
            )
            
            units = result["units"]
            sizing_method = result["sizing_method"]
            adjustments = result.get("adjustments", {})
        else:
            # Standard risk-based sizing with drawdown adjustment
            units = self.risk_manager.compute_size(
                equity=self.current_equity,
                entry=entry,
                stop=stop,
                current_dd_pct=self.current_drawdown_pct,
            )
            sizing_method = "risk_with_drawdown"
            adjustments = {
                "drawdown_pct": self.current_drawdown_pct,
                "dd_multiplier": self.drawdown_controller.risk_multiplier(self.current_drawdown_pct),
            }
        
        # Apply size reduction if shutdown manager recommends it
        units = units * size_reduction
        
        # Calculate metrics
        notional = units * entry
        risk_per_unit = abs(entry - stop)
        risk_amount = units * risk_per_unit
        
        # Calculate suggested fraction (for metrics)
        suggested_fraction = (risk_amount / self.current_equity) if self.current_equity > 0 else 0.0
        
        # If Kelly was used, include Kelly fraction
        if self.use_kelly and win_rate and payoff_ratio:
            kelly_info = self.kelly_sizer.get_kelly_fraction(win_rate, payoff_ratio)
            suggested_fraction = max(suggested_fraction, kelly_info["applied_fraction"])
        
        return {
            "units": round(units, 8),
            "notional": round(notional, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_percentage": round((risk_amount / self.current_equity * 100.0) if self.current_equity > 0 else 0.0, 2),
            "sizing_method": sizing_method,
            "adjustments": adjustments,
            "suggested_fraction": round(suggested_fraction, 4),
            "size_reduction_factor": size_reduction,
        }

    def update_drawdown(self, current_equity: float, trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """
        Update drawdown metrics based on current equity.
        
        Args:
            current_equity: Current equity value
            trades: Optional list of trades for metrics calculation
            
        Returns:
            Dict with updated drawdown metrics
        """
        self.current_equity = current_equity
        
        # Update peak equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        # Calculate current drawdown
        if self.peak_equity > 0:
            self.current_drawdown_pct = ((self.peak_equity - current_equity) / self.peak_equity) * 100.0
        else:
            self.current_drawdown_pct = 100.0
        
        # Update trade history for ruin simulation
        if trades:
            self.trade_history = trades[-100:]  # Keep last 100 trades
        
        # Update metrics
        self.last_update = datetime.utcnow()
        
        # Calculate suggested fraction (risk budget adjusted by drawdown)
        effective_risk = self.risk_manager.get_effective_risk_budget(
            base_risk_budget_pct=self.risk_sizer.risk_budget_pct,
            current_dd_pct=self.current_drawdown_pct,
        )
        suggested_fraction = effective_risk
        
        # Calculate risk of ruin
        risk_of_ruin = self.simulate_ruin()
        
        self.current_metrics = RiskMetrics(
            current_drawdown_pct=self.current_drawdown_pct,
            peak_equity=self.peak_equity,
            current_equity=self.current_equity,
            risk_of_ruin=risk_of_ruin,
            suggested_fraction=suggested_fraction,
            sizing_method="risk_with_drawdown",
            last_update=self.last_update,
        )
        
        return {
            "current_drawdown_pct": round(self.current_drawdown_pct, 2),
            "peak_equity": round(self.peak_equity, 2),
            "current_equity": round(self.current_equity, 2),
            "risk_of_ruin": round(risk_of_ruin, 4),
            "suggested_fraction": round(suggested_fraction, 4),
            "last_update": self.last_update.isoformat(),
        }

    def check_shutdown(self) -> dict[str, Any]:
        """
        Check if trading should be shut down based on drawdown or performance.
        
        Returns:
            Dict with shutdown status, reason, and size reduction info
        """
        if not self.shutdown_manager:
            return {"shutdown": False, "reason": "no_shutdown_manager"}
        
        # Create strategy metrics for shutdown check
        metrics = StrategyMetrics(
            current_drawdown_pct=self.current_drawdown_pct,
            peak_equity=self.peak_equity,
            current_equity=self.current_equity,
            trades=self.trade_history if self.trade_history else None,
            equity_curve=None,  # Can be calculated from trade history if needed
        )
        
        # Evaluate shutdown
        self.shutdown_manager.evaluate(metrics)
        
        shutdown_active = self.shutdown_manager.is_shutdown_active()
        size_reduction_active = self.shutdown_manager.is_size_reduction_active()
        
        return {
            "shutdown": shutdown_active,
            "reason": self.shutdown_manager.get_shutdown_reason() if shutdown_active else None,
            "size_reduction": size_reduction_active,
            "size_reduction_factor": self.shutdown_manager.get_size_multiplier(),
            "size_reduction_reason": self.shutdown_manager.get_size_reduction_reason() if size_reduction_active else None,
        }

    def simulate_ruin(
        self,
        win_rate: float | None = None,
        payoff_ratio: float | None = None,
        threshold: float | None = None,
        horizon: int | None = None,
    ) -> float:
        """
        Estimate risk of ruin using Monte Carlo simulation.
        
        Args:
            win_rate: Optional win rate (if None, calculated from trade history)
            payoff_ratio: Optional payoff ratio (if None, calculated from trade history)
            threshold: Optional ruin threshold (default: self.ruin_threshold)
            horizon: Optional horizon in trades (default: self.ruin_horizon)
            
        Returns:
            Estimated probability of ruin (0.0 to 1.0)
        """
        threshold = threshold or self.ruin_threshold
        horizon = horizon or self.ruin_horizon
        
        # If trade history available, use it to estimate parameters
        if self.trade_history and len(self.trade_history) >= 10:
            try:
                return self.ruin_simulator.estimate_from_trades(
                    trades=self.trade_history,
                    horizon=horizon,
                    threshold=threshold,
                )
            except Exception:
                pass
        
        # If win_rate and payoff_ratio provided, use them
        if win_rate is not None and payoff_ratio is not None:
            return self.ruin_simulator.estimate(
                win_rate=win_rate,
                payoff_ratio=payoff_ratio,
                horizon=horizon,
                threshold=threshold,
            )
        
        # Default: return conservative estimate if no data
        return 0.0

    def get_metrics(self) -> RiskMetrics | None:
        """
        Get current risk metrics.
        
        Returns:
            RiskMetrics snapshot or None if not yet calculated
        """
        return self.current_metrics

    def reset(self, new_capital: float | None = None) -> None:
        """
        Reset risk manager state (e.g., after drawdown recovery or capital change).
        
        Args:
            new_capital: Optional new capital value (default: keep current equity)
        """
        if new_capital is not None:
            self.base_capital = new_capital
            self.current_equity = new_capital
        
        self.peak_equity = self.current_equity
        self.current_drawdown_pct = 0.0
        self.trade_history = []
        self.current_metrics = None
        
        if self.shutdown_manager:
            self.shutdown_manager.reset()
        
        self.last_update = datetime.utcnow()


