"""Auto-shutdown policies for drawdown and performance degradation protection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class StrategyMetrics:
    """Current strategy metrics for shutdown evaluation."""

    current_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    trades: list[dict[str, Any]] | pd.DataFrame | None = None
    equity_curve: list[float] | None = None

    def rolling_sharpe(self, lookback_trades: int, min_trades: int = 2) -> float | None:
        """
        Calculate rolling Sharpe ratio over last N trades.
        
        Args:
            lookback_trades: Number of trades to look back
            min_trades: Minimum number of trades required to compute Sharpe (default: 2)
            
        Returns:
            Rolling Sharpe ratio (annualized) or None if insufficient data
        """
        if self.trades is None or self.equity_curve is None:
            return None
        
        if isinstance(self.trades, list):
            if not self.trades:
                return None
            trades_df = pd.DataFrame(self.trades)
        else:
            trades_df = self.trades.copy()
        
        if trades_df.empty or len(trades_df) < min_trades:
            return None
        
        # Get last N trades
        recent_trades = trades_df.tail(lookback_trades)
        
        if "return_pct" in recent_trades.columns:
            returns = recent_trades["return_pct"].values
        elif "pnl" in recent_trades.columns:
            # Convert PnL to returns (approximate)
            if self.current_equity > 0:
                returns = (recent_trades["pnl"].values / self.current_equity) * 100
            else:
                returns = recent_trades["pnl"].values
        else:
            return None
        
        if len(returns) < min_trades:
            return None
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        # Zero variance means no risk, but also no meaningful Sharpe
        if std_return == 0:
            return None
        
        # Annualized Sharpe (assuming ~252 trading days, ~1 trade per day)
        sharpe = (mean_return / std_return) * np.sqrt(252)
        return float(sharpe)

    def rolling_hit_rate(self, lookback_trades: int) -> float:
        """
        Calculate rolling hit rate (win rate) over last N trades.
        
        Args:
            lookback_trades: Number of trades to look back
            
        Returns:
            Hit rate as percentage (0.0 to 100.0)
        """
        if self.trades is None:
            return 0.0
        
        if isinstance(self.trades, list):
            if not self.trades:
                return 0.0
            trades_df = pd.DataFrame(self.trades)
        else:
            trades_df = self.trades.copy()
        
        if trades_df.empty:
            return 0.0
        
        recent_trades = trades_df.tail(lookback_trades)
        
        if "pnl" in recent_trades.columns:
            winning = (recent_trades["pnl"] > 0).sum()
        elif "return_pct" in recent_trades.columns:
            winning = (recent_trades["return_pct"] > 0).sum()
        else:
            return 0.0
        
        total = len(recent_trades)
        if total == 0:
            return 0.0
        
        return float((winning / total) * 100.0)


@dataclass
class AutoShutdownPolicy:
    """
    Auto-shutdown policy for drawdown and performance degradation protection.
    
    Suspends new operations when:
    - Drawdown exceeds max_drawdown_pct (hard stop)
    - Rolling Sharpe falls below min_rolling_sharpe for N trades
    - Rolling hit rate falls below min_hit_rate for N trades
    """

    max_drawdown_pct: float = 20.0
    min_rolling_sharpe: float = 0.2
    min_hit_rate: float = 40.0
    lookback_trades: int = 50
    consecutive_breaches: int = 1
    reduction_factor: float = 0.5
    enable_size_reduction: bool = True

    def should_shutdown(
        self,
        metrics: StrategyMetrics,
        *,
        check_sharpe: bool = True,
        check_hit_rate: bool = True,
        allow_missing_data: bool = False,
    ) -> tuple[bool, str]:
        """
        Determine if strategy should be shut down based on current metrics.
        
        Args:
            metrics: Current strategy metrics
            check_sharpe: Check rolling Sharpe breach
            check_hit_rate: Check rolling hit rate breach
            allow_missing_data: If True, missing Sharpe/hit rate data won't trigger shutdown
            
        Returns:
            Tuple of (should_shutdown, reason)
        """
        # Hard stop: drawdown breach
        if metrics.current_drawdown_pct >= self.max_drawdown_pct:
            return True, f"Drawdown hard-stop: {metrics.current_drawdown_pct:.2f}% >= {self.max_drawdown_pct:.2f}%"
        
        # Performance guard: rolling Sharpe
        if check_sharpe:
            rolling_sharpe = metrics.rolling_sharpe(self.lookback_trades)
            if rolling_sharpe is None:
                # Insufficient data
                if not allow_missing_data:
                    return True, f"Insufficient performance history: need at least 2 trades to compute rolling Sharpe (last {self.lookback_trades} trades)"
                # allow_missing_data=True: skip Sharpe check when data is missing
            elif rolling_sharpe < self.min_rolling_sharpe:
                return True, f"Rolling Sharpe breach: {rolling_sharpe:.2f} < {self.min_rolling_sharpe:.2f} (last {self.lookback_trades} trades)"
        
        # Performance guard: rolling hit rate
        if check_hit_rate:
            rolling_hit_rate = metrics.rolling_hit_rate(self.lookback_trades)
            if rolling_hit_rate == 0.0 and (metrics.trades is None or (isinstance(metrics.trades, list) and not metrics.trades)):
                # No trades at all
                if not allow_missing_data:
                    return True, f"Insufficient performance history: need trade history to compute rolling hit rate (last {self.lookback_trades} trades)"
            elif rolling_hit_rate < self.min_hit_rate:
                return True, f"Rolling hit rate breach: {rolling_hit_rate:.2f}% < {self.min_hit_rate:.2f}% (last {self.lookback_trades} trades)"
        
        return False, "ok"

    def should_reduce_size(
        self,
        metrics: StrategyMetrics,
    ) -> tuple[bool, float, str]:
        """
        Determine if position size should be reduced (instead of full shutdown).
        
        Args:
            metrics: Current strategy metrics
            
        Returns:
            Tuple of (should_reduce, reduction_factor, reason)
        """
        if not self.enable_size_reduction:
            return False, 1.0, "size_reduction_disabled"
        
        # Check if approaching drawdown limit (80% of max)
        warning_threshold = self.max_drawdown_pct * 0.8
        if metrics.current_drawdown_pct >= warning_threshold:
            return True, self.reduction_factor, f"Drawdown warning: {metrics.current_drawdown_pct:.2f}% >= {warning_threshold:.2f}%"
        
        # Check if Sharpe is below warning threshold (120% of min)
        warning_sharpe = self.min_rolling_sharpe * 1.2
        rolling_sharpe = metrics.rolling_sharpe(self.lookback_trades)
        if rolling_sharpe is not None and rolling_sharpe < warning_sharpe and rolling_sharpe > self.min_rolling_sharpe:
            return True, self.reduction_factor, f"Sharpe warning: {rolling_sharpe:.2f} < {warning_sharpe:.2f}"
        
        # Check if hit rate is below warning threshold (120% of min)
        warning_hit_rate = self.min_hit_rate * 1.2
        rolling_hit_rate = metrics.rolling_hit_rate(self.lookback_trades)
        if rolling_hit_rate < warning_hit_rate and rolling_hit_rate > self.min_hit_rate:
            return True, self.reduction_factor, f"Hit rate warning: {rolling_hit_rate:.2f}% < {warning_hit_rate:.2f}%"
        
        return False, 1.0, "ok"

    def get_status(
        self,
        metrics: StrategyMetrics,
    ) -> dict[str, Any]:
        """
        Get current shutdown policy status.
        
        Args:
            metrics: Current strategy metrics
            
        Returns:
            Dict with shutdown status, warnings, and recommendations
        """
        should_shutdown, shutdown_reason = self.should_shutdown(metrics)
        should_reduce, reduction_factor, reduce_reason = self.should_reduce_size(metrics)
        
        rolling_sharpe = metrics.rolling_sharpe(self.lookback_trades)
        rolling_hit_rate = metrics.rolling_hit_rate(self.lookback_trades)
        
        return {
            "shutdown": should_shutdown,
            "shutdown_reason": shutdown_reason,
            "size_reduction": should_reduce,
            "size_reduction_factor": reduction_factor,
            "size_reduction_reason": reduce_reason,
            "current_drawdown_pct": metrics.current_drawdown_pct,
            "rolling_sharpe": rolling_sharpe,
            "rolling_hit_rate": rolling_hit_rate,
            "has_sharpe_data": rolling_sharpe is not None,
            "max_drawdown_pct": self.max_drawdown_pct,
            "min_rolling_sharpe": self.min_rolling_sharpe,
            "min_hit_rate": self.min_hit_rate,
            "lookback_trades": self.lookback_trades,
        }


class AutoShutdownManager:
    """
    Manager for auto-shutdown policies with state tracking.
    
    Tracks shutdown state and provides recovery detection.
    """

    def __init__(
        self,
        policy: AutoShutdownPolicy | None = None,
    ) -> None:
        """
        Initialize auto-shutdown manager.
        
        Args:
            policy: Shutdown policy (default: standard policy)
        """
        self.policy = policy or AutoShutdownPolicy()
        self.is_shutdown: bool = False
        self.shutdown_reason: str = ""
        self.size_reduction_factor: float = 1.0
        self.size_reduction_reason: str = ""

    def evaluate(
        self,
        metrics: StrategyMetrics,
    ) -> dict[str, Any]:
        """
        Evaluate shutdown policy and update state.
        
        Args:
            metrics: Current strategy metrics
            
        Returns:
            Dict with evaluation results and recommendations
        """
        status = self.policy.get_status(metrics)
        
        # Update shutdown state
        if status["shutdown"]:
            self.is_shutdown = True
            self.shutdown_reason = status["shutdown_reason"]
        else:
            # Check if recovered from shutdown
            if self.is_shutdown:
                # Recovery: drawdown below 80% of max, Sharpe above min (if available), hit rate above min
                recovery_dd = metrics.current_drawdown_pct < (self.policy.max_drawdown_pct * 0.8)
                recovery_sharpe = status["rolling_sharpe"] is None or status["rolling_sharpe"] >= self.policy.min_rolling_sharpe
                recovery_hit_rate = status["rolling_hit_rate"] >= self.policy.min_hit_rate
                
                if recovery_dd and recovery_sharpe and recovery_hit_rate:
                    self.is_shutdown = False
                    self.shutdown_reason = ""
                    status["recovered"] = True
                    status["recovery_message"] = "Strategy recovered from shutdown"
        
        # Update size reduction
        if status["size_reduction"]:
            self.size_reduction_factor = status["size_reduction_factor"]
            self.size_reduction_reason = status["size_reduction_reason"]
        else:
            # Check if recovered from size reduction
            if self.size_reduction_factor < 1.0:
                # Recovery: all metrics above warning thresholds
                recovery_dd = metrics.current_drawdown_pct < (self.policy.max_drawdown_pct * 0.6)
                recovery_sharpe = status["rolling_sharpe"] is None or status["rolling_sharpe"] >= (self.policy.min_rolling_sharpe * 1.5)
                recovery_hit_rate = status["rolling_hit_rate"] >= (self.policy.min_hit_rate * 1.2)
                
                if recovery_dd and recovery_sharpe and recovery_hit_rate:
                    self.size_reduction_factor = 1.0
                    self.size_reduction_reason = ""
                    status["size_reduction_recovered"] = True
        
        status["is_shutdown"] = self.is_shutdown
        status["current_size_factor"] = self.size_reduction_factor
        
        return status

    def get_size_multiplier(self) -> float:
        """
        Get current position size multiplier.
        
        Returns:
            Size multiplier (0.0 to 1.0)
        """
        if self.is_shutdown:
            return 0.0
        return self.size_reduction_factor

    def reset(self) -> None:
        """Reset shutdown state (for manual override)."""
        self.is_shutdown = False
        self.shutdown_reason = ""
        self.size_reduction_factor = 1.0
        self.size_reduction_reason = ""





