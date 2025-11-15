"""Risk-based position sizing based on equity and stop loss distance."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RiskSizer:
    """
    Position sizing based on fixed risk percentage of equity.
    
    Calculates position size such that the maximum loss (difference between
    entry and stop loss) equals a fixed percentage of equity.
    
    Example:
        If equity = $10,000, risk_budget_pct = 0.01 (1%), entry = $50,000,
        stop = $48,000:
        - risk_per_unit = $50,000 - $48,000 = $2,000
        - risk_budget = $10,000 * 0.01 = $100
        - units = $100 / $2,000 = 0.05 BTC
    """

    risk_budget_pct: float = 0.01
    min_size: float = 0.001
    max_size: float | None = None

    def compute_size(
        self,
        equity: float,
        entry: float,
        stop: float,
    ) -> float:
        """
        Calculate position size based on risk percentage.
        
        Args:
            equity: Current equity/capital
            entry: Entry price
            stop: Stop loss price
            
        Returns:
            Position size in units (e.g., BTC amount)
        """
        if equity <= 0 or entry <= 0:
            return 0.0
        
        # Calculate risk per unit
        risk_per_unit = abs(entry - stop)
        if risk_per_unit == 0:
            return 0.0
        
        # Calculate risk budget (amount to risk)
        risk_budget = equity * self.risk_budget_pct
        
        # Calculate units: risk_budget / risk_per_unit
        units = risk_budget / risk_per_unit
        
        # Apply minimum size
        units = max(units, self.min_size)
        
        # Apply maximum size if configured
        if self.max_size is not None:
            units = min(units, self.max_size)
        
        return float(units)

    def compute_notional(self, units: float, price: float) -> float:
        """
        Calculate notional value of position.
        
        Args:
            units: Position size in units
            price: Price per unit
            
        Returns:
            Notional value (units * price)
        """
        return float(units * price)

    def compute_risk_amount(self, units: float, entry: float, stop: float) -> float:
        """
        Calculate actual risk amount for position.
        
        Args:
            units: Position size in units
            entry: Entry price
            stop: Stop loss price
            
        Returns:
            Risk amount (units * |entry - stop|)
        """
        risk_per_unit = abs(entry - stop)
        return float(units * risk_per_unit)

    def validate_size(self, units: float, equity: float, entry: float, stop: float) -> tuple[bool, str]:
        """
        Validate that position size respects risk budget.
        
        Args:
            units: Position size in units
            equity: Current equity
            entry: Entry price
            stop: Stop loss price
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if units < self.min_size:
            return False, f"Size {units} below minimum {self.min_size}"
        
        if self.max_size is not None and units > self.max_size:
            return False, f"Size {units} above maximum {self.max_size}"
        
        risk_amount = self.compute_risk_amount(units, entry, stop)
        risk_pct = risk_amount / equity if equity > 0 else 0.0
        
        if risk_pct > self.risk_budget_pct * 1.1:  # Allow 10% tolerance
            return False, f"Risk {risk_pct:.2%} exceeds budget {self.risk_budget_pct:.2%}"
        
        return True, "valid"


