"""Volatility targeting and Kelly criterion position sizing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.backtesting.risk_sizing import RiskSizer


@dataclass
class VolatilityTargeting:
    """
    Volatility targeting to scale position size to maintain target volatility.
    
    Adjusts position size so that portfolio volatility matches a target level.
    """

    target_volatility: float = 0.10  # 10% annualized
    min_scale: float = 0.1  # Minimum scale factor (10% of base)
    max_scale: float = 2.0  # Maximum scale factor (200% of base)

    def adjust_units(
        self,
        base_units: float,
        realized_vol: float,
    ) -> float:
        """
        Adjust position size to target volatility.
        
        Formula: adjusted_units = base_units * (target_vol / realized_vol)
        
        Args:
            base_units: Base position size in units
            realized_vol: Realized volatility (annualized, e.g., 0.15 for 15%)
            
        Returns:
            Adjusted position size in units
        """
        if realized_vol <= 0 or base_units <= 0:
            return base_units
        
        scale = self.target_volatility / realized_vol
        scale_clamped = np.clip(scale, self.min_scale, self.max_scale)
        
        return float(base_units * scale_clamped)

    def get_scale_factor(
        self,
        realized_vol: float,
    ) -> float:
        """
        Get volatility adjustment scale factor without applying to units.
        
        Args:
            realized_vol: Realized volatility (annualized)
            
        Returns:
            Scale factor (clamped between min_scale and max_scale)
        """
        if realized_vol <= 0:
            return 1.0
        
        scale = self.target_volatility / realized_vol
        return float(np.clip(scale, self.min_scale, self.max_scale))


@dataclass
class KellySizer:
    """
    Kelly criterion position sizing with truncation for safety.
    
    Calculates optimal position size using Kelly criterion, but applies
    truncation (e.g., 50% of full Kelly) to avoid over-leveraging.
    """

    kelly_cap: float = 0.5  # Maximum Kelly fraction (50% of full Kelly)
    max_fraction: float = 0.25  # Absolute maximum position size (25% of capital)

    def truncated_fraction(
        self,
        win_rate: float,
        payoff_ratio: float,
        cap: float | None = None,
    ) -> float:
        """
        Calculate truncated Kelly fraction.
        
        Formula: kelly = win_rate - (1 - win_rate) / payoff_ratio
        Then: truncated = clip(kelly, 0.0, cap * kelly) with absolute max
        
        Args:
            win_rate: Win rate (0.0 to 1.0)
            payoff_ratio: Average win / Average loss (e.g., 2.0)
            cap: Optional override for kelly_cap (default: self.kelly_cap)
            
        Returns:
            Truncated Kelly fraction (0.0 to max_fraction)
        """
        if win_rate <= 0 or win_rate >= 1 or payoff_ratio <= 0:
            return 0.0
        
        # Calculate full Kelly
        kelly_full = win_rate - (1 - win_rate) / payoff_ratio
        
        if kelly_full <= 0:
            return 0.0
        
        # Apply truncation cap
        cap_value = cap if cap is not None else self.kelly_cap
        kelly_truncated = kelly_full * cap_value
        
        # Apply absolute maximum
        return float(np.clip(kelly_truncated, 0.0, self.max_fraction))

    def compute_size(
        self,
        capital: float,
        win_rate: float,
        payoff_ratio: float,
        entry: float,
        cap: float | None = None,
    ) -> float:
        """
        Calculate position size using truncated Kelly criterion.
        
        Args:
            capital: Available capital
            win_rate: Win rate (0.0 to 1.0)
            payoff_ratio: Average win / Average loss
            entry: Entry price
            cap: Optional override for kelly_cap
            
        Returns:
            Position size in units
        """
        if capital <= 0 or entry <= 0:
            return 0.0
        
        kelly_fraction = self.truncated_fraction(win_rate, payoff_ratio, cap)
        
        # Position size as fraction of capital
        notional = capital * kelly_fraction
        units = notional / entry
        
        return float(units)

    def get_kelly_fraction(
        self,
        win_rate: float,
        payoff_ratio: float,
        cap: float | None = None,
    ) -> dict[str, float]:
        """
        Get Kelly fraction information (full and truncated).
        
        Args:
            win_rate: Win rate
            payoff_ratio: Payoff ratio
            cap: Optional truncation cap
            
        Returns:
            Dict with full_kelly, truncated_kelly, and applied_fraction
        """
        if win_rate <= 0 or win_rate >= 1 or payoff_ratio <= 0:
            return {
                "full_kelly": 0.0,
                "truncated_kelly": 0.0,
                "applied_fraction": 0.0,
            }
        
        full_kelly = win_rate - (1 - win_rate) / payoff_ratio
        cap_value = cap if cap is not None else self.kelly_cap
        
        if full_kelly <= 0:
            truncated_kelly = 0.0
        else:
            truncated_kelly = full_kelly * cap_value
        
        applied_fraction = float(np.clip(truncated_kelly, 0.0, self.max_fraction))
        
        return {
            "full_kelly": float(full_kelly),
            "truncated_kelly": float(truncated_kelly),
            "applied_fraction": applied_fraction,
        }


class CombinedSizer:
    """
    Combined position sizing system integrating risk-based, Kelly, and volatility targeting.
    
    Applies sizing methods in sequence:
    1. Base sizing (risk-based or Kelly)
    2. Volatility targeting adjustment
    3. Drawdown adjustment (if applicable)
    """

    def __init__(
        self,
        risk_sizer=None,  # RiskSizer or None
        kelly_sizer: KellySizer | None = None,
        volatility_targeting: VolatilityTargeting | None = None,
    ) -> None:
        """
        Initialize combined sizer.
        
        Args:
            risk_sizer: Optional RiskSizer for risk-based sizing
            kelly_sizer: Optional KellySizer for Kelly criterion sizing
            volatility_targeting: Optional VolatilityTargeting for vol adjustment
        """
        self.risk_sizer = risk_sizer
        self.kelly_sizer = kelly_sizer or KellySizer()
        self.volatility_targeting = volatility_targeting or VolatilityTargeting()

    def compute_size(
        self,
        capital: float,
        entry: float,
        stop: float,
        *,
        win_rate: float | None = None,
        payoff_ratio: float | None = None,
        realized_vol: float | None = None,
        current_dd_pct: float = 0.0,
        drawdown_controller=None,
        regime_probabilities: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Calculate position size using combined methods.
        
        Args:
            capital: Available capital
            entry: Entry price
            stop: Stop loss price
            win_rate: Optional win rate for Kelly sizing
            payoff_ratio: Optional payoff ratio for Kelly sizing
            realized_vol: Optional realized volatility for vol targeting
            current_dd_pct: Current drawdown percentage
            drawdown_controller: Optional DrawdownController
            regime_probabilities: Optional regime probabilities
            
        Returns:
            Dict with units, sizing method, and adjustments applied
        """
        base_units = 0.0
        sizing_method = "unknown"
        
        # Step 1: Calculate base size (risk-based or Kelly)
        if self.risk_sizer is not None:
            # Use risk-based sizing
            if isinstance(self.risk_sizer, RiskSizer):
                risk_budget_pct = self.risk_sizer.risk_budget_pct
                
                # Apply drawdown adjustment if available
                if drawdown_controller and current_dd_pct > 0:
                    from app.backtesting.risk_sizing import RiskManager
                    risk_manager = RiskManager(
                        risk_sizer=self.risk_sizer,
                        drawdown_controller=drawdown_controller,
                    )
                    base_units = risk_manager.compute_size(
                        equity=capital,
                        entry=entry,
                        stop=stop,
                        current_dd_pct=current_dd_pct,
                    )
                    sizing_method = "risk_with_drawdown"
                else:
                    base_units = self.risk_sizer.compute_size(
                        equity=capital,
                        entry=entry,
                        stop=stop,
                    )
                    sizing_method = "risk_based"
        
        # If Kelly parameters provided, can use Kelly instead or combine
        if win_rate is not None and payoff_ratio is not None:
            kelly_units = self.kelly_sizer.compute_size(
                capital=capital,
                win_rate=win_rate,
                payoff_ratio=payoff_ratio,
                entry=entry,
            )
            
            # Use Kelly if risk_sizer not provided, or take minimum for safety
            if self.risk_sizer is None:
                base_units = kelly_units
                sizing_method = "kelly_truncated"
            else:
                # Use minimum of risk-based and Kelly for conservative sizing
                base_units = min(base_units, kelly_units)
                sizing_method = "risk_kelly_min"
        
        if base_units <= 0:
            return {
                "units": 0.0,
                "notional": 0.0,
                "sizing_method": "none",
                "adjustments": {},
            }
        
        # Step 2: Apply volatility targeting if volatility provided
        vol_adjusted_units = base_units
        vol_scale = 1.0
        if realized_vol is not None and realized_vol > 0:
            vol_scale = self.volatility_targeting.get_scale_factor(realized_vol)
            vol_adjusted_units = self.volatility_targeting.adjust_units(
                base_units,
                realized_vol,
            )
            sizing_method += "_vol_adjusted"
        
        # Step 3: Final drawdown adjustment (additional safety layer)
        final_units = vol_adjusted_units
        if drawdown_controller and current_dd_pct > 0:
            dd_multiplier = drawdown_controller.risk_multiplier(current_dd_pct)
            final_units = vol_adjusted_units * dd_multiplier
            sizing_method += "_dd_adjusted"
        
        notional = final_units * entry
        
        adjustments = {
            "base_units": round(base_units, 8),
            "vol_scale": round(vol_scale, 4),
            "vol_adjusted_units": round(vol_adjusted_units, 8),
        }
        
        if current_dd_pct > 0 and drawdown_controller:
            adjustments["drawdown_pct"] = round(current_dd_pct, 2)
            adjustments["dd_multiplier"] = round(
                drawdown_controller.risk_multiplier(current_dd_pct),
                4,
            )
            adjustments["final_units"] = round(final_units, 8)
        
        return {
            "units": round(final_units, 8),
            "notional": round(notional, 2),
            "sizing_method": sizing_method,
            "adjustments": adjustments,
        }

