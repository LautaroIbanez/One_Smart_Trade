"""Probabilistic regime classification using HMM and clustering."""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False


class HmmRegimeClassifier:
    """Hidden Markov Model based regime classifier."""

    def __init__(
        self,
        n_components: int = 3,
        covariance_type: str = "full",
        random_state: int | None = None,
    ) -> None:
        if not HMM_AVAILABLE:
            raise ImportError("hmmlearn is required for HMM regime classification. Install with: pip install hmmlearn")
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.random_state = random_state
        self.model: hmm.GaussianHMM | None = None
        self.scaler = StandardScaler()
        self.feature_names: list[str] = []
        self.regime_names: list[str] = ["calm", "balanced", "stress"]

    def fit(self, features: pd.DataFrame, *, regime_names: list[str] | None = None) -> None:
        """
        Fit HMM model to features.
        
        Args:
            features: DataFrame with columns [volatility, skew, volume] or similar
            regime_names: Optional custom names for regimes (default: calm, balanced, stress)
        """
        if features.empty:
            raise ValueError("Features dataframe cannot be empty")
        self.feature_names = list(features.columns)
        if regime_names and len(regime_names) == self.n_components:
            self.regime_names = regime_names
        elif len(self.regime_names) != self.n_components:
            self.regime_names = [f"regime_{i}" for i in range(self.n_components)]
        
        X_scaled = self.scaler.fit_transform(features.values)
        self.model = hmm.GaussianHMM(
            n_components=self.n_components,
            covariance_type=self.covariance_type,
            random_state=self.random_state,
            n_iter=100,
        )
        self.model.fit(X_scaled)

    def predict_proba(self, features: pd.DataFrame) -> pd.DataFrame:
        """
        Predict regime probabilities for features.
        
        Returns:
            DataFrame with columns [calm, balanced, stress] and probabilities per row
        """
        if self.model is None:
            raise ValueError("Model must be fitted before prediction")
        if features.empty:
            return pd.DataFrame(columns=self.regime_names)
        
        X_scaled = self.scaler.transform(features.values)
        logprob, posterior = self.model.score_samples(X_scaled)
        
        result = pd.DataFrame(
            posterior,
            index=features.index,
            columns=self.regime_names,
        )
        return result

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """Predict most likely regime for each observation."""
        proba = self.predict_proba(features)
        return proba.idxmax(axis=1)


class KMeansRegimeClassifier:
    """K-means clustering based regime classifier with probabilistic outputs."""

    def __init__(
        self,
        n_clusters: int = 3,
        random_state: int | None = None,
    ) -> None:
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.model: KMeans | None = None
        self.scaler = StandardScaler()
        self.feature_names: list[str] = []
        self.regime_names: list[str] = ["calm", "balanced", "stress"]

    def fit(self, features: pd.DataFrame, *, regime_names: list[str] | None = None) -> None:
        """
        Fit K-means model to features.
        
        Args:
            features: DataFrame with columns [volatility, skew, volume] or similar
            regime_names: Optional custom names for regimes
        """
        if features.empty:
            raise ValueError("Features dataframe cannot be empty")
        self.feature_names = list(features.columns)
        if regime_names and len(regime_names) == self.n_clusters:
            self.regime_names = regime_names
        elif len(self.regime_names) != self.n_clusters:
            self.regime_names = [f"regime_{i}" for i in range(self.n_clusters)]
        
        X_scaled = self.scaler.fit_transform(features.values)
        self.model = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10,
        )
        self.model.fit(X_scaled)

    def predict_proba(self, features: pd.DataFrame) -> pd.DataFrame:
        """
        Predict regime probabilities using soft assignments based on distance to centroids.
        
        Returns:
            DataFrame with columns [calm, balanced, stress] and probabilities per row
        """
        if self.model is None:
            raise ValueError("Model must be fitted before prediction")
        if features.empty:
            return pd.DataFrame(columns=self.regime_names)
        
        X_scaled = self.scaler.transform(features.values)
        distances = self.model.transform(X_scaled)
        
        epsilon = 1e-10
        inv_distances = 1.0 / (distances + epsilon)
        soft_proba = inv_distances / inv_distances.sum(axis=1, keepdims=True)
        
        result = pd.DataFrame(
            soft_proba,
            index=features.index,
            columns=self.regime_names,
        )
        return result

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """Predict most likely regime for each observation."""
        proba = self.predict_proba(features)
        return proba.idxmax(axis=1)


