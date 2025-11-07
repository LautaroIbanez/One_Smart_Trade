from __future__ import annotations

from datetime import datetime
from typing import Any

TEMPLATE = """Contexto:
- Señal consolidada: {signal}
- Confianza histórica: {confidence:.1f}%
- Rango de entrada sugerido: {entry_min:.2f} – {entry_max:.2f} (óptimo {entry_opt:.2f})- Stop-loss / Take-profit: {sl:.2f} / {tp:.2f}

Indicadores clave:
- RSI(14): {rsi:.2f}
- ATR(14): {atr:.2f}
- Volatilidad 30d: {volatility:.2%}
- VWAP: {vwap:.2f}

Riesgo:
- Prob. tocar SL: {prob_sl:.1f}%
- Prob. tocar TP: {prob_tp:.1f}%
- Drawdown esperado: {drawdown:.2f}

Última actualización: {timestamp} UTC.
"""


def build_narrative(payload: dict[str, Any]) -> str:
    indicators = payload.get("indicators", {})
    risk = payload.get("risk_metrics", {})
    entry = payload.get("entry_range", {})
    sltp = payload.get("stop_loss_take_profit", {})

    return TEMPLATE.format(
        signal=payload.get("signal", "N/A"),
        confidence=payload.get("confidence", 0.0),
        entry_min=entry.get("min", 0.0),
        entry_max=entry.get("max", 0.0),
        entry_opt=entry.get("optimal", 0.0),
        sl=sltp.get("stop_loss", 0.0),
        tp=sltp.get("take_profit", 0.0),
        rsi=indicators.get("rsi_14", 0.0),
        atr=indicators.get("atr_14", 0.0),
        volatility=indicators.get("volatility_30", 0.0),
        vwap=indicators.get("vwap", 0.0),
        prob_sl=risk.get("sl_probability", 0.0),
        prob_tp=risk.get("tp_probability", 0.0),
        drawdown=risk.get("expected_drawdown", 0.0),
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    )


