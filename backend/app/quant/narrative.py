from __future__ import annotations

from datetime import datetime
from typing import Any

TEMPLATE = """Contexto:
- Señal consolidada: {signal}
- Confianza: {confidence:.1f}%
- Rango de entrada: {entry_min:.2f} – {entry_max:.2f} (óptimo {entry_opt:.2f})
- Stop-loss / Take-profit: {sl:.2f} / {tp:.2f}

Indicadores clave:
- RSI(14): {rsi:.2f}
- ATR(14): {atr:.2f}
- Volatilidad 30 días: {vol:.2%}
- Volumen reciente: {volume:.0f}

Riesgo:
- Prob. tocar SL: {sl_prob:.1f}%
- Prob. tocar TP: {tp_prob:.1f}%
- Drawdown esperado: {dd:.2f}

Generado {timestamp} UTC."""


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
        vol=indicators.get("volatility_30", 0.0),
        volume=indicators.get("volume", 0.0),
        sl_prob=risk.get("sl_probability", 0.0),
        tp_prob=risk.get("tp_probability", 0.0),
        dd=risk.get("expected_drawdown", 0.0),
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    )