class RegimeClassifier:
    """
    Unified regime classifier supporting HMM and K-means with rolling window training.
    """

    def __init__(
        self,
        method: Literal["hmm", "kmeans"] = "hmm",
        n_regimes: int = 3,
        window_size: int = 252,
        regime_names: list[str] | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize regime classifier.
        
        Args:
            method: Classification method ("hmm" or "kmeans")
            n_regimes: Number of regimes to identify
            window_size: Rolling window size for training (default: 252 trading days)
            regime_names: Custom regime names
            **kwargs: Additional arguments for underlying classifier
        """
        self.method = method
        self.n_regimes = n_regimes
        self.window_size = window_size
        self.regime_names = regime_names or ["calm", "balanced", "stress"]
        
        if method == "hmm":
            if not HMM_AVAILABLE:
                raise ImportError("hmmlearn is required for HMM. Install with: pip install hmmlearn")
            self.classifier = HmmRegimeClassifier(
                n_components=n_regimes,
                regime_names=self.regime_names,
                **kwargs,
            )
        elif method == "kmeans":
            self.classifier = KMeansRegimeClassifier(
                n_clusters=n_regimes,
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported method: {method}. Must be 'hmm' or 'kmeans'")

    def extract_features(
        self,
        df: pd.DataFrame,
        *,
        volatility_col: str = "realized_vol",
        volume_col: str = "volume",
    ) -> pd.DataFrame:
        """
        Extract features for regime classification.
        
        Args:
            df: DataFrame with OHLCV and indicator columns
            volatility_col: Column name for volatility
            volume_col: Column name for volume
            
        Returns:
            DataFrame with columns [volatility, skew, volume]
        """
        features = {}
        
        if volatility_col in df.columns:
            features["volatility"] = df[volatility_col].bfill().fillna(0.0)
        else:
            returns = df["close"].pct_change()
            features["volatility"] = returns.rolling(window=20).std() * np.sqrt(252)
        
        returns = df["close"].pct_change()
        features["skew"] = returns.rolling(window=30).skew().fillna(0.0)
        
        if volume_col in df.columns:
            volume = df[volume_col].fillna(0.0)
            volume_ma = volume.rolling(window=20).mean()
            features["volume"] = (volume / volume_ma.replace(0, np.nan)).fillna(1.0)
        else:
            features["volume"] = pd.Series(1.0, index=df.index)
        
        result = pd.DataFrame(features, index=df.index)
        result = result.dropna()
        return result

    def fit_rolling(
        self,
        features: pd.DataFrame,
        *,
        refit_every: int = 21,
    ) -> None:
        """
        Fit model using rolling window training.
        
        Args:
            features: Feature DataFrame
            refit_every: Retrain model every N observations (default: 21 = monthly)
        """
        if len(features) < self.window_size:
            window_features = features
        else:
            window_features = features.tail(self.window_size)
        
        self.classifier.fit(window_features, regime_names=self.regime_names)

    def predict_proba(self, features: pd.DataFrame) -> pd.DataFrame:
        """
        Predict regime probabilities.
        
        Returns:
            DataFrame with regime probabilities per row
        """
        return self.classifier.predict_proba(features)

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """Predict most likely regime."""
        return self.classifier.predict(features)

    def fit_predict_proba(
        self,
        df: pd.DataFrame,
        *,
        refit_every: int = 21,
        volatility_col: str = "realized_vol",
        volume_col: str = "volume",
    ) -> pd.DataFrame:
        """
        Extract features, fit model, and predict probabilities in one step.
        
        Args:
            df: Input DataFrame with OHLCV data
            refit_every: Retrain frequency
            volatility_col: Column name for volatility
            volume_col: Column name for volume
            
        Returns:
            DataFrame with regime probabilities
        """
        features = self.extract_features(df, volatility_col=volatility_col, volume_col=volume_col)
        self.fit_rolling(features, refit_every=refit_every)
        return self.predict_proba(features)