class AdaptiveRiskSizer:
    """
    Risk-based position sizing with adaptive risk budget based on regime.
    
    Adjusts risk_budget_pct based on market regime probabilities.
    """

    def __init__(
        self,
        base_risk_pct: float = 0.01,
        calm_multiplier: float = 1.5,
        balanced_multiplier: float = 1.0,
        stress_multiplier: float = 0.5,
        min_size: float = 0.001,
        max_size: float | None = None,
    ) -> None:
        """
        Initialize adaptive risk sizer.
        
        Args:
            base_risk_pct: Base risk percentage (applied in balanced regime)
            calm_multiplier: Multiplier for calm regime (e.g., 1.5 = 1.5% risk)
            balanced_multiplier: Multiplier for balanced regime (1.0 = base risk)
            stress_multiplier: Multiplier for stress regime (e.g., 0.5 = 0.5% risk)
            min_size: Minimum position size
            max_size: Maximum position size (None = no limit)
        """
        self.base_risk_pct = base_risk_pct
        self.calm_multiplier = calm_multiplier
        self.balanced_multiplier = balanced_multiplier
        self.stress_multiplier = stress_multiplier
        self.min_size = min_size
        self.max_size = max_size

    def compute_size(
        self,
        equity: float,
        entry: float,
        stop: float,
        regime_probabilities: dict[str, float] | None = None,
    ) -> float:
        """
        Calculate position size with adaptive risk budget.
        
        Args:
            equity: Current equity/capital
            entry: Entry price
            stop: Stop loss price
            regime_probabilities: Dict with regime probabilities (calm, balanced, stress)
            
        Returns:
            Position size in units
        """
        # Calculate adaptive risk budget
        if regime_probabilities:
            calm_prob = regime_probabilities.get("calm", 0.0)
            balanced_prob = regime_probabilities.get("balanced", 0.0)
            stress_prob = regime_probabilities.get("stress", 0.0)
            
            risk_multiplier = (
                calm_prob * self.calm_multiplier +
                balanced_prob * self.balanced_multiplier +
                stress_prob * self.stress_multiplier
            )
            risk_budget_pct = self.base_risk_pct * risk_multiplier
        else:
            risk_budget_pct = self.base_risk_pct
        
        # Use base RiskSizer with adaptive risk budget
        sizer = RiskSizer(
            risk_budget_pct=risk_budget_pct,
            min_size=self.min_size,
            max_size=self.max_size,
        )
        
        return sizer.compute_size(equity, entry, stop)


class DrawdownController:
    """
    Dynamic risk reduction based on current drawdown.
    
    Adjusts risk budget percentage based on drawdown using formula:
    risk_multiplier = 1.0 - (current_dd_pct / 50.0)
    
    Example:
        If current drawdown = 0%: multiplier = 1.0 (100% of base risk)
        If current drawdown = 25%: multiplier = 0.5 (50% of base risk)
        If current drawdown = 50%: multiplier = 0.0 (0% of base risk, stops trading)
    """

    def __init__(self, max_drawdown_pct: float = 50.0) -> None:
        """
        Initialize drawdown controller.
        
        Args:
            max_drawdown_pct: Maximum drawdown percentage at which risk is reduced to 0
                             (default: 50%)
        """
        self.max_drawdown_pct = max_drawdown_pct

    def risk_multiplier(self, current_dd_pct: float) -> float:
        """
        Calculate risk multiplier based on current drawdown.
        
        Formula: multiplier = 1.0 - (current_dd_pct / max_drawdown_pct)
        Clipped between 0.0 and 1.0 to avoid negative values.
        
        Args:
            current_dd_pct: Current drawdown as percentage (e.g., 25.0 for 25%)
            
        Returns:
            Risk multiplier (0.0 to 1.0)
        """
        if self.max_drawdown_pct <= 0:
            return 1.0
        
        multiplier = 1.0 - (current_dd_pct / self.max_drawdown_pct)
        return float(np.clip(multiplier, 0.0, 1.0))

    def adjusted_risk_budget(
        self,
        base_risk_budget_pct: float,
        current_dd_pct: float,
    ) -> float:
        """
        Calculate adjusted risk budget based on drawdown.
        
        Args:
            base_risk_budget_pct: Base risk budget percentage (e.g., 0.01 for 1%)
            current_dd_pct: Current drawdown as percentage
            
        Returns:
            Adjusted risk budget percentage
        """
        multiplier = self.risk_multiplier(current_dd_pct)
        return float(base_risk_budget_pct * multiplier)


