"""Narrative builder for professional textual analysis."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TEMPLATE = """Contexto:
- Señal consolidada: {signal}
- Entrada sugerida: {entry_min:.2f} - {entry_max:.2f}
- Stop-loss: {stop_loss:.2f} | Take-profit: {take_profit:.2f}
- Confianza histórica: {confidence:.1%}

Indicadores:
- RSI(14): {rsi_14:.2f}
- ATR(14): {atr_14:.2f}
- Volatilidad 30d: {volatility_30:.2%}

Riesgo:
- Prob. tocar SL: {prob_stop_loss:.1%}
- Prob. tocar TP: {prob_take_profit:.1%}
- Drawdown esperado: {expected_drawdown:.2%}

Última actualización: {timestamp} UTC.
"""


def build_narrative(signal_payload: dict[str, Any]) -> str:
    """
    Build professional textual analysis from signal payload using template.

    Args:
        signal_payload: Dict with signal, confidence, indicators, factors, risk_metrics, entry_range, stop_loss_take_profit

    Returns:
        Professional analysis text
    """
    import math

    def safe_float(val, default=0.0):
        """Safely convert value to float, handling NaN/Inf."""
        try:
            fval = float(val)
            return fval if not (math.isnan(fval) or math.isinf(fval)) else default
        except (ValueError, TypeError):
            return default

    # Extract values with safe defaults
    signal = signal_payload.get("signal", "HOLD")
    confidence = safe_float(signal_payload.get("confidence", 50.0)) / 100.0  # Convert to decimal

    entry_range = signal_payload.get("entry_range", {})
    entry_min = safe_float(entry_range.get("min", 0.0))
    entry_max = safe_float(entry_range.get("max", 0.0))

    sl_tp = signal_payload.get("stop_loss_take_profit", {})
    stop_loss = safe_float(sl_tp.get("stop_loss", 0.0))
    take_profit = safe_float(sl_tp.get("take_profit", 0.0))

    indicators = signal_payload.get("indicators", {})
    rsi_14 = safe_float(indicators.get("rsi_14", indicators.get("rsi", 50.0)))
    atr_14 = safe_float(indicators.get("atr_14", indicators.get("atr", 0.0)))
    volatility_30 = safe_float(indicators.get("volatility_30", indicators.get("realized_volatility", 0.0))) / 100.0  # Convert to decimal

    risk_metrics = signal_payload.get("risk_metrics", {})
    prob_stop_loss = safe_float(risk_metrics.get("sl_probability", 0.0)) / 100.0  # Convert to decimal
    prob_take_profit = safe_float(risk_metrics.get("tp_probability", 0.0)) / 100.0  # Convert to decimal
    expected_drawdown = safe_float(risk_metrics.get("expected_drawdown", 0.0))

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    try:
        return TEMPLATE.format(
            signal=signal,
            entry_min=entry_min,
            entry_max=entry_max,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            rsi_14=rsi_14,
            atr_14=atr_14,
            volatility_30=volatility_30,
            prob_stop_loss=prob_stop_loss,
            prob_take_profit=prob_take_profit,
            expected_drawdown=expected_drawdown,
            timestamp=timestamp,
        )
    except (KeyError, ValueError):
        # Fallback to a simpler narrative if template fails
        return f"Señal: {signal}, Confianza: {confidence:.1%}, RSI: {rsi_14:.2f}, ATR: {atr_14:.2f}. Última actualización: {timestamp} UTC."


def build_analysis(factors: dict[str, Any], risk_metrics: dict[str, Any], **kwargs) -> str:
    """
    Build analysis text from factors and risk metrics.

    This is a convenience wrapper around build_narrative for backward compatibility.
    """
    payload = {
        "signal": kwargs.get("signal", "HOLD"),
        "confidence": kwargs.get("confidence", 50.0),
        "indicators": kwargs.get("indicators", {}),
        "factors": factors,
        "risk_metrics": risk_metrics,
        "entry_range": kwargs.get("entry_range", {}),
        "stop_loss_take_profit": kwargs.get("stop_loss_take_profit", {}),
    }
    return build_narrative(payload)


