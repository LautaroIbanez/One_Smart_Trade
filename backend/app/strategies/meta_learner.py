"""Meta-learner for combining strategy signals."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score,
    brier_score_loss,
    calibration_curve,
    log_loss,
)
from sklearn.preprocessing import StandardScaler

from app.core.logging import logger


class MetaLearner:
    """Meta-learner that learns to combine strategy signals optimally."""

    def __init__(
        self,
        model_type: str = "logistic",
        regime: str | None = None,
    ):
        """
        Initialize meta-learner.
        
        Args:
            model_type: Model type ("logistic" or "gradient_boosting")
            regime: Market regime this model is trained for (None for general)
        """
        self.model_type = model_type
        self.regime = regime
        self.model = self._create_model()
        self.scaler = StandardScaler()
        self.feature_names: list[str] = []
        self.is_fitted = False
        self.metrics: dict[str, float] = {}

    def _create_model(self):
        """Create model based on model_type."""
        if self.model_type == "logistic":
            return LogisticRegression(
                max_iter=1000,
                C=1.0,
                penalty="l2",
                solver="lbfgs",
                random_state=42,
            )
        elif self.model_type == "gradient_boosting":
            return GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
                subsample=0.8,
            )
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

    def build_features(
        self,
        strategy_signals: list[dict[str, Any]],
        regime_features: dict[str, Any] | None = None,
        volatility_state: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """
        Build feature vector from strategy signals and market context.
        
        Args:
            strategy_signals: List of dicts with keys: strategy, signal, confidence
            regime_features: Market regime features (regime, vol_bucket, etc.)
            volatility_state: Volatility state features
        
        Returns:
            Feature vector as numpy array
        """
        features = []

        # Strategy signals: one-hot encode signal type and include confidence
        strategy_names = ["momentum_trend", "mean_reversion", "breakout"]
        for strategy_name in strategy_names:
            # Find signal for this strategy
            signal_data = next(
                (s for s in strategy_signals if s.get("strategy") == strategy_name),
                None,
            )

            if signal_data:
                signal = signal_data.get("signal", "HOLD")
                confidence = float(signal_data.get("confidence", 0.0)) / 100.0  # Normalize to 0-1

                # One-hot encode signal
                signal_buy = 1.0 if signal == "BUY" else 0.0
                signal_sell = 1.0 if signal == "SELL" else 0.0
                signal_hold = 1.0 if signal == "HOLD" else 0.0

                features.extend([signal_buy, signal_sell, signal_hold, confidence])
            else:
                # Missing strategy: all zeros
                features.extend([0.0, 0.0, 0.0, 0.0])

        # Regime features
        if regime_features:
            regime = regime_features.get("regime", "neutral")
            vol_bucket = regime_features.get("vol_bucket", "unknown")

            # One-hot encode regime
            regime_bull = 1.0 if regime == "bull" else 0.0
            regime_bear = 1.0 if regime == "bear" else 0.0
            regime_range = 1.0 if regime == "range" else 0.0
            regime_neutral = 1.0 if regime == "neutral" else 0.0

            # One-hot encode vol_bucket
            vol_low = 1.0 if vol_bucket == "low" else 0.0
            vol_balanced = 1.0 if vol_bucket == "balanced" else 0.0
            vol_high = 1.0 if vol_bucket == "high" else 0.0

            features.extend([
                regime_bull,
                regime_bear,
                regime_range,
                regime_neutral,
                vol_low,
                vol_balanced,
                vol_high,
            ])
        else:
            # Default: neutral regime, unknown vol
            features.extend([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0])

        # Volatility state features
        if volatility_state:
            vol = float(volatility_state.get("volatility", 0.0))
            atr = float(volatility_state.get("atr", 0.0))
            features.extend([vol, atr])
        else:
            features.extend([0.0, 0.0])

        # Additional features from regime_features if available
        if regime_features:
            # Extract numeric features from features_regimen if available
            features_regimen = regime_features.get("features_regimen", {})
            if isinstance(features_regimen, dict):
                # Add momentum, RSI, etc. if available
                mom_1d = float(features_regimen.get("mom_1d", 0.0))
                rsi = float(features_regimen.get("rsi", 50.0)) / 100.0  # Normalize to 0-1
                features.extend([mom_1d, rsi])
            else:
                features.extend([0.0, 0.5])
        else:
            features.extend([0.0, 0.5])

        return np.array(features, dtype=np.float32)

    def fit(
        self,
        X: np.ndarray | pd.DataFrame,
        y: np.ndarray | pd.Series,
    ) -> dict[str, float]:
        """
        Train the meta-learner.
        
        Args:
            X: Feature matrix
            y: Target labels (0=HOLD/SELL, 1=BUY) or (0=HOLD/BUY, 1=SELL)
        
        Returns:
            Dict with training metrics
        """
        if isinstance(X, pd.DataFrame):
            self.feature_names = list(X.columns)
            X = X.values
        else:
            self.feature_names = [f"feature_{i}" for i in range(X.shape[1])]

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train model
        self.model.fit(X_scaled, y)
        self.is_fitted = True

        # Calculate training metrics
        y_pred_proba = self.model.predict_proba(X_scaled)[:, 1]
        y_pred = self.model.predict(X_scaled)

        metrics = {
            "roc_auc": float(roc_auc_score(y, y_pred_proba)) if len(np.unique(y)) > 1 else 0.0,
            "brier_score": float(brier_score_loss(y, y_pred_proba)),
            "log_loss": float(log_loss(y, y_pred_proba)),
            "accuracy": float(np.mean(y_pred == y)),
        }

        # Calibration curve
        try:
            fraction_of_positives, mean_predicted_value = calibration_curve(
                y, y_pred_proba, n_bins=10
            )
            # ECE (Expected Calibration Error)
            ece = float(np.mean(np.abs(fraction_of_positives - mean_predicted_value)))
            metrics["ece"] = ece
        except Exception as exc:
            logger.warning(f"Failed to calculate ECE: {exc}")
            metrics["ece"] = 1.0  # Worst case

        self.metrics = metrics
        logger.info(
            "Meta-learner trained",
            extra={
                "model_type": self.model_type,
                "regime": self.regime,
                "metrics": metrics,
            },
        )

        return metrics

    def predict_proba(
        self,
        X: np.ndarray | pd.DataFrame,
    ) -> np.ndarray:
        """
        Predict probabilities.
        
        Args:
            X: Feature matrix
        
        Returns:
            Array of shape (n_samples, 2) with probabilities for [class_0, class_1]
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")

        if isinstance(X, pd.DataFrame):
            X = X.values

        # Handle single sample
        if X.ndim == 1:
            X = X.reshape(1, -1)

        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)

    def predict(
        self,
        strategy_signals: list[dict[str, Any]],
        regime_features: dict[str, Any] | None = None,
        volatility_state: dict[str, Any] | None = None,
        task: str = "buy",
    ) -> dict[str, float]:
        """
        Predict probabilities for BUY/SELL given strategy signals.
        
        Args:
            strategy_signals: List of strategy signal dicts
            regime_features: Market regime features
            volatility_state: Volatility state
            task: Prediction task ("buy" or "sell")
        
        Returns:
            Dict with prob_buy, prob_sell, prob_hold, and signal
        """
        if not self.is_fitted:
            logger.warning("Meta-learner not fitted, returning uniform probabilities")
            return {
                "prob_buy": 0.33,
                "prob_sell": 0.33,
                "prob_hold": 0.34,
                "signal": "HOLD",
            }

        # Build features
        X = self.build_features(strategy_signals, regime_features, volatility_state)
        X = X.reshape(1, -1)

        # Predict
        proba = self.predict_proba(X)[0]

        if task == "buy":
            # Binary classification: BUY vs (SELL + HOLD)
            prob_buy = float(proba[1])
            prob_not_buy = float(proba[0])
            # Distribute not_buy between SELL and HOLD
            prob_sell = prob_not_buy * 0.5
            prob_hold = prob_not_buy * 0.5
        else:
            # For sell task, similar logic
            prob_sell = float(proba[1])
            prob_not_sell = float(proba[0])
            prob_buy = prob_not_sell * 0.5
            prob_hold = prob_not_sell * 0.5

        # Determine signal
        if prob_buy > prob_sell and prob_buy > prob_hold:
            signal = "BUY"
        elif prob_sell > prob_buy and prob_sell > prob_hold:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "prob_buy": prob_buy,
            "prob_sell": prob_sell,
            "prob_hold": prob_hold,
            "signal": signal,
        }

    def save(self, path: Path) -> None:
        """Save model to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "model_type": self.model_type,
            "regime": self.regime,
            "is_fitted": self.is_fitted,
            "metrics": self.metrics,
        }

        with open(path, "wb") as f:
            pickle.dump(model_data, f)

        logger.info(f"Saved meta-learner to {path}")

    @classmethod
    def load(cls, path: Path) -> MetaLearner:
        """Load model from disk."""
        with open(path, "rb") as f:
            model_data = pickle.load(f)

        instance = cls(
            model_type=model_data["model_type"],
            regime=model_data.get("regime"),
        )
        instance.model = model_data["model"]
        instance.scaler = model_data["scaler"]
        instance.feature_names = model_data["feature_names"]
        instance.is_fitted = model_data["is_fitted"]
        instance.metrics = model_data.get("metrics", {})

        logger.info(f"Loaded meta-learner from {path}")
        return instance

    def get_ece(self) -> float:
        """Get Expected Calibration Error."""
        return self.metrics.get("ece", 1.0)

