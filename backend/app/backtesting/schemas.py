"""Data schemas for backtesting outputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class BacktestSummary:
    start_date: datetime
    end_date: datetime
    trading_days: int
    cagr: float
    sharpe: float
    sortino: float
    profit_factor: float
    max_drawdown: float
    bh_cagr: float
    bh_sharpe: float
    bh_sortino: float
    bh_max_drawdown: float
    slippage_bps: int

