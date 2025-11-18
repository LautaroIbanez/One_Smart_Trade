"""Strategy ensemble for signal consolidation."""
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.core.config import settings
from app.core.logging import logger
from app.strategies.base import BaseStrategy, SignalType
from app.strategies.breakout import BreakoutStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.momentum_trend import MomentumTrendStrategy
from app.strategies.meta_learner import MetaLearner
from app.strategies.performance_store import StrategyPerformanceStore
from app.strategies.weight_store import MetaWeightStore
from app.quant.regime import RegimeClassifier


class StrategyEnsemble:
    """Combine multiple strategies into consolidated signal."""

    def __init__(
        self,
        weight_store: MetaWeightStore | None = None,
        regime: str | None = None,
        meta_learner_path: Path | str | None = None,
        ece_threshold: float = 0.15,
        config_path: Path | str | None = None,
    ):
        """
        Initialize strategy ensemble.
        
        Args:
            weight_store: Optional weight store for dynamic weights
            regime: Optional current market regime (auto-detected if None)
            meta_learner_path: Path to meta-learner models directory (default: artifacts/meta_learner)
            ece_threshold: ECE threshold above which to degrade to voting (default: 0.15)
            config_path: Path to ensemble config YAML (default: config/ensemble.yaml)
        """
        self.strategies: list[BaseStrategy] = [
            MomentumTrendStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
        ]
        self.weight_store = weight_store or MetaWeightStore()
        self.regime = regime
        self.strategy_weights = self._load_weights()
        self.ece_threshold = ece_threshold
        
        # Load configuration
        if config_path is None:
            # Try multiple possible paths
            possible_paths = [
                Path("config/ensemble.yaml"),
                Path("backend/config/ensemble.yaml"),
                Path(__file__).parent.parent.parent / "config" / "ensemble.yaml",
            ]
            config_path = None
            for path in possible_paths:
                if path.exists():
                    config_path = path
                    break
            if config_path is None:
                config_path = Path("config/ensemble.yaml")  # Default, will use defaults if not found
        elif isinstance(config_path, str):
            config_path = Path(config_path)
        self.config = self._load_config(config_path)
        
        # Setup meta-learner path
        if meta_learner_path is None:
            meta_learner_path = Path("artifacts/meta_learner")
        elif isinstance(meta_learner_path, str):
            meta_learner_path = Path(meta_learner_path)
        self.meta_learner_path = meta_learner_path
        self.meta_learner: MetaLearner | None = None
        self._load_meta_learner()
        
        # Setup performance store for correlation/MAE/MFE
        self.performance_store = StrategyPerformanceStore()

    def _load_weights(self) -> dict[str, float]:
        """Load dynamic weights from store, fallback to uniform if not available."""
        try:
            weights = self.weight_store.load(regime=self.regime, fallback_to_latest=True)
            if weights:
                # Ensure all strategies have weights (fill missing with 0)
                for strategy in self.strategies:
                    if strategy.name not in weights:
                        weights[strategy.name] = 0.0
                
                # Normalize to sum to 1.0
                total = sum(weights.values())
                if total > 0:
                    weights = {name: w / total for name, w in weights.items()}
                else:
                    # Fallback to uniform
                    weights = {s.name: 1.0 / len(self.strategies) for s in self.strategies}
                
                logger.debug(
                    "Loaded dynamic weights",
                    extra={"regime": self.regime, "weights": weights},
                )
                return weights
        except Exception as exc:
            logger.warning(
                "Failed to load dynamic weights, using uniform",
                extra={"regime": self.regime, "error": str(exc)},
            )
        
        # Fallback to uniform weights
        uniform_weights = {s.name: 1.0 / len(self.strategies) for s in self.strategies}
        logger.debug("Using uniform weights", extra={"weights": uniform_weights})
        return uniform_weights

    def _detect_regime(self, df: pd.DataFrame) -> str:
        """Detect market regime from price data."""
        try:
            classifier = RegimeClassifier(method="hmm", n_regimes=3)
            regime_proba = classifier.fit_predict_proba(df)
            
            if regime_proba.empty:
                return "neutral"
            
            latest = regime_proba.iloc[-1]
            
            if "stress" in latest.index:
                p_stress = latest.get("stress", 0.0)
                p_calm = latest.get("calm", 0.0)
                p_balanced = latest.get("balanced", 0.0)
                
                if p_stress > 0.5:
                    return "bear"
                elif p_calm > 0.5:
                    return "bull"
                elif p_balanced > 0.4:
                    return "range"
            
            return "neutral"
        except Exception:
            return "neutral"

    def _load_meta_learner(self) -> None:
        """Load meta-learner for current regime."""
        if self.regime is None:
            return

        model_path = self.meta_learner_path / self.regime / "model.pkl"
        
        if not model_path.exists():
            logger.debug(
                f"Meta-learner not found for regime {self.regime}, will use voting",
                extra={"model_path": str(model_path)},
            )
            return

        try:
            self.meta_learner = MetaLearner.load(model_path)
            ece = self.meta_learner.get_ece()
            
            if ece > self.ece_threshold:
                logger.warning(
                    f"Meta-learner ECE ({ece:.3f}) exceeds threshold ({self.ece_threshold}), "
                    "will degrade to voting",
                    extra={"regime": self.regime, "ece": ece, "threshold": self.ece_threshold},
                )
                self.meta_learner = None
            else:
                logger.info(
                    f"Loaded meta-learner for regime {self.regime}",
                    extra={"ece": ece, "model_path": str(model_path)},
                )
        except Exception as exc:
            logger.warning(
                f"Failed to load meta-learner for regime {self.regime}",
                extra={"error": str(exc), "model_path": str(model_path)},
            )
            self.meta_learner = None

    def consolidate_signals(self, df: pd.DataFrame, indicators: dict[str, Any]) -> dict[str, Any]:
        """Consolidate signals from all strategies."""
        # Auto-detect regime if not set
        if self.regime is None:
            self.regime = self._detect_regime(df)
            # Reload weights with detected regime
            self.strategy_weights = self._load_weights()
            # Load meta-learner for detected regime
            self._load_meta_learner()
        
        signals: list[dict[str, Any]] = []
        weighted_confidence = 0.0
        valid_weight_total = 0.0

        for strategy in self.strategies:
            try:
                signal_data = strategy.generate_signal(df, indicators)
                signals.append(
                    {
                        "strategy": strategy.name,
                        "signal": signal_data["signal"],
                        "confidence": signal_data.get("confidence", 0.0),
                        "reason": signal_data.get("reason", ""),
                    }
                )
                weight = self.strategy_weights.get(strategy.name, 0.0)
                reason = signal_data.get("reason", "").lower()
                confidence = float(signal_data.get("confidence", 0.0))
                is_valid = confidence > 0.0 and "missing" not in reason
                if is_valid:
                    weighted_confidence += confidence * weight
                    valid_weight_total += weight
            except Exception:
                continue

        if not signals:
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "strategies": [],
                "decision_reason": "no_signals",
            }

        # Check no-trade rules
        should_hold, no_trade_reason = self._check_no_trade_rules(signals, indicators)
        if should_hold:
            logger.info(
                "No-trade rule triggered",
                extra={"reason": no_trade_reason, "signals": [s["signal"] for s in signals]},
            )
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "agreement": max(
                    sum(1 for s in signals if s["signal"] == "BUY"),
                    sum(1 for s in signals if s["signal"] == "SELL"),
                    sum(1 for s in signals if s["signal"] == "HOLD"),
                ) / len(signals) if signals else 0.0,
                "buy_votes": sum(1 for s in signals if s["signal"] == "BUY"),
                "sell_votes": sum(1 for s in signals if s["signal"] == "SELL"),
                "hold_votes": sum(1 for s in signals if s["signal"] == "HOLD"),
                "strategies": signals,
                "decision_reason": no_trade_reason,
                "meta_learner_used": False,
            }

        # Try to use meta-learner if available
        use_meta_learner = False
        meta_learner_result = None
        
        if self.meta_learner is not None and self.meta_learner.is_fitted:
            try:
                # Build regime features
                regime_features = {
                    "regime": self.regime,
                    "vol_bucket": self._get_vol_bucket(df, indicators),
                    "features_regimen": indicators,
                }
                
                # Build volatility state
                volatility_state = {
                    "volatility": float(indicators.get("realized_volatility", 0.0)),
                    "atr": float(indicators.get("atr", 0.0)),
                }
                
                # Predict using meta-learner
                meta_learner_result = self.meta_learner.predict(
                    signals,
                    regime_features,
                    volatility_state,
                    task="buy",
                )
                
                # Check ECE threshold
                ece = self.meta_learner.get_ece()
                if ece <= self.ece_threshold:
                    use_meta_learner = True
                else:
                    logger.warning(
                        f"Meta-learner ECE ({ece:.3f}) exceeds threshold, degrading to voting",
                        extra={"regime": self.regime, "ece": ece},
                    )
                    # Alert service would be called here
                    from app.services.alert_service import AlertService
                    alerts = AlertService()
                    alerts.notify(
                        "meta_learner.degraded",
                        f"Meta-learner degraded to voting due to high ECE ({ece:.3f})",
                        payload={"regime": self.regime, "ece": ece, "threshold": self.ece_threshold},
                    )
            except Exception as exc:
                logger.warning(
                    "Meta-learner prediction failed, falling back to voting",
                    extra={"error": str(exc)},
                )

        # Use meta-learner result or fall back to voting
        if use_meta_learner and meta_learner_result:
            consolidated_signal = meta_learner_result["signal"]
            prob_buy = meta_learner_result["prob_buy"]
            prob_sell = meta_learner_result["prob_sell"]
            prob_hold = meta_learner_result["prob_hold"]
            
            # Use probability as confidence
            if consolidated_signal == "BUY":
                final_confidence = prob_buy * 100.0
            elif consolidated_signal == "SELL":
                final_confidence = prob_sell * 100.0
            else:
                final_confidence = prob_hold * 100.0
            
            # Calculate agreement from probabilities
            agreement = max(prob_buy, prob_sell, prob_hold)

        buy_votes = sum(1 for s in signals if s["signal"] == "BUY")
        sell_votes = sum(1 for s in signals if s["signal"] == "SELL")
        hold_votes = sum(1 for s in signals if s["signal"] == "HOLD")
            
            return {
                "signal": consolidated_signal,
                "confidence": min(final_confidence, 95.0),
                "agreement": agreement,
                "buy_votes": buy_votes,
                "sell_votes": sell_votes,
                "hold_votes": hold_votes,
                "strategies": signals,
                "meta_learner_used": True,
                "meta_learner_probs": {
                    "prob_buy": prob_buy,
                    "prob_sell": prob_sell,
                    "prob_hold": prob_hold,
                },
                "decision_reason": "meta_learner",
            }
        else:
            # Fallback to classic voting
        buy_votes = sum(1 for s in signals if s["signal"] == "BUY")
        sell_votes = sum(1 for s in signals if s["signal"] == "SELL")
        hold_votes = sum(1 for s in signals if s["signal"] == "HOLD")

        if buy_votes > sell_votes and buy_votes > hold_votes:
            consolidated_signal: SignalType = "BUY"
        elif sell_votes > buy_votes and sell_votes > hold_votes:
            consolidated_signal = "SELL"
        else:
            consolidated_signal = "HOLD"

        agreement = max(buy_votes, sell_votes, hold_votes) / len(signals) if signals else 0.0
        base_confidence = (
            weighted_confidence / valid_weight_total if valid_weight_total > 0 else 0.0
        )
        integrity_factor = max(min(valid_weight_total, 1.0), 0.0)
        final_confidence = min(base_confidence * agreement * (0.6 + 0.4 * integrity_factor), 90.0)

        return {
            "signal": consolidated_signal,
            "confidence": final_confidence,
            "agreement": agreement,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "hold_votes": hold_votes,
            "strategies": signals,
                "meta_learner_used": False,
                "decision_reason": "voting",
            }

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        """Load ensemble configuration from YAML."""
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
                    return config.get("no_trade_rules", {})
            else:
                logger.warning(f"Config file not found: {config_path}, using defaults")
                return self._default_config()
        except Exception as exc:
            logger.warning(f"Failed to load config: {exc}, using defaults")
            return self._default_config()

    def _default_config(self) -> dict[str, Any]:
        """Return default configuration."""
        return {
            "min_agreement": 0.67,
            "max_cross_corr": 0.75,
            "min_rr": 1.2,
            "correlation_window_days": 30,
            "mae_mfe_window_days": 60,
            "enabled": True,
            "require_unanimous_on_conflict": True,
        }

    def _check_no_trade_rules(
        self,
        signals: list[dict[str, Any]],
        indicators: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """
        Check if no-trade rules should be applied.
        
        Args:
            signals: List of strategy signals
            indicators: Market indicators
        
        Returns:
            Tuple of (should_hold, reason)
        """
        if not self.config.get("enabled", True):
            return False, None

        reasons = []

        # Check agreement
        buy_votes = sum(1 for s in signals if s["signal"] == "BUY")
        sell_votes = sum(1 for s in signals if s["signal"] == "SELL")
        hold_votes = sum(1 for s in signals if s["signal"] == "HOLD")
        total_votes = len(signals)

        if total_votes == 0:
            return True, "no_signals"

        agreement = max(buy_votes, sell_votes, hold_votes) / total_votes
        min_agreement = self.config.get("min_agreement", 0.67)

        if agreement < min_agreement:
            reasons.append(f"agreement_too_low_{agreement:.2f}")

        # Check for BUY vs SELL conflict
        if self.config.get("require_unanimous_on_conflict", True):
            if buy_votes > 0 and sell_votes > 0:
                reasons.append("buy_sell_conflict")

        # Check correlation
        strategy_names = [s["strategy"] for s in signals]
        max_cross_corr = self.config.get("max_cross_corr", 0.75)
        correlation_window = self.config.get("correlation_window_days", 30)

        try:
            corr_matrix = self.performance_store.calculate_correlation_matrix(
                strategy_names,
                window_days=correlation_window,
                regime=self.regime,
            )

            # Check if any correlation exceeds threshold
            for strategy, correlations in corr_matrix.items():
                for other_strategy, corr in correlations.items():
                    if abs(corr) > max_cross_corr:
                        reasons.append(f"high_correlation_{strategy}_{other_strategy}_{corr:.2f}")
        except Exception as exc:
            logger.warning(f"Failed to calculate correlation: {exc}")

        # Check expected RR
        min_rr = self.config.get("min_rr", 1.2)
        mae_mfe_window = self.config.get("mae_mfe_window_days", 60)

        try:
            # Calculate weighted expected RR
            total_weight = 0.0
            weighted_rr = 0.0

            for signal in signals:
                strategy_name = signal["strategy"]
                weight = self.strategy_weights.get(strategy_name, 0.0)

                if weight > 0:
                    mae_mfe = self.performance_store.get_strategy_mae_mfe(
                        strategy_name,
                        window_days=mae_mfe_window,
                        regime=self.regime,
                    )

                    rr = mae_mfe.get("rr_expected", 0.0)
                    if rr > 0:
                        weighted_rr += rr * weight
                        total_weight += weight

            if total_weight > 0:
                expected_rr = weighted_rr / total_weight
                if expected_rr < min_rr:
                    reasons.append(f"expected_rr_too_low_{expected_rr:.2f}")
        except Exception as exc:
            logger.warning(f"Failed to calculate expected RR: {exc}")

        if reasons:
            reason = "; ".join(reasons)
            return True, reason

        return False, None

    def _get_vol_bucket(self, df: pd.DataFrame, indicators: dict[str, Any]) -> str:
        """Get volatility bucket from indicators."""
        vol = indicators.get("realized_volatility", 0.0)
        if isinstance(vol, (int, float)):
            if vol < 0.2:
                return "low"
            elif vol > 0.5:
                return "high"
            else:
                return "balanced"
        return "unknown"