class RiskManager:
    """
    Combined risk management system integrating RiskSizer with DrawdownController.
    
    Recalculates effective position size based on:
    1. Base risk budget (from RiskSizer)
    2. Drawdown-adjusted multiplier (from DrawdownController)
    3. Optionally regime probabilities (for AdaptiveRiskSizer)
    """

    def __init__(
        self,
        risk_sizer: RiskSizer | AdaptiveRiskSizer,
        drawdown_controller: DrawdownController | None = None,
    ) -> None:
        """
        Initialize risk manager.
        
        Args:
            risk_sizer: Risk sizing system (standard or adaptive)
            drawdown_controller: Optional drawdown controller for dynamic risk reduction
        """
        self.risk_sizer = risk_sizer
        self.drawdown_controller = drawdown_controller or DrawdownController()

    def compute_size(
        self,
        equity: float,
        entry: float,
        stop: float,
        current_dd_pct: float = 0.0,
        regime_probabilities: dict[str, float] | None = None,
    ) -> float:
        """
        Calculate position size with drawdown-adjusted risk budget.
        
        Args:
            equity: Current equity/capital
            entry: Entry price
            stop: Stop loss price
            current_dd_pct: Current drawdown as percentage
            regime_probabilities: Optional regime probabilities for adaptive sizing
            
        Returns:
            Position size in units
        """
        if isinstance(self.risk_sizer, AdaptiveRiskSizer):
            # AdaptiveRiskSizer manages its own risk budget adjustment
            # But we still apply drawdown multiplier
            base_risk_pct = self.risk_sizer.base_risk_pct
            
            # Apply regime-based adjustment first
            if regime_probabilities:
                calm_prob = regime_probabilities.get("calm", 0.0)
                balanced_prob = regime_probabilities.get("balanced", 0.0)
                stress_prob = regime_probabilities.get("stress", 0.0)
                
                risk_multiplier_regime = (
                    calm_prob * self.risk_sizer.calm_multiplier +
                    balanced_prob * self.risk_sizer.balanced_multiplier +
                    stress_prob * self.risk_sizer.stress_multiplier
                )
                adjusted_risk_pct = base_risk_pct * risk_multiplier_regime
            else:
                adjusted_risk_pct = base_risk_pct
            
            # Apply drawdown multiplier
            drawdown_multiplier = self.drawdown_controller.risk_multiplier(current_dd_pct)
            final_risk_pct = adjusted_risk_pct * drawdown_multiplier
            
            # Use base RiskSizer with adjusted risk budget
            sizer = RiskSizer(
                risk_budget_pct=final_risk_pct,
                min_size=self.risk_sizer.min_size,
                max_size=self.risk_sizer.max_size,
            )
            return sizer.compute_size(equity, entry, stop)
        else:
            # Standard RiskSizer: apply drawdown multiplier to base risk budget
            base_risk_pct = self.risk_sizer.risk_budget_pct
            adjusted_risk_pct = self.drawdown_controller.adjusted_risk_budget(
                base_risk_pct,
                current_dd_pct,
            )
            
            # Create temporary sizer with adjusted risk budget
            sizer = RiskSizer(
                risk_budget_pct=adjusted_risk_pct,
                min_size=self.risk_sizer.min_size,
                max_size=self.risk_sizer.max_size,
            )
            return sizer.compute_size(equity, entry, stop)

    def get_effective_risk_budget(
        self,
        base_risk_budget_pct: float,
        current_dd_pct: float,
        regime_probabilities: dict[str, float] | None = None,
    ) -> float:
        """
        Get effective risk budget after all adjustments.
        
        Args:
            base_risk_budget_pct: Base risk budget percentage
            current_dd_pct: Current drawdown as percentage
            regime_probabilities: Optional regime probabilities
            
        Returns:
            Effective risk budget percentage
        """
        # Apply regime adjustment if adaptive
        if isinstance(self.risk_sizer, AdaptiveRiskSizer) and regime_probabilities:
            calm_prob = regime_probabilities.get("calm", 0.0)
            balanced_prob = regime_probabilities.get("balanced", 0.0)
            stress_prob = regime_probabilities.get("stress", 0.0)
            
            risk_multiplier_regime = (
                calm_prob * self.risk_sizer.calm_multiplier +
                balanced_prob * self.risk_sizer.balanced_multiplier +
                stress_prob * self.risk_sizer.stress_multiplier
            )
            adjusted_risk_pct = base_risk_budget_pct * risk_multiplier_regime
        else:
            adjusted_risk_pct = base_risk_budget_pct
        
        # Apply drawdown multiplier
        drawdown_multiplier = self.drawdown_controller.risk_multiplier(current_dd_pct)
        return float(adjusted_risk_pct * drawdown_multiplier)

