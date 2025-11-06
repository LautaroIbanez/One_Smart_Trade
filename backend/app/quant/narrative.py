"""Narrative builder for professional textual analysis."""
from __future__ import annotations

from typing import Dict, Any


def build_narrative(signal_payload: Dict[str, Any]) -> str:
    s = signal_payload["signal"]
    conf = signal_payload["confidence"]
    ind = signal_payload.get("indicators", {})
    fac = signal_payload.get("factors", {})
    risk = signal_payload.get("risk_metrics", {})

    parts = []
    if s == "BUY":
        parts.append("Contexto alcista con confluencia multi-timeframe. ")
    elif s == "SELL":
        parts.append("Contexto bajista con señales de continuidad. ")
    else:
        parts.append("Contexto neutral; priorizar paciencia y gestión de riesgo. ")

    rsi = ind.get("rsi", 50)
    macd = ind.get("macd", 0)
    atr = ind.get("atr", 0)
    vol = ind.get("realized_vol", 0)
    parts.append(f"Confianza {conf:.1f}%. RSI {rsi:.1f}, MACD {macd:.4f}, ATR {atr:.2f}, Vol. {vol:.2f}. ")

    align = fac.get("momentum_alignment", 0)
    regime_d = fac.get("vol_regime_1d", fac.get("vol_regime_1h", 1))
    parts.append("Momentum 1h/1d alineado. " if align else "Momentum 1h/1d desalineado. ")
    parts.append("Régimen de volatilidad alto. " if regime_d == 2 else ("Régimen de volatilidad bajo. " if regime_d == 0 else "Régimen de volatilidad medio. "))

    rr = risk.get("risk_reward_ratio")
    if rr:
        parts.append(f"RR esperado {rr:.2f}. ")

    parts.append("Este contenido no es asesoramiento financiero; opere bajo su propio criterio.")
    return "".join(parts)


