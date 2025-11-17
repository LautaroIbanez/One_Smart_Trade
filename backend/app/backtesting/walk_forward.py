"""Walk-forward and train/validation/OOS pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from app.backtesting.engine import BacktestEngine, BacktestRunRequest
from app.backtesting.metrics import calculate_metrics
from app.core.logging import logger


@dataclass
class WalkForwardWindow:
    """Single walk-forward window."""

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    window_index: int


@dataclass
class WalkForwardResult:
    """Result of walk-forward analysis."""

    windows: list[WalkForwardWindow]
    train_results: list[dict[str, Any]]
    test_results: list[dict[str, Any]]
    train_scores: list[float]
    test_scores: list[float]
    avg_train_score: float
    avg_test_score: float
    std_test_score: float


@dataclass
class TrainValOOSSplit:
    """Train/validation/OOS split."""

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp


class WalkForwardPipeline:
    """Walk-forward pipeline with train/validation/OOS splits."""

    def __init__(
        self,
        *,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        oos_ratio: float = 0.2,
        walk_forward_train_days: int = 90,
        walk_forward_test_days: int = 30,
        oos_days: int = 180,
    ) -> None:
        """
        Initialize walk-forward pipeline.

        Args:
            train_ratio: Training set ratio (default: 60%)
            val_ratio: Validation set ratio (default: 20%)
            oos_ratio: Out-of-sample ratio (default: 20%)
            walk_forward_train_days: Training window for walk-forward (default: 90 days)
            walk_forward_test_days: Test window for walk-forward (default: 30 days)
            oos_days: Fixed OOS period in days (default: 180 = 6 months)
        """
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.oos_ratio = oos_ratio
        self.walk_forward_train_days = walk_forward_train_days
        self.walk_forward_test_days = walk_forward_test_days
        self.oos_days = oos_days

    def split_train_val_oos(
        self,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> TrainValOOSSplit:
        """
        Split data into train/validation/OOS.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            TrainValOOSSplit with date ranges
        """
        total_days = (end_date - start_date).days

        # Calculate split points
        train_days = int(total_days * self.train_ratio)
        val_days = int(total_days * self.val_ratio)

        train_end = start_date + pd.Timedelta(days=train_days)
        val_start = train_end
        val_end = val_start + pd.Timedelta(days=val_days)
        oos_start = end_date - pd.Timedelta(days=self.oos_days)
        oos_end = end_date

        # Ensure OOS doesn't overlap with validation
        if oos_start < val_end:
            oos_start = val_end

        return TrainValOOSSplit(
            train_start=start_date,
            train_end=train_end,
            val_start=val_start,
            val_end=val_end,
            oos_start=oos_start,
            oos_end=oos_end,
        )

    def generate_walk_forward_windows(
        self,
        train_start: pd.Timestamp,
        train_end: pd.Timestamp,
    ) -> list[WalkForwardWindow]:
        """
        Generate rolling walk-forward windows.

        Args:
            train_start: Start of training period
            train_end: End of training period (before OOS)

        Returns:
            List of WalkForwardWindow
        """
        windows = []
        current_start = train_start
        window_index = 0

        while current_start + pd.Timedelta(days=self.walk_forward_train_days + self.walk_forward_test_days) <= train_end:
            train_window_end = current_start + pd.Timedelta(days=self.walk_forward_train_days)
            test_window_start = train_window_end
            test_window_end = test_window_start + pd.Timedelta(days=self.walk_forward_test_days)

            if test_window_end > train_end:
                break

            windows.append(
                WalkForwardWindow(
                    train_start=current_start,
                    train_end=train_window_end,
                    test_start=test_window_start,
                    test_end=test_window_end,
                    window_index=window_index,
                )
            )

            # Slide window forward by test period
            current_start = test_window_start
            window_index += 1

        return windows

    async def run_walk_forward(
        self,
        engine: BacktestEngine,
        request: BacktestRunRequest,
        scorer: Callable[[dict[str, Any]], float],
        *,
        dd_limit: float = 0.25,
    ) -> WalkForwardResult:
        """
        Run walk-forward analysis.

        Args:
            engine: BacktestEngine instance
            request: BacktestRunRequest (will be modified for each window)
            scorer: Function to score results (returns Calmar or similar)
            dd_limit: Maximum drawdown limit (default: 25%)

        Returns:
            WalkForwardResult
        """
        # Split into train/val/OOS
        split = self.split_train_val_oos(request.start_date, request.end_date)

        # Generate walk-forward windows from training period
        windows = self.generate_walk_forward_windows(split.train_start, split.val_end)

        train_results = []
        test_results = []
        train_scores = []
        test_scores = []

        for window in windows:
            # Train window
            train_request = BacktestRunRequest(
                instrument=request.instrument,
                timeframe=request.timeframe,
                start_date=window.train_start,
                end_date=window.train_end,
                strategy=request.strategy,
                initial_capital=request.initial_capital,
                commission_rate=request.commission_rate,
                slippage_model=request.slippage_model,
                fixed_slippage_bps=request.fixed_slippage_bps,
                use_orderbook=request.use_orderbook,
                risk_manager=request.risk_manager,
                seed=request.seed,
            )

            try:
                train_result = await engine.run_backtest(
                    window.train_start,
                    window.train_end,
                    instrument=request.instrument,
                    timeframe=request.timeframe,
                    strategy=request.strategy,
                    initial_capital=request.initial_capital,
                    commission_rate=request.commission_rate,
                    slippage_model=request.slippage_model,
                    fixed_slippage_bps=request.fixed_slippage_bps,
                    use_orderbook=request.use_orderbook,
                    risk_manager=request.risk_manager,
                    seed=request.seed,
                )

                if "error" in train_result:
                    logger.warning("Train window failed", extra={"window": window.window_index, "error": train_result.get("error")})
                    continue

                train_metrics = calculate_metrics(train_result)
                train_score = scorer(train_metrics)

                # Skip if drawdown exceeds limit
                max_dd = train_metrics.get("max_drawdown", 0.0) / 100.0  # Convert from percentage
                if max_dd > dd_limit:
                    logger.info("Train window rejected due to drawdown", extra={"window": window.window_index, "max_dd": max_dd})
                    continue

                train_results.append(train_result)
                train_scores.append(train_score)

                # Test window
                test_result = await engine.run_backtest(
                    window.test_start,
                    window.test_end,
                    instrument=request.instrument,
                    timeframe=request.timeframe,
                    strategy=request.strategy,
                    initial_capital=request.initial_capital,
                    commission_rate=request.commission_rate,
                    slippage_model=request.slippage_model,
                    fixed_slippage_bps=request.fixed_slippage_bps,
                    use_orderbook=request.use_orderbook,
                    risk_manager=request.risk_manager,
                    seed=request.seed,
                )

                if "error" in test_result:
                    logger.warning("Test window failed", extra={"window": window.window_index, "error": test_result.get("error")})
                    continue

                test_metrics = calculate_metrics(test_result)
                test_score = scorer(test_metrics)

                test_results.append(test_result)
                test_scores.append(test_score)

            except Exception as exc:
                logger.exception("Walk-forward window failed", extra={"window": window.window_index, "error": str(exc)})
                continue

        avg_train_score = sum(train_scores) / len(train_scores) if train_scores else 0.0
        avg_test_score = sum(test_scores) / len(test_scores) if test_scores else 0.0
        std_test_score = pd.Series(test_scores).std() if test_scores else 0.0

        return WalkForwardResult(
            windows=windows,
            train_results=train_results,
            test_results=test_results,
            train_scores=train_scores,
            test_scores=test_scores,
            avg_train_score=avg_train_score,
            avg_test_score=avg_test_score,
            std_test_score=std_test_score,
        )

    async def run_oos_validation(
        self,
        engine: BacktestEngine,
        request: BacktestRunRequest,
        scorer: Callable[[dict[str, Any]], float],
    ) -> dict[str, Any]:
        """
        Run final OOS validation.

        Args:
            engine: BacktestEngine instance
            request: BacktestRunRequest
            scorer: Function to score results

        Returns:
            OOS result dict with metrics
        """
        split = self.split_train_val_oos(request.start_date, request.end_date)

        oos_result = await engine.run_backtest(
            split.oos_start,
            split.oos_end,
            instrument=request.instrument,
            timeframe=request.timeframe,
            strategy=request.strategy,
            initial_capital=request.initial_capital,
            commission_rate=request.commission_rate,
            slippage_model=request.slippage_model,
            fixed_slippage_bps=request.fixed_slippage_bps,
            use_orderbook=request.use_orderbook,
            risk_manager=request.risk_manager,
            seed=request.seed,
        )

        if "error" in oos_result:
            return {"error": oos_result.get("error"), "valid": False}

        oos_metrics = calculate_metrics(oos_result)
        oos_score = scorer(oos_metrics)

        oos_length_days = (split.oos_end - split.oos_start).days

        return {
            "valid": True,
            "result": oos_result,
            "metrics": oos_metrics,
            "score": oos_score,
            "start_date": split.oos_start.isoformat(),
            "end_date": split.oos_end.isoformat(),
            "length_days": oos_length_days,
        }

