"""Narrative builder for professional textual analysis."""
from __future__ import annotations

from typing import Dict, Any


def build_narrative(signal_payload: Dict[str, Any]) -> str:
    """
    Build professional textual analysis from signal payload.
    
    Args:
        signal_payload: Dict with signal, confidence, indicators, factors, risk_metrics
        
    Returns:
        Professional analysis text
    """
    s = signal_payload["signal"]
    conf = signal_payload["confidence"]
    ind = signal_payload.get("indicators", {})
    fac = signal_payload.get("factors", {})
    risk = signal_payload.get("risk_metrics", {})
    entry = signal_payload.get("entry_range", {})
    sl_tp = signal_payload.get("stop_loss_take_profit", {})

    parts = []
    
    # Signal context
    if s == "BUY":
        parts.append("Contexto alcista con confluencia multi-timeframe. ")
    elif s == "SELL":
        parts.append("Contexto bajista con señales de continuidad. ")
    else:
        parts.append("Contexto neutral; priorizar paciencia y gestión de riesgo. ")

    # Key indicators
    rsi = ind.get("rsi", 50)
    macd_val = ind.get("macd", 0)
    atr_val = ind.get("atr", 0)
    vol = ind.get("realized_vol", 0)
    parts.append(f"Confianza {conf:.1f}%. RSI {rsi:.1f}, MACD {macd_val:.4f}, ATR {atr_val:.2f}, Vol. {vol:.2f}. ")

    # Cross-timeframe factors
    align = fac.get("momentum_alignment", 0)
    regime_d = fac.get("vol_regime_1d", fac.get("vol_regime_1h", 1))
    if align:
        parts.append("Momentum 1h/1d alineado favorablemente. ")
    else:
        parts.append("Momentum 1h/1d desalineado; considerar esperar mejor entrada. ")
    
    if regime_d == 2:
        parts.append("Régimen de volatilidad alto; ajustar tamaño de posición. ")
    elif regime_d == 0:
        parts.append("Régimen de volatilidad bajo; condiciones favorables. ")
    else:
        parts.append("Régimen de volatilidad medio. ")

    # Risk metrics
    rr = risk.get("risk_reward_ratio", 0)
    if rr > 0:
        parts.append(f"Ratio riesgo/recompensa {rr:.2f}. ")
    
    sl_prob = risk.get("sl_probability", 0)
    tp_prob = risk.get("tp_probability", 0)
    if sl_prob > 0 and tp_prob > 0:
        parts.append(f"Probabilidad SL {sl_prob:.1f}%, TP {tp_prob:.1f}%. ")

    # Entry and levels
    if entry:
        opt = entry.get("optimal", 0)
        if opt > 0:
            parts.append(f"Entrada óptima ${opt:,.2f}. ")
    
    if sl_tp:
        sl = sl_tp.get("stop_loss", 0)
        tp = sl_tp.get("take_profit", 0)
        if sl > 0 and tp > 0:
            parts.append(f"Stop Loss ${sl:,.2f}, Take Profit ${tp:,.2f}. ")

    # Liquidity assessment
    volume_24h = ind.get("volume", 0)
    if isinstance(volume_24h, (int, float)) and volume_24h > 0:
        parts.append("Liquidez adecuada detectada. ")
    else:
        parts.append("Monitorear liquidez antes de ejecutar. ")

    parts.append("Este contenido no es asesoramiento financiero; opere bajo su propio criterio.")
    return "".join(parts)


def build_analysis(factors: Dict[str, Any], risk_metrics: Dict[str, Any], price: float, **kwargs) -> str:
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


