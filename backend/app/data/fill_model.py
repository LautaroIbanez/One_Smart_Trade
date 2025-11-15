"""Probabilistic fill model and slippage estimation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.data.orderbook import OrderBookSnapshot


@dataclass
class FillModelConfig:
    """Configuration for fill model parameters."""

    alpha: float = 0.001  # Impact coefficient (linear impact term)
    beta: float = 0.5  # Volatility coefficient (volatility impact term)
    gamma: float = 1.0  # Depth weighting factor
    impact_type: str = "linear"  # "linear" or "exponential"
    depth_metric_method: str = "notional_at_spread"  # "notional_at_spread", "cumulative_depth", "effective_depth"


class FillModel:
    """
    Probabilistic fill model that estimates execution probability and slippage.
    
    Combines spread, order book depth, and intraday volatility to estimate:
    - Probability of full fill at each price level
    - Expected slippage for given order size
    """

    def __init__(
        self,
        *,
        alpha: float = 0.001,
        beta: float = 0.5,
        gamma: float = 1.0,
        impact_type: str = "linear",
        depth_metric_method: str = "notional_at_spread",
    ) -> None:
        """
        Initialize fill model.
        
        Args:
            alpha: Impact coefficient for market impact (default: 0.001)
            beta: Volatility coefficient for volatility impact (default: 0.5)
            gamma: Depth weighting factor (default: 1.0)
            impact_type: "linear" or "exponential" impact function (default: "linear")
            depth_metric_method: Method for calculating depth metric:
                - "notional_at_spread": Notional value at spread levels
                - "cumulative_depth": Cumulative quantity within spread
                - "effective_depth": Weighted depth considering price levels
        """
        self.config = FillModelConfig(
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            impact_type=impact_type,
            depth_metric_method=depth_metric_method,
        )

    def depth_metric(self, book: OrderBookSnapshot, side: str) -> float:
        """
        Calculate depth metric for given side.
        
        Args:
            book: Order book snapshot
            side: "buy" or "sell"
            
        Returns:
            Depth metric value (higher = more liquidity)
        """
        if self.config.depth_metric_method == "notional_at_spread":
            # Calculate notional value at best bid/ask
            if side.lower() == "buy":
                if not book.asks:
                    return 0.0
                # Sum notional of first few levels (within 2x spread)
                spread = book.spread or 0.0
                if spread == 0:
                    return 0.0
                threshold = book.best_ask + (2 * spread)
                notional = 0.0
                for price, qty in book.asks:
                    if price > threshold:
                        break
                    notional += price * qty
                return notional
            else:  # sell
                if not book.bids:
                    return 0.0
                spread = book.spread or 0.0
                if spread == 0:
                    return 0.0
                threshold = book.best_bid - (2 * spread)
                notional = 0.0
                for price, qty in book.bids:
                    if price < threshold:
                        break
                    notional += price * qty
                return notional
        
        elif self.config.depth_metric_method == "cumulative_depth":
            # Sum of quantities within spread
            spread = book.spread or 0.0
            if spread == 0:
                return 0.0
            
            if side.lower() == "buy":
                # Cumulative quantity of asks within spread
                depth = 0.0
                threshold = book.best_ask + (2 * spread)
                for price, qty in book.asks:
                    if price > threshold:
                        break
                    depth += qty
                return depth
            else:  # sell
                depth = 0.0
                threshold = book.best_bid - (2 * spread)
                for price, qty in book.bids:
                    if price < threshold:
                        break
                    depth += qty
                return depth
        
        else:  # effective_depth
            # Weighted depth (closer levels weighted more)
            mid = book.mid_price or 0.0
            if mid == 0:
                return 0.0
            
            if side.lower() == "buy":
                depth = 0.0
                for i, (price, qty) in enumerate(book.asks):
                    # Weight decreases with distance from best ask
                    weight = 1.0 / (1.0 + i * 0.1)
                    depth += price * qty * weight
                return depth
            else:  # sell
                depth = 0.0
                for i, (price, qty) in enumerate(book.bids):
                    weight = 1.0 / (1.0 + i * 0.1)
                    depth += price * qty * weight
                return depth

    def market_impact(self, notional: float, depth: float) -> float:
        """
        Calculate market impact based on order size and depth.
        
        Args:
            notional: Order notional value
            depth: Available depth metric
            
        Returns:
            Market impact coefficient (0.0 to 1.0+)
        """
        if depth <= 0:
            return 1.0  # No liquidity, maximum impact
        
        impact_ratio = notional / depth
        
        if self.config.impact_type == "linear":
            return impact_ratio
        else:  # exponential
            return 1.0 - np.exp(-impact_ratio)

    def expected_slippage(
        self,
        side: str,
        notional: float,
        book: OrderBookSnapshot,
        vol_est: float,
    ) -> float:
        """
        Calculate expected slippage for an order.
        
        Formula:
            slippage = spread_term + alpha * impact + beta * vol_est
        
        Where:
            spread_term = (best_ask - best_bid) / mid_price
            impact = notional / depth_metric(book, side)
            vol_est = volatility estimate (typically in %)
        
        Args:
            side: "buy" or "sell"
            notional: Order notional value (price * quantity)
            book: Order book snapshot
            vol_est: Volatility estimate (as decimal, e.g., 0.02 for 2%)
            
        Returns:
            Expected slippage as percentage (e.g., 0.05 for 5 bps)
        """
        if book.mid_price is None or book.mid_price == 0:
            return 0.0
        
        # Spread term: half-spread as percentage
        spread = book.spread or 0.0
        spread_term = (spread / book.mid_price) / 2.0  # Half-spread for one side
        
        # Impact term: market impact based on order size
        depth = self.depth_metric(book, side)
        impact = self.market_impact(notional, depth)
        impact_term = self.config.alpha * impact
        
        # Volatility term: volatility impact
        vol_term = self.config.beta * vol_est
        
        # Total expected slippage
        expected_slippage = spread_term + impact_term + vol_term
        
        # Apply gamma weighting if needed
        if self.config.gamma != 1.0:
            expected_slippage = expected_slippage * self.config.gamma
        
        return max(0.0, expected_slippage)  # Ensure non-negative

    def fill_probability(
        self,
        side: str,
        notional: float,
        book: OrderBookSnapshot,
        target_price: float | None = None,
        *,
        vol_est: float = 0.0,
    ) -> dict[str, Any]:
        """
        Calculate probability of getting filled at target price or better.
        
        Args:
            side: "buy" or "sell"
            notional: Order notional value
            book: Order book snapshot
            target_price: Target execution price (if None, uses best bid/ask)
            vol_est: Volatility estimate for slippage calculation
            
        Returns:
            Dict with fill probability, expected price, and slippage metrics
        """
        if target_price is None:
            if side.lower() == "buy":
                target_price = book.best_ask
            else:
                target_price = book.best_bid
        
        if target_price is None or book.mid_price is None:
            return {
                "fill_probability": 0.0,
                "expected_price": None,
                "expected_slippage_pct": 0.0,
                "expected_slippage_bps": 0.0,
            }
        
        # Calculate expected slippage
        expected_slippage_pct = self.expected_slippage(side, notional, book, vol_est)
        expected_slippage_bps = expected_slippage_pct * 10000  # Convert to basis points
        
        # Calculate expected execution price
        if side.lower() == "buy":
            # Buy orders execute at ask + slippage
            expected_price = target_price * (1.0 + expected_slippage_pct)
        else:
            # Sell orders execute at bid - slippage
            expected_price = target_price * (1.0 - expected_slippage_pct)
        
        # Calculate fill probability based on depth
        depth = self.depth_metric(book, side)
        required_qty = notional / target_price if target_price > 0 else 0.0
        
        # Probability decreases as required quantity approaches available depth
        if depth > 0:
            utilization_ratio = required_qty / (depth / target_price if target_price > 0 else 1.0)
            # Exponential decay: high probability if utilization < 20%, low if > 80%
            fill_probability = max(0.0, min(1.0, np.exp(-utilization_ratio * 2.0)))
        else:
            fill_probability = 0.0
        
        # Adjust probability based on volatility (higher vol = lower fill probability)
        if vol_est > 0:
            vol_adjustment = 1.0 - (vol_est * self.config.beta)
            fill_probability = fill_probability * max(0.0, vol_adjustment)
        
        return {
            "fill_probability": float(fill_probability),
            "expected_price": float(expected_price) if expected_price else None,
            "target_price": float(target_price),
            "expected_slippage_pct": float(expected_slippage_pct),
            "expected_slippage_bps": float(expected_slippage_bps),
            "utilization_ratio": float(utilization_ratio) if depth > 0 else 1.0,
            "depth_metric": float(depth),
        }

    def partial_fill_probability(
        self,
        side: str,
        notional: float,
        book: OrderBookSnapshot,
        fill_ratio: float,
        *,
        vol_est: float = 0.0,
    ) -> float:
        """
        Calculate probability of getting at least fill_ratio of the order filled.
        
        Args:
            side: "buy" or "sell"
            notional: Total order notional value
            book: Order book snapshot
            fill_ratio: Minimum fill ratio (0.0 to 1.0)
            vol_est: Volatility estimate
            
        Returns:
            Probability of getting at least fill_ratio filled
        """
        partial_notional = notional * fill_ratio
        result = self.fill_probability(side, partial_notional, book, vol_est=vol_est)
        return result["fill_probability"]

    def optimal_order_split(
        self,
        side: str,
        total_notional: float,
        book: OrderBookSnapshot,
        *,
        vol_est: float = 0.0,
        max_splits: int = 5,
        min_split_size: float = 100.0,
    ) -> list[dict[str, Any]]:
        """
        Calculate optimal order splitting to minimize slippage.
        
        Args:
            side: "buy" or "sell"
            total_notional: Total order notional value
            book: Order book snapshot
            vol_est: Volatility estimate
            max_splits: Maximum number of splits
            min_split_size: Minimum size per split
            
        Returns:
            List of split orders with expected slippage for each
        """
        if total_notional <= min_split_size:
            # Single order
            slippage = self.expected_slippage(side, total_notional, book, vol_est)
            return [
                {
                    "split": 1,
                    "notional": total_notional,
                    "expected_slippage_pct": slippage,
                    "expected_slippage_bps": slippage * 10000,
                }
            ]
        
        # Calculate optimal split sizes (weighted by depth)
        splits = []
        remaining_notional = total_notional
        depth = self.depth_metric(book, side)
        
        # Simple strategy: split based on available depth
        split_size = max(min_split_size, min(remaining_notional / max_splits, depth * 0.2))
        
        split_num = 1
        while remaining_notional > 0 and split_num <= max_splits:
            current_split = min(split_size, remaining_notional)
            slippage = self.expected_slippage(side, current_split, book, vol_est)
            
            splits.append({
                "split": split_num,
                "notional": current_split,
                "expected_slippage_pct": slippage,
                "expected_slippage_bps": slippage * 10000,
            })
            
            remaining_notional -= current_split
            split_num += 1
        
        # Calculate weighted average slippage
        total_weighted_slippage = sum(s["expected_slippage_pct"] * s["notional"] for s in splits)
        avg_slippage = total_weighted_slippage / total_notional if total_notional > 0 else 0.0
        
        return {
            "splits": splits,
            "total_notional": total_notional,
            "weighted_avg_slippage_pct": avg_slippage,
            "weighted_avg_slippage_bps": avg_slippage * 10000,
            "single_order_slippage_pct": self.expected_slippage(side, total_notional, book, vol_est),
            "slippage_reduction_pct": max(0.0, self.expected_slippage(side, total_notional, book, vol_est) - avg_slippage),
        }


@dataclass
class FillSimulationResult:
    """Result of fill simulation."""

    filled_notional: float
    avg_fill_price: float
    total_slippage_pct: float
    total_slippage_bps: float
    fill_ratio: float
    partial_fills: list[dict[str, Any]]


class FillSimulator:
    """Simulate order execution across order book levels."""

    def __init__(self, fill_model: FillModel) -> None:
        """
        Initialize fill simulator.
        
        Args:
            fill_model: FillModel instance for slippage estimation
        """
        self.fill_model = fill_model

    def simulate_execution(
        self,
        side: str,
        notional: float,
        book: OrderBookSnapshot,
        *,
        vol_est: float = 0.0,
    ) -> FillSimulationResult:
        """
        Simulate order execution across order book levels.
        
        Args:
            side: "buy" or "sell"
            notional: Order notional value
            book: Order book snapshot
            vol_est: Volatility estimate
            
        Returns:
            FillSimulationResult with execution details
        """
        if book.mid_price is None:
            return FillSimulationResult(
                filled_notional=0.0,
                avg_fill_price=0.0,
                total_slippage_pct=0.0,
                total_slippage_bps=0.0,
                fill_ratio=0.0,
                partial_fills=[],
            )
        
        remaining_notional = notional
        filled_notional = 0.0
        total_cost = 0.0
        partial_fills = []
        
        if side.lower() == "buy":
            # Execute against asks (ascending price)
            for price, qty in book.asks:
                if remaining_notional <= 0:
                    break
                
                level_notional = price * qty
                fill_notional = min(remaining_notional, level_notional)
                fill_qty = fill_notional / price
                
                filled_notional += fill_notional
                total_cost += fill_notional
                remaining_notional -= fill_notional
                
                partial_fills.append({
                    "price": price,
                    "quantity": fill_qty,
                    "notional": fill_notional,
                    "level": len(partial_fills) + 1,
                })
        else:  # sell
            # Execute against bids (descending price)
            for price, qty in book.bids:
                if remaining_notional <= 0:
                    break
                
                level_notional = price * qty
                fill_notional = min(remaining_notional, level_notional)
                fill_qty = fill_notional / price
                
                filled_notional += fill_notional
                total_cost += fill_notional
                remaining_notional -= fill_notional
                
                partial_fills.append({
                    "price": price,
                    "quantity": fill_qty,
                    "notional": fill_notional,
                    "level": len(partial_fills) + 1,
                })
        
        # Calculate average fill price
        avg_fill_price = total_cost / filled_notional if filled_notional > 0 else book.mid_price
        
        # Calculate slippage
        if side.lower() == "buy":
            reference_price = book.best_ask
        else:
            reference_price = book.best_bid
        
        if reference_price and reference_price > 0:
            total_slippage_pct = abs((avg_fill_price - reference_price) / reference_price)
        else:
            total_slippage_pct = 0.0
        
        total_slippage_bps = total_slippage_pct * 10000
        fill_ratio = filled_notional / notional if notional > 0 else 0.0
        
        return FillSimulationResult(
            filled_notional=filled_notional,
            avg_fill_price=avg_fill_price,
            total_slippage_pct=total_slippage_pct,
            total_slippage_bps=total_slippage_bps,
            fill_ratio=fill_ratio,
            partial_fills=partial_fills,
        )


