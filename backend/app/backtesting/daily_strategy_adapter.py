"""Adapter to wrap DailySignalEngine as StrategyProtocol for backtesting."""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.backtesting.engine import StrategyProtocol
from app.core.logging import logger
from app.quant.signal_engine import DailySignalEngine
from app.utils.seeding import generate_deterministic_seed


class DailyStrategyAdapter:
    """
    Adapter that wraps DailySignalEngine to implement StrategyProtocol.
    
    This allows the daily signal engine to be used in backtesting by converting
    the bar-by-bar context into the format expected by DailySignalEngine.
    """
    
    def __init__(
        self,
        signal_engine: DailySignalEngine,
        df_1h: pd.DataFrame,
        df_1d: pd.DataFrame,
        seed: int | None = None,
        symbol: str = "BTCUSDT",
        data_metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize the adapter.
        
        Args:
            signal_engine: The DailySignalEngine instance to wrap
            df_1h: Hourly dataframe (will be sliced per bar)
            df_1d: Daily dataframe (will be sliced per bar)
            seed: Optional fallback seed (only used if date-based seed cannot be derived).
                  If None, seed will be derived from timestamp in on_bar().
            symbol: Trading symbol for seed generation (default: "BTCUSDT")
            data_metadata: Optional metadata about data freshness/staleness from SignalDataProvider
        """
        self.signal_engine = signal_engine
        self.df_1h_full = df_1h.copy()
        self.df_1d_full = df_1d.copy()
        self.fallback_seed = seed  # Renamed to clarify it's only a fallback
        self.symbol = symbol
        self.data_metadata = data_metadata  # Store metadata about data freshness/staleness
        
        # Ensure dataframes have timestamp index
        if not isinstance(self.df_1h_full.index, pd.DatetimeIndex):
            if "timestamp" in self.df_1h_full.columns:
                self.df_1h_full["timestamp"] = pd.to_datetime(self.df_1h_full["timestamp"])
                self.df_1h_full = self.df_1h_full.set_index("timestamp")
        if not isinstance(self.df_1d_full.index, pd.DatetimeIndex):
            if "timestamp" in self.df_1d_full.columns:
                self.df_1d_full["timestamp"] = pd.to_datetime(self.df_1d_full["timestamp"])
                self.df_1d_full = self.df_1d_full.set_index("timestamp")
    
    def on_bar(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Generate signal from bar context (StrategyProtocol interface).
        
        Args:
            context: Bar context with 'bar' (Series with timestamp index), 'equity', 'drawdown', etc.
        
        Returns:
            Signal dict with 'action' (BUY/SELL/HOLD), 'entry', 'stop_loss', 'take_profit'
        """
        # Extract timestamp from bar Series (index) or context
        bar = context.get("bar")
        if bar is not None and hasattr(bar, "name") and bar.name is not None:
            timestamp = pd.to_datetime(bar.name)
            # Ensure timestamp is timezone-aware UTC
            if isinstance(timestamp, pd.Timestamp):
                if timestamp.tz is None:
                    timestamp = timestamp.tz_localize("UTC")
                else:
                    timestamp = timestamp.tz_convert("UTC")
        elif "timestamp" in context and context["timestamp"] is not None:
            timestamp = pd.to_datetime(context["timestamp"])
            # Ensure timestamp is timezone-aware UTC
            if isinstance(timestamp, pd.Timestamp):
                if timestamp.tz is None:
                    timestamp = timestamp.tz_localize("UTC")
                else:
                    timestamp = timestamp.tz_convert("UTC")
        else:
            # Fallback: return HOLD if no timestamp available
            return {"action": "hold"}
        
        # Derive seed from timestamp (date) to match production behavior
        # This ensures the same date produces the same seed in both backtest and production
        try:
            # Extract date from timestamp
            if hasattr(timestamp, "date"):
                date_obj = timestamp.date()
            elif hasattr(timestamp, "to_pydatetime"):
                date_obj = timestamp.to_pydatetime().date()
            else:
                # Fallback: try to parse as string
                date_obj = pd.to_datetime(str(timestamp)).date()
            
            # Generate deterministic seed from date (same as production)
            daily_seed = generate_deterministic_seed(date_obj, self.symbol)
        except Exception:
            # If date extraction fails, use fallback seed or let engine generate it
            daily_seed = self.fallback_seed
        
        # Slice dataframes up to current timestamp
        # Ensure timestamp comparison works with timezone-aware indices
        df_1h = self.df_1h_full[self.df_1h_full.index <= timestamp].copy()
        df_1d = self.df_1d_full[self.df_1d_full.index <= timestamp].copy()
        
        # Check if data is stale based on metadata
        if self.data_metadata and self.data_metadata.get("status") == "stale_or_missing":
            reason = "stale_data"
            logger.warning(
                "Stale data detected in DailyStrategyAdapter",
                extra={
                    "reason": reason,
                    "current_timestamp": timestamp.isoformat() if isinstance(timestamp, pd.Timestamp) else str(timestamp),
                    "metadata": self.data_metadata,
                    "data_status": self.data_metadata.get("status"),
                },
            )
            return {
                "action": "hold",
                "reason": reason,
                "data_status": self.data_metadata.get("status"),
                "metadata": self.data_metadata,
            }
        
        # Need at least some data to generate signal
        if df_1h.empty or df_1d.empty:
            # Determine which dataset is empty and get last available date
            reason = None
            empty_dataset = None
            last_available_date = None
            
            if df_1h.empty and df_1d.empty:
                reason = "empty_df_1h_and_df_1d"
                empty_dataset = "both"
                # Get last available date from full dataframes
                if not self.df_1h_full.empty:
                    last_available_date = self.df_1h_full.index.max()
                elif not self.df_1d_full.empty:
                    last_available_date = self.df_1d_full.index.max()
            elif df_1h.empty:
                reason = "empty_df_1h"
                empty_dataset = "df_1h"
                last_available_date = self.df_1h_full.index.max() if not self.df_1h_full.empty else None
            elif df_1d.empty:
                reason = "empty_df_1d"
                empty_dataset = "df_1d"
                last_available_date = self.df_1d_full.index.max() if not self.df_1d_full.empty else None
            
            # Log the empty dataset condition
            logger.warning(
                "Empty dataset detected in DailyStrategyAdapter",
                extra={
                    "empty_dataset": empty_dataset,
                    "reason": reason,
                    "current_timestamp": timestamp.isoformat() if isinstance(timestamp, pd.Timestamp) else str(timestamp),
                    "last_available_date": last_available_date.isoformat() if last_available_date is not None and hasattr(last_available_date, "isoformat") else str(last_available_date),
                    "df_1h_empty": df_1h.empty,
                    "df_1d_empty": df_1d.empty,
                    "df_1h_full_rows": len(self.df_1h_full),
                    "df_1d_full_rows": len(self.df_1d_full),
                },
            )
            
            return {
                "action": "hold",
                "reason": reason,
                "empty_dataset": empty_dataset,
                "last_available_date": last_available_date.isoformat() if last_available_date is not None and hasattr(last_available_date, "isoformat") else str(last_available_date),
            }
        
        # Generate signal using DailySignalEngine with date-based seed
        # This ensures same confidence for same date in both backtest and production
        try:
            signal = self.signal_engine.generate(df_1h, df_1d, seed=daily_seed)
            
            # Convert to backtest format
            signal_type = signal.get("signal", "HOLD")
            entry_range = signal.get("entry_range", {})
            sl_tp = signal.get("stop_loss_take_profit", {})
            entry_price = entry_range.get("optimal", context.get("close", 0))
            stop_loss = sl_tp.get("stop_loss", 0)
            take_profit = sl_tp.get("take_profit", 0)
            
            # Convert signal type to backtest action
            # BacktestEngine expects: "enter", "exit", "stop_loss", "take_profit", "trailing_stop", "adjust", or empty dict for HOLD
            if signal_type == "BUY":
                return {
                    "action": "enter",
                    "side": "BUY",
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "confidence": signal.get("confidence", 0.0),
                }
            elif signal_type == "SELL":
                return {
                    "action": "enter",
                    "side": "SELL",
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "confidence": signal.get("confidence", 0.0),
                }
            else:
                # HOLD - return action="hold" to avoid validation warning
                return {"action": "hold"}
        except Exception:
            # On error, return HOLD action
            return {"action": "hold"}

