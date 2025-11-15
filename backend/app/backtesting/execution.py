"""Execution modelling utilities for dynamic slippage and partial fills."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass(slots=True)
class VolumeLiquidityModel:
    """Estimate available depth using volume and order book hints."""

    min_depth: float = 1_000.0
    volume_scale: float = 0.4

    def depth(self, bar: Any) -> float:
        bids = float(bar.get("bid_depth", 0.0) or 0.0)
        asks = float(bar.get("ask_depth", 0.0) or 0.0)
        if bids or asks:
            return max(self.min_depth, bids + asks)
        volume = float(bar.get("volume", 0.0) or 0.0)
        return max(self.min_depth, volume * self.volume_scale)


@dataclass(slots=True)
class ExecutionModel:
    """Dynamic slippage model accounting for volatility, depth and gaps."""

    liquidity_model: VolumeLiquidityModel
    base_bps: float = 5.0
    vol_coeff: float = 40.0
    depth_coeff: float = 0.00004
    gap_threshold: float = 0.01
    gap_penalty: float = 0.002

    def vol_estimator(self, bar: Any) -> float:
        for key in ("atr", "atr_14", "realized_vol_7", "realized_vol_90", "volatility_30"):
            value = bar.get(key)
            if value is not None:
                return max(0.0, float(value))
        return 0.02

    def price_impact(self, bar: Any, side: str, notional: float) -> float:
        vol = self.vol_estimator(bar)
        depth = self.liquidity_model.depth(bar)
        depth_term = (notional / max(depth, 1.0)) * self.depth_coeff
        slip_bps = self.base_bps + self.vol_coeff * vol + depth_term
        return slip_bps / 10_000

    def simulate_fill(self, target_price: float, gap_open: float, side: str) -> Tuple[float, float]:
        if abs(gap_open) >= self.gap_threshold:
            direction = 1 if (gap_open > 0 and side == "BUY") or (gap_open < 0 and side == "SELL") else -1
            adjusted = target_price * (1 + direction * self.gap_penalty)
            return adjusted, 0.6
        return target_price, 1.0

    def adjust_price(
        self,
        bar: Any,
        side: str,
        target_price: float,
        notional: float,
        gap_open: float,
    ) -> Tuple[float, float]:
        impact = self.price_impact(bar, side, abs(notional))
        if side == "BUY":
            impacted_price = target_price * (1 + impact)
        else:
            impacted_price = target_price * (1 - impact)
        return self.simulate_fill(impacted_price, gap_open, side)



