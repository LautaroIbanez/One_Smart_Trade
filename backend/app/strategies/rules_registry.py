"""Centralized registry of strategy entry and exit rules for traceability.

BE-STRAT-01: This module provides a single source of truth for all strategy rules,
ensuring that every trade can be traced back to its triggering conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.quant.config_manager import get_signal_params

PARAMS = get_signal_params()


@dataclass
class StrategyRule:
    """Documented strategy rule with entry/exit conditions."""
    
    strategy_name: str
    rule_type: str  # "entry" or "exit"
    signal_type: str  # "BUY", "SELL", or "HOLD"
    condition_description: str
    code_reference: str  # Function/class name where rule is implemented
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


class StrategyRulesRegistry:
    """Centralized registry of all strategy rules."""
    
    def __init__(self):
        self._rules: list[StrategyRule] = []
        self._load_rules()
    
    def _load_rules(self) -> None:
        """Load all strategy rules from implementations."""
        # Momentum Strategy Rules
        momentum_params = PARAMS.get("momentum", {})
        self._rules.extend([
            StrategyRule(
                strategy_name="momentum",
                rule_type="entry",
                signal_type="BUY",
                condition_description="Price > EMA9 > EMA21 > EMA50 > SMA200 AND MACD > MACD Signal",
                code_reference="app.quant.strategies.momentum_strategy",
                parameters={
                    "confidence_buy": momentum_params.get("confidence_buy", 65.0),
                },
                confidence=momentum_params.get("confidence_buy", 65.0),
            ),
            StrategyRule(
                strategy_name="momentum",
                rule_type="entry",
                signal_type="SELL",
                condition_description="Price < EMA9 < EMA21 < EMA50 < SMA200 AND MACD < MACD Signal",
                code_reference="app.quant.strategies.momentum_strategy",
                parameters={
                    "confidence_sell": momentum_params.get("confidence_sell", 65.0),
                },
                confidence=momentum_params.get("confidence_sell", 65.0),
            ),
            StrategyRule(
                strategy_name="momentum",
                rule_type="entry",
                signal_type="HOLD",
                condition_description="No trend alignment detected",
                code_reference="app.quant.strategies.momentum_strategy",
                parameters={
                    "confidence_hold": momentum_params.get("confidence_hold", 30.0),
                },
                confidence=momentum_params.get("confidence_hold", 30.0),
            ),
        ])
        
        # Mean Reversion Strategy Rules
        mean_reversion_params = PARAMS.get("mean_reversion", {})
        self._rules.extend([
            StrategyRule(
                strategy_name="mean_reversion",
                rule_type="entry",
                signal_type="BUY",
                condition_description="Price <= BB Lower AND RSI < RSI Buy Threshold",
                code_reference="app.quant.strategies.mean_reversion_strategy",
                parameters={
                    "rsi_buy": mean_reversion_params.get("rsi_buy", 30),
                    "confidence_buy": mean_reversion_params.get("confidence_buy", 55.0),
                },
                confidence=mean_reversion_params.get("confidence_buy", 55.0),
            ),
            StrategyRule(
                strategy_name="mean_reversion",
                rule_type="entry",
                signal_type="SELL",
                condition_description="Price >= BB Upper AND RSI > RSI Sell Threshold",
                code_reference="app.quant.strategies.mean_reversion_strategy",
                parameters={
                    "rsi_sell": mean_reversion_params.get("rsi_sell", 70),
                    "confidence_sell": mean_reversion_params.get("confidence_sell", 55.0),
                },
                confidence=mean_reversion_params.get("confidence_sell", 55.0),
            ),
            StrategyRule(
                strategy_name="mean_reversion",
                rule_type="entry",
                signal_type="HOLD",
                condition_description="Price within Bollinger Bands and RSI neutral",
                code_reference="app.quant.strategies.mean_reversion_strategy",
                parameters={
                    "confidence_hold": mean_reversion_params.get("confidence_hold", 25.0),
                },
                confidence=mean_reversion_params.get("confidence_hold", 25.0),
            ),
        ])
        
        # Breakout Strategy Rules
        breakout_params = PARAMS.get("breakout", {})
        self._rules.extend([
            StrategyRule(
                strategy_name="breakout",
                rule_type="entry",
                signal_type="BUY",
                condition_description="Price > Recent High (lookback) AND Volume > Volume Multiple * Avg Volume",
                code_reference="app.quant.strategies.breakout_strategy",
                parameters={
                    "lookback": breakout_params.get("lookback", 20),
                    "volume_multiple": breakout_params.get("volume_multiple", 1.5),
                    "confidence_buy": breakout_params.get("confidence_buy", 60.0),
                },
                confidence=breakout_params.get("confidence_buy", 60.0),
            ),
            StrategyRule(
                strategy_name="breakout",
                rule_type="entry",
                signal_type="SELL",
                condition_description="Price < Recent Low (lookback) AND Volume > Volume Multiple * Avg Volume",
                code_reference="app.quant.strategies.breakout_strategy",
                parameters={
                    "lookback": breakout_params.get("lookback", 20),
                    "volume_multiple": breakout_params.get("volume_multiple", 1.5),
                    "confidence_sell": breakout_params.get("confidence_sell", 60.0),
                },
                confidence=breakout_params.get("confidence_sell", 60.0),
            ),
            StrategyRule(
                strategy_name="breakout",
                rule_type="entry",
                signal_type="HOLD",
                condition_description="No breakout detected with sufficient volume",
                code_reference="app.quant.strategies.breakout_strategy",
                parameters={
                    "confidence_hold": breakout_params.get("confidence_hold", 20.0),
                },
                confidence=breakout_params.get("confidence_hold", 20.0),
            ),
        ])
        
        # Volatility Strategy Rules
        volatility_params = PARAMS.get("volatility", {})
        self._rules.extend([
            StrategyRule(
                strategy_name="volatility",
                rule_type="entry",
                signal_type="BUY",
                condition_description="Realized Volatility > High Threshold (prefer breakouts in high vol)",
                code_reference="app.quant.strategies.volatility_strategy",
                parameters={
                    "high_threshold": volatility_params.get("high_threshold", 0.5),
                    "confidence_high": volatility_params.get("confidence_high", 50.0),
                },
                confidence=volatility_params.get("confidence_high", 50.0),
            ),
            StrategyRule(
                strategy_name="volatility",
                rule_type="entry",
                signal_type="HOLD",
                condition_description="Realized Volatility < Low Threshold (low vol range) OR Mid Threshold",
                code_reference="app.quant.strategies.volatility_strategy",
                parameters={
                    "low_threshold": volatility_params.get("low_threshold", 0.2),
                    "confidence_low": volatility_params.get("confidence_low", 35.0),
                    "confidence_mid": volatility_params.get("confidence_mid", 30.0),
                },
                confidence=volatility_params.get("confidence_mid", 30.0),
            ),
        ])
        
        # Exit Rules (SL/TP)
        self._rules.extend([
            StrategyRule(
                strategy_name="risk_management",
                rule_type="exit",
                signal_type="SELL",
                condition_description="Price hits Stop Loss level",
                code_reference="app.backtesting.engine.BacktestEngine._check_stop_loss",
                parameters={},
            ),
            StrategyRule(
                strategy_name="risk_management",
                rule_type="exit",
                signal_type="SELL",
                condition_description="Price hits Take Profit level",
                code_reference="app.backtesting.engine.BacktestEngine._check_take_profit",
                parameters={},
            ),
            StrategyRule(
                strategy_name="risk_management",
                rule_type="exit",
                signal_type="SELL",
                condition_description="Trailing Stop triggered",
                code_reference="app.backtesting.engine.BacktestEngine._check_trailing_stop",
                parameters={},
            ),
            StrategyRule(
                strategy_name="signal_engine",
                rule_type="exit",
                signal_type="SELL",
                condition_description="Exit signal from strategy (opposite signal or HOLD after position)",
                code_reference="app.backtesting.engine.BacktestEngine.run_backtest",
                parameters={},
            ),
        ])
    
    def get_rules(self, strategy_name: str | None = None, rule_type: str | None = None, signal_type: str | None = None) -> list[StrategyRule]:
        """Get rules matching filters."""
        rules = self._rules
        if strategy_name:
            rules = [r for r in rules if r.strategy_name == strategy_name]
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        if signal_type:
            rules = [r for r in rules if r.signal_type == signal_type]
        return rules
    
    def find_rule(self, strategy_name: str, rule_type: str, signal_type: str, reason: str | None = None) -> StrategyRule | None:
        """Find a specific rule by strategy, type, and signal."""
        for rule in self._rules:
            if (rule.strategy_name == strategy_name and 
                rule.rule_type == rule_type and 
                rule.signal_type == signal_type):
                if reason is None or reason in rule.condition_description.lower():
                    return rule
        return None
    
    def get_all_rules(self) -> list[StrategyRule]:
        """Get all registered rules."""
        return self._rules.copy()
    
    def document_rules(self) -> dict[str, Any]:
        """Generate documentation of all rules."""
        by_strategy: dict[str, list[dict[str, Any]]] = {}
        for rule in self._rules:
            if rule.strategy_name not in by_strategy:
                by_strategy[rule.strategy_name] = []
            by_strategy[rule.strategy_name].append({
                "rule_type": rule.rule_type,
                "signal_type": rule.signal_type,
                "condition": rule.condition_description,
                "code_reference": rule.code_reference,
                "parameters": rule.parameters,
                "confidence": rule.confidence,
            })
        return {
            "strategies": by_strategy,
            "total_rules": len(self._rules),
        }


# Global registry instance
_rules_registry: StrategyRulesRegistry | None = None


def get_rules_registry() -> StrategyRulesRegistry:
    """Get the global strategy rules registry."""
    global _rules_registry
    if _rules_registry is None:
        _rules_registry = StrategyRulesRegistry()
    return _rules_registry

