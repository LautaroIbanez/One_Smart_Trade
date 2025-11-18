"""Stop-loss / take-profit optimizer with walk-forward validation."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.model_selection import ParameterGrid

from app.core.logging import logger
from app.quant.regime import RegimeClassifier


DEFAULT_SEARCH_SPACE: dict[str, list[float]] = {
    "atr_multiplier_sl": [1.25, 1.5, 1.75, 2.0, 2.5],
    "atr_multiplier_tp": [2.0, 2.25, 2.5, 3.0],
    "tp_ratio": [1.4, 1.8, 2.2],
    "breakeven_buffer_pct": [0.0, 0.15, 0.25],
}


@dataclass
class OptimizationMetrics:
    """Container for optimization metrics."""

    calmar: float
    profit_factor: float
    hit_rate: float
    avg_rr: float
    expectancy_r: float
    max_drawdown: float
    rr_distribution: list[float]

    def to_dict(self) -> dict[str, float]:
        return {
            "calmar": float(self.calmar),
            "profit_factor": float(self.profit_factor),
            "hit_rate": float(self.hit_rate),
            "avg_rr": float(self.avg_rr),
            "expectancy_r": float(self.expectancy_r),
            "max_drawdown": float(self.max_drawdown),
        }


@dataclass
class WindowConfig:
    """Represents walk-forward window summary."""

    index: int
    train_range: tuple[str, str]
    test_range: tuple[str, str]
    params: dict[str, float]
    train_metrics: OptimizationMetrics
    test_metrics: OptimizationMetrics

    def serialize(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "train_range": self.train_range,
            "test_range": self.test_range,
            "params": {k: float(v) for k, v in self.params.items()},
            "train_metrics": self.train_metrics.to_dict(),
            "test_metrics": self.test_metrics.to_dict(),
        }


class StopLossTakeProfitOptimizer:
    """Optimizer that tunes SL/TP parameters per symbol and regime."""

    def __init__(
        self,
        *,
        artifacts_dir: str | Path = "artifacts/sl_tp",
        train_days: int = 90,
        test_days: int = 30,
        rr_floor: float = 1.2,
        max_config_age_days: int = 14,
    ) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.train_days = train_days
        self.test_days = test_days
        self.rr_floor = rr_floor
        self.max_config_age_days = max_config_age_days
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def optimize(
        self,
        trades: pd.DataFrame,
        *,
        symbol: str,
        regime_classifier: RegimeClassifier | None = None,
        price_data: pd.DataFrame | None = None,
        search_space: dict[str, Iterable[float]] | None = None,
        method: str = "grid",
        timestamp_col: str = "timestamp",
        regime_col: str = "regime",
    ) -> dict[str, Any]:
        """
        Optimize SL/TP hyperparameters per regime using walk-forward validation.

        Args:
            trades: DataFrame with historical backtest trades and MAE/MFE columns.
            symbol: Symbol to optimize (e.g. "BTCUSDT").
            regime_classifier: Optional classifier to label regimes if missing.
            price_data: Price dataframe to derive regimes when not present.
            search_space: Optional hyperparameter search space.
            method: "grid" or "bayesian" (bayesian falls back to adaptive random search).
            timestamp_col: Column name with trade timestamps.
            regime_col: Column name with regime labels.
        """
        if trades is None or trades.empty:
            raise ValueError("Trades dataframe cannot be empty for SL/TP optimization")

        df = trades.copy()
        if symbol:
            df = df[df.get("symbol", symbol) == symbol]
        if df.empty:
            raise ValueError(f"No trades available for symbol={symbol}")

        df[timestamp_col] = pd.to_datetime(df[timestamp_col], utc=True)
        df = df.sort_values(timestamp_col)

        if regime_col not in df.columns or df[regime_col].isna().all():
            if regime_classifier and price_data is not None:
                df = self._attach_regimes(df, price_data, regime_classifier, timestamp_col, regime_col)
            else:
                logger.warning("Regime column missing; defaulting to 'unknown'")
                df[regime_col] = "unknown"

        configs: dict[str, Any] = {}
        regimes = df[regime_col].dropna().unique()
        for regime in regimes:
            regime_df = df[df[regime_col] == regime].copy()
            min_points = self.train_days + self.test_days
            if len(regime_df) < min_points:
                logger.info("Skipping regime %s due to insufficient samples", regime)
                continue
            windows = self._build_windows(regime_df[timestamp_col])
            if not windows:
                continue

            space = search_space or DEFAULT_SEARCH_SPACE
            combos = self._generate_search_combinations(space, method)

            window_results: list[WindowConfig] = []
            for window in windows:
                train_mask = (regime_df[timestamp_col] >= window["train_start"]) & (regime_df[timestamp_col] < window["train_end"])
                test_mask = (regime_df[timestamp_col] >= window["test_start"]) & (regime_df[timestamp_col] < window["test_end"])
                train_df = regime_df.loc[train_mask].reset_index(drop=True)
                test_df = regime_df.loc[test_mask].reset_index(drop=True)
                if train_df.empty or test_df.empty:
                    continue

                best_params, train_metrics = self._search_params(train_df, combos)
                test_metrics = self._evaluate_params(test_df, best_params)
                window_results.append(
                    WindowConfig(
                        index=window["index"],
                        train_range=(window["train_start"].isoformat(), window["train_end"].isoformat()),
                        test_range=(window["test_start"].isoformat(), window["test_end"].isoformat()),
                        params=best_params,
                        train_metrics=train_metrics,
                        test_metrics=test_metrics,
                    )
                )

            if not window_results:
                continue

            rr_values = [cfg.test_metrics.avg_rr for cfg in window_results if not math.isnan(cfg.test_metrics.avg_rr)]
            rr_threshold = max(self.rr_floor, float(np.percentile(rr_values, 35))) if rr_values else self.rr_floor

            aggregate = self._aggregate_results(window_results)
            payload = {
                "symbol": symbol,
                "regime": regime,
                "rr_threshold": rr_threshold,
                "search_space": {k: list(map(float, v)) for k, v in (search_space or DEFAULT_SEARCH_SPACE).items()},
                "windows": [cfg.serialize() for cfg in window_results],
                "aggregates": aggregate,
                "best_params": self._derive_consensus_params(window_results),
                "metadata": {
                    "method": method,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "train_days": self.train_days,
                    "test_days": self.test_days,
                },
            }
            self._persist_config(symbol, regime, payload)
            configs[regime] = payload

        return configs

    def load_config(
        self,
        symbol: str,
        regime: str,
        *,
        max_age_days: int | None = None,
    ) -> dict[str, Any] | None:
        """Load persisted configuration if still valid."""
        path = self._artifact_path(symbol, regime)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            logger.warning("Invalid SL/TP config JSON at %s", path)
            return None

        age_limit = max_age_days if max_age_days is not None else self.max_config_age_days
        updated_at = data.get("metadata", {}).get("updated_at")
        if updated_at and age_limit:
            try:
                ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError:
                ts = None
            if ts and datetime.now(timezone.utc) - ts > timedelta(days=age_limit):
                logger.warning("SL/TP config for %s/%s is stale (> %s days)", symbol, regime, age_limit)
                return None
        return data

    def _attach_regimes(
        self,
        trades: pd.DataFrame,
        price_data: pd.DataFrame,
        classifier: RegimeClassifier,
        timestamp_col: str,
        regime_col: str,
    ) -> pd.DataFrame:
        """Attach regime labels to trades using classifier predictions."""
        df = trades.copy()
        price = price_data.copy()
        if "timestamp" in price.columns:
            price["timestamp"] = pd.to_datetime(price["timestamp"], utc=True)
            price = price.sort_values("timestamp")
            price = price.set_index("timestamp")
        else:
            price = price.copy()
            price.index = pd.to_datetime(price.index, utc=True)

        features = classifier.extract_features(price)
        if features.empty:
            df[regime_col] = "unknown"
            return df

        classifier.fit_rolling(features)
        proba = classifier.predict_proba(features)
        regimes = proba.idxmax(axis=1)
        regime_df = regimes.to_frame(name=regime_col)
        regime_df.index.name = timestamp_col
        merged = pd.merge_asof(
            df.sort_values(timestamp_col),
            regime_df.reset_index(),
            left_on=timestamp_col,
            right_on=timestamp_col,
            direction="backward",
        )
        merged[regime_col] = merged[regime_col].fillna("unknown")
        return merged

    def _build_windows(self, timestamps: pd.Series) -> list[dict[str, Any]]:
        """Build rolling windows for walk-forward analysis."""
        if timestamps.empty:
            return []
        start = timestamps.min()
        end = timestamps.max()
        windows: list[dict[str, Any]] = []
        idx = 0
        current_start = start

        while current_start + timedelta(days=self.train_days + self.test_days) <= end:
            train_end = current_start + timedelta(days=self.train_days)
            test_end = train_end + timedelta(days=self.test_days)
            windows.append(
                {
                    "index": idx,
                    "train_start": current_start,
                    "train_end": train_end,
                    "test_start": train_end,
                    "test_end": test_end,
                }
            )
            current_start = current_start + timedelta(days=self.test_days)
            idx += 1
        return windows

    def _generate_search_combinations(self, space: dict[str, Iterable[float]], method: str) -> list[dict[str, float]]:
        """Generate hyperparameter combinations."""
        if method == "grid":
            grid = list(ParameterGrid(space))
            return [self._sanitize_params(combo) for combo in grid]
        # Simple adaptive random search acting as Bayesian-lite fallback
        combos: list[dict[str, float]] = []
        keys = list(space.keys())
        values = [list(v) for v in space.values()]
        rng = np.random.default_rng(seed=42)
        for _ in range(max(30, len(values[0]) * len(keys))):
            combo = {key: float(rng.choice(space[key])) for key in keys}
            combos.append(self._sanitize_params(combo))
        return combos

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, float]:
        return {k: float(v) for k, v in params.items()}

    def _search_params(self, df: pd.DataFrame, combos: list[dict[str, float]]) -> tuple[dict[str, float], OptimizationMetrics]:
        """Search over parameter combinations and pick the best by score."""
        best_score = -np.inf
        best_params: dict[str, float] = {}
        best_metrics: OptimizationMetrics | None = None
        for params in combos:
            metrics = self._evaluate_params(df, params)
            score = self._score(metrics)
            if score > best_score:
                best_score = score
                best_params = params
                best_metrics = metrics
        if best_metrics is None:
            raise RuntimeError("Failed to evaluate any parameter combination")
        return best_params, best_metrics

    def _evaluate_params(self, df: pd.DataFrame, params: dict[str, float]) -> OptimizationMetrics:
        """Evaluate performance of a parameter combination."""
        pnl_r: list[float] = []
        rr_values: list[float] = []
        drawdown_curve: list[float] = []

        for _, row in df.iterrows():
            atr = float(row.get("atr") or row.get("atr_14") or 0.0)
            if atr <= 0:
                continue
            entry_price = float(row.get("entry_price") or row.get("entry"))
            direction = str(row.get("direction") or row.get("side") or "BUY").upper()
            mae = abs(float(row.get("mae", atr)))
            mfe = abs(float(row.get("mfe", atr)))
            pnl_realized = float(row.get("pnl", 0.0))

            sl_distance = max(atr * params.get("atr_multiplier_sl", 1.5), 1e-8)
            tp_distance = atr * params.get("atr_multiplier_tp", 2.0)
            tp_ratio = params.get("tp_ratio", 2.0)
            reward_distance = max(tp_distance * tp_ratio, sl_distance * self.rr_floor)

            breakeven_buffer = params.get("breakeven_buffer_pct", 0.0)
            rr = reward_distance / sl_distance if sl_distance else 0.0
            rr_values.append(rr)

            hit_sl = mae >= sl_distance
            hit_tp = mfe >= reward_distance

            outcome_r: float
            if hit_sl and hit_tp:
                mae_ratio = mae / sl_distance
                mfe_ratio = mfe / reward_distance
                outcome_r = -1.0 if mae_ratio <= mfe_ratio else rr
            elif hit_sl:
                outcome_r = -1.0
            elif hit_tp:
                outcome_r = rr
            else:
                outcome_r = (pnl_realized / sl_distance) if sl_distance else 0.0

            if breakeven_buffer > 0 and hit_tp and mfe >= breakeven_buffer * reward_distance:
                outcome_r = max(outcome_r, 0.0)

            pnl_r.append(outcome_r)
            equity = 1.0 + float(np.sum(pnl_r))
            drawdown_curve.append(equity)

        if not pnl_r:
            return OptimizationMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [])

        hit_rate = float(np.mean([1.0 if x > 0 else 0.0 for x in pnl_r]))
        expectancy = float(np.mean(pnl_r))
        profit_factor = self._profit_factor(pnl_r)
        calmar = self._calmar_ratio(drawdown_curve)
        max_dd = self._max_drawdown(drawdown_curve)

        return OptimizationMetrics(
            calmar=calmar,
            profit_factor=profit_factor,
            hit_rate=hit_rate,
            avg_rr=float(np.mean(rr_values)) if rr_values else 0.0,
            expectancy_r=expectancy,
            max_drawdown=max_dd,
            rr_distribution=rr_values,
        )

    @staticmethod
    def _profit_factor(pnl: list[float]) -> float:
        profits = sum(x for x in pnl if x > 0)
        losses = -sum(x for x in pnl if x < 0)
        if losses == 0:
            return float("inf")
        return profits / losses if losses else 0.0

    @staticmethod
    def _max_drawdown(curve: list[float]) -> float:
        if not curve:
            return 0.0
        series = pd.Series(curve)
        running_max = series.cummax()
        drawdowns = (series / running_max) - 1.0
        return abs(float(drawdowns.min()))

    def _calmar_ratio(self, curve: list[float]) -> float:
        if len(curve) < 2:
            return 0.0
        series = pd.Series(curve)
        total_return = series.iloc[-1] / series.iloc[0] - 1.0
        years = max(len(series) / 252.0, 1e-6)
        cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if total_return >= -0.99 else -1.0
        max_dd = self._max_drawdown(curve)
        if max_dd == 0:
            return float("inf") if cagr > 0 else 0.0
        return float(cagr / max_dd)

    @staticmethod
    def _score(metrics: OptimizationMetrics) -> float:
        calmar_component = metrics.calmar
        pf_component = metrics.profit_factor
        expectancy_component = metrics.expectancy_r * 2.0
        return calmar_component * 0.5 + pf_component * 0.3 + expectancy_component * 0.2

    def _aggregate_results(self, windows: list[WindowConfig]) -> dict[str, Any]:
        """Aggregate metrics across windows."""
        train = pd.DataFrame([w.train_metrics.to_dict() for w in windows])
        test = pd.DataFrame([w.test_metrics.to_dict() for w in windows])
        
        # Calculate aggregate metrics (using test metrics for out-of-sample)
        aggregates = {
            "calmar": float(test["calmar"].mean()) if "calmar" in test.columns else 0.0,
            "profit_factor": float(test["profit_factor"].mean()) if "profit_factor" in test.columns else 0.0,
            "hit_rate": float(test["hit_rate"].mean()) if "hit_rate" in test.columns else 0.0,
            "avg_rr": float(test["avg_rr"].mean()) if "avg_rr" in test.columns else 0.0,
            "expectancy_r": float(test["expectancy_r"].mean()) if "expectancy_r" in test.columns else 0.0,
            "max_drawdown": float(test["max_drawdown"].max()) if "max_drawdown" in test.columns else 0.0,
        }
        
        return {
            "train_mean": train.mean(numeric_only=True).to_dict(),
            "test_mean": test.mean(numeric_only=True).to_dict(),
            "test_std": test.std(numeric_only=True).to_dict(),
            **aggregates,  # Include flat aggregates for easy access
        }

    def _derive_consensus_params(self, windows: list[WindowConfig]) -> dict[str, float]:
        """Average parameters across windows weighted by test Calmar."""
        if not windows:
            return {}
        weights = np.array([max(0.0, w.test_metrics.calmar) + 1e-6 for w in windows])
        weights = weights / weights.sum() if weights.sum() else np.ones_like(weights) / len(weights)
        param_keys = windows[0].params.keys()
        consensus = {}
        for key in param_keys:
            values = np.array([w.params[key] for w in windows], dtype=float)
            consensus[key] = float(np.dot(weights, values))
        return consensus

    def _persist_config(self, symbol: str, regime: str, payload: dict[str, Any]) -> None:
        path = self._artifact_path(symbol, regime)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=self._json_serializer))
        logger.info("Persisted SL/TP optimizer config", extra={"symbol": symbol, "regime": regime, "path": str(path)})

    def _artifact_path(self, symbol: str, regime: str) -> Path:
        sanitized_symbol = symbol.replace("/", "_")
        sanitized_regime = regime.replace(" ", "_").lower()
        return self.artifacts_dir / sanitized_symbol / sanitized_regime / "config.json"

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

