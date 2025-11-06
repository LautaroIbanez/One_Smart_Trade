"""Backtesting engine with commission and slippage modeling."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from app.data.curation import DataCuration
from app.quant.signal_engine import generate_signal
from app.quant.strategies import momentum_strategy, mean_reversion_strategy, breakout_strategy, volatility_strategy
from app.quant import indicators as ind
from app.core.logging import logger


class BacktestEngine:
    """Backtesting engine with realistic trade execution."""

    COMMISSION_RATE = 0.001  # 0.1% per trade (Binance spot)
    SLIPPAGE_RATE = 0.0005  # 0.05% slippage

    def __init__(self, commission: float = COMMISSION_RATE, slippage: float = SLIPPAGE_RATE):
        self.commission = commission
        self.slippage = slippage
        self.curation = DataCuration()

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to entry/exit price."""
        if side == "BUY":
            return price * (1 + self.slippage)
        return price * (1 - self.slippage)

    def _apply_commission(self, notional: float) -> float:
        """Apply commission to trade."""
        return notional * self.commission

    def _execute_trade(
        self, entry_price: float, exit_price: float, side: str, size: float
    ) -> Dict[str, float]:
        """Execute a trade with slippage and commission."""
        entry_exec = self._apply_slippage(entry_price, side)
        exit_exec = self._apply_slippage(exit_price, "SELL" if side == "BUY" else "BUY")

        if side == "BUY":
            cost = entry_exec * size
            revenue = exit_exec * size
        else:
            revenue = entry_exec * size
            cost = exit_exec * size

        commission_entry = self._apply_commission(cost)
        commission_exit = self._apply_commission(revenue)

        pnl = revenue - cost - commission_entry - commission_exit
        return_pct = (pnl / cost) * 100 if cost > 0 else 0.0

        return {
            "pnl": pnl,
            "return_pct": return_pct,
            "entry_price": entry_exec,
            "exit_price": exit_exec,
            "commission": commission_entry + commission_exit,
        }

    def run_backtest(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        position_size_pct: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Run backtest over date range (supports 5+ years of data).
        
        Args:
            start_date: Start date for backtest
            end_date: End date for backtest
            initial_capital: Starting capital
            position_size_pct: Position size as percentage of capital
            
        Returns:
            Dict with trades, equity_curve, and metadata, or error dict
        """
        # Load historical data for the date range
        df_1d = self.curation.get_historical_curated("1d", start_date=start_date, end_date=end_date)
        if df_1d is None or df_1d.empty:
            return {
                "error": "No historical data available",
                "error_type": "NO_DATA",
                "details": f"No curated 1d data found for range {start_date.date()} to {end_date.date()}"
            }

        # Ensure we have enough data (at least 200 days for indicators)
        if len(df_1d) < 200:
            return {
                "error": f"Insufficient data: only {len(df_1d)} days available, need at least 200",
                "error_type": "INSUFFICIENT_DATA",
                "details": f"Found {len(df_1d)} rows, minimum 200 required for reliable indicators"
            }

        # Load 1h data for signal generation (use historical if available, otherwise latest)
        df_1h = self.curation.get_historical_curated("1h", start_date=start_date, end_date=end_date)
        if df_1h is None or df_1h.empty:
            # Fallback to latest curated 1h data
            df_1h = self.curation.get_latest_curated("1h")
            if df_1h is None or df_1h.empty:
                # Last resort: use 1d data
                df_1h = df_1d.copy()
                logger.warning("Using 1d data as fallback for 1h signals")

        trades: List[Dict[str, Any]] = []
        equity_curve: List[float] = [initial_capital]
        current_position: Optional[Dict[str, Any]] = None
        capital = initial_capital

        for i in range(1, len(df_1d)):
            current_row = df_1d.iloc[i]
            prev_row = df_1d.iloc[i - 1]

            # Generate signal for previous day
            df_slice = df_1d.iloc[:i]
            df_h_slice = df_1h[df_1h["open_time"] <= prev_row["open_time"]]

            try:
                signal_data = generate_signal(df_h_slice, df_slice)
            except Exception as e:
                logger.debug(f"Error generating signal at index {i}: {e}")
                continue

            signal = signal_data["signal"]
            entry_range = signal_data["entry_range"]
            sl_tp = signal_data["stop_loss_take_profit"]

            # Close position if SL/TP hit
            if current_position:
                pos = current_position
                current_price = current_row["close"]
                exit_reason = None

                if pos["side"] == "BUY":
                    if current_price <= pos["stop_loss"]:
                        exit_reason = "SL"
                        exit_price = pos["stop_loss"]
                    elif current_price >= pos["take_profit"]:
                        exit_reason = "TP"
                        exit_price = pos["take_profit"]
                else:  # SELL
                    if current_price >= pos["stop_loss"]:
                        exit_reason = "SL"
                        exit_price = pos["stop_loss"]
                    elif current_price <= pos["take_profit"]:
                        exit_reason = "TP"
                        exit_price = pos["take_profit"]

                if exit_reason:
                    exec_result = self._execute_trade(
                        pos["entry_price"], exit_price, pos["side"], pos["size"]
                    )
                    capital += exec_result["pnl"]

                    trades.append(
                        {
                            "entry_time": pos["entry_time"],
                            "exit_time": current_row["open_time"],
                            "side": pos["side"],
                            "entry_price": exec_result["entry_price"],
                            "exit_price": exec_result["exit_price"],
                            "pnl": exec_result["pnl"],
                            "return_pct": exec_result["return_pct"],
                            "exit_reason": exit_reason,
                            "commission": exec_result["commission"],
                        }
                    )
                    current_position = None

            # Open new position if signal and no position
            if not current_position and signal in ("BUY", "SELL"):
                entry_price = entry_range["optimal"]
                size = (capital * position_size_pct) / entry_price

                current_position = {
                    "entry_time": current_row["open_time"],
                    "entry_price": entry_price,
                    "side": signal,
                    "size": size,
                    "stop_loss": sl_tp["stop_loss"],
                    "take_profit": sl_tp["take_profit"],
                }

            equity_curve.append(capital)

        # Close any open position at end
        if current_position:
            last_price = df_1d.iloc[-1]["close"]
            exec_result = self._execute_trade(
                current_position["entry_price"], last_price, current_position["side"], current_position["size"]
            )
            capital += exec_result["pnl"]
            trades.append(
                {
                    "entry_time": current_position["entry_time"],
                    "exit_time": df_1d.iloc[-1]["open_time"],
                    "side": current_position["side"],
                    "entry_price": exec_result["entry_price"],
                    "exit_price": exec_result["exit_price"],
                    "pnl": exec_result["pnl"],
                    "return_pct": exec_result["return_pct"],
                    "exit_reason": "END",
                    "commission": exec_result["commission"],
                }
            )

        # Store first and last prices for Buy & Hold calculation
        first_price = float(df_1d.iloc[0]["close"]) if not df_1d.empty else 0.0
        last_price = float(df_1d.iloc[-1]["close"]) if not df_1d.empty else 0.0

        return {
            "trades": trades,
            "equity_curve": equity_curve,
            "final_capital": capital,
            "initial_capital": initial_capital,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "first_price": first_price,  # For Buy & Hold calculation
            "last_price": last_price,    # For Buy & Hold calculation
        }

