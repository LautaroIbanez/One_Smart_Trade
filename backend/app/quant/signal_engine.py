"""Signal engine consolidating strategies with SL/TP and confidence."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np
import pandas as pd

from app.quant import indicators as ind
from app.quant.factors import cross_timeframe
from app.quant.strategies import momentum_strategy, mean_reversion_strategy, breakout_strategy, volatility_strategy


def _entry_range(df: pd.DataFrame, signal: str, current_price: float) -> Dict[str, float]:
    recent = df.tail(100)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    vwap_val = float(ind.vwap(df).iloc[-1])
    if signal == "BUY":
        mn = max(support, current_price * 0.995)
        mx = min(vwap_val * 1.005, current_price * 1.01)
    elif signal == "SELL":
        mn = max(current_price * 0.99, vwap_val * 0.995)
        mx = min(resistance, current_price * 1.005)
    else:
        mn = current_price * 0.998
        mx = current_price * 1.002
    opt = (mn + mx) / 2
    return {"min": round(mn, 2), "max": round(mx, 2), "optimal": round(opt, 2)}


def _sl_tp(df: pd.DataFrame, signal: str, entry: float) -> Dict[str, float]:
    a = ind.atr(df).iloc[-1]
    vol = ind.realized_volatility(df).iloc[-1]
    mult = 2.0
    if vol > 0.5:
        mult = 2.5
    elif vol < 0.2:
        mult = 1.5
    if signal == "BUY":
        sl = entry - mult * a
        tp = entry + mult * a * 2.5
    elif signal == "SELL":
        sl = entry + mult * a
        tp = entry - mult * a * 2.5
    else:
        sl = entry * 0.98
        tp = entry * 1.02
    return {
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "stop_loss_pct": round((sl - entry) / entry * 100, 2),
        "take_profit_pct": round((tp - entry) / entry * 100, 2),
    }


def _mc_confidence(df: pd.DataFrame, entry: float, sl: float, tp: float, trials: int = 500) -> float:
    """Very simple Monte Carlo using recent log-returns to estimate hit probabilities."""
    rets = np.log(df["close"]).diff().dropna().tail(500)
    if rets.empty:
        return 50.0
    mu = float(rets.mean())
    sigma = float(rets.std())
    price = float(df["close"].iloc[-1])
    horizon = 48  # steps (~2 days on 1h equivalent)
    wins = 0
    for _ in range(trials):
        p = price
        hit_tp = False
        hit_sl = False
        for _ in range(horizon):
            p *= float(np.exp(np.random.normal(mu, sigma)))
            if p >= tp:
                hit_tp = True
                break
            if p <= sl:
                hit_sl = True
                break
        if hit_tp and not hit_sl:
            wins += 1
    return float(wins / trials * 100)


def generate_signal(df_1h: pd.DataFrame, df_1d: pd.DataFrame) -> Dict[str, Any]:
    ind_1d = ind.calculate_all(df_1d)
    ind_1h = ind.calculate_all(df_1h)
    factors = cross_timeframe(df_1h, df_1d, ind_1h, ind_1d)

    s1 = momentum_strategy(df_1d, ind_1d)
    s2 = mean_reversion_strategy(df_1d, ind_1d)
    s3 = breakout_strategy(df_1d, ind_1d)
    s4 = volatility_strategy(df_1d, ind_1d)
    signals = [s1, s2, s3, s4]

    votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
    conf_sum = 0.0
    for s in signals:
        votes[s["signal"]] += 1
        conf_sum += s.get("confidence", 0.0)
    if votes["BUY"] > max(votes["SELL"], votes["HOLD"]):
        final_signal = "BUY"
    elif votes["SELL"] > max(votes["BUY"], votes["HOLD"]):
        final_signal = "SELL"
    else:
        final_signal = "HOLD"

    price = float(df_1d["close"].iloc[-1])
    entry = _entry_range(df_1d, final_signal, price)
    levels = _sl_tp(df_1d, final_signal, entry["optimal"])
    mc_conf = _mc_confidence(df_1d, entry["optimal"], levels["stop_loss"], levels["take_profit"])

    base_conf = min(conf_sum / len(signals), 90.0)
    agreement = max(votes.values()) / len(signals)
    final_conf = float(min(95.0, 0.6 * base_conf + 0.4 * mc_conf) * (0.8 + 0.2 * agreement))

    # Calculate risk metrics
    rr_ratio = abs((levels["take_profit"] - entry["optimal"]) / (entry["optimal"] - levels["stop_loss"])) if entry["optimal"] != levels["stop_loss"] else 0.0
    sl_prob = 100.0 - mc_conf  # Simplified: inverse of TP probability
    tp_prob = mc_conf
    expected_dd = abs(entry["optimal"] - levels["stop_loss"])
    vol = float(ind.realized_volatility(df_1d).iloc[-1]) if not ind.realized_volatility(df_1d).empty else 0.0

    risk_metrics = {
        "risk_reward_ratio": round(rr_ratio, 2),
        "sl_probability": round(sl_prob, 1),
        "tp_probability": round(tp_prob, 1),
        "expected_drawdown": round(expected_dd, 2),
        "volatility": round(vol, 2),
    }

    # Prepare indicators dict (extract last values from Series)
    indicators_dict = {}
    for k, v in ind_1d.items():
        if isinstance(v, pd.Series) and not v.empty:
            try:
                indicators_dict[k] = float(v.iloc[-1])
            except (ValueError, IndexError):
                pass
        elif isinstance(v, (int, float)):
            indicators_dict[k] = float(v)

    return {
        "signal": final_signal,
        "entry_range": entry,
        "stop_loss_take_profit": levels,
        "confidence": round(final_conf, 1),
        "current_price": round(price, 2),
        "factors": factors,
        "indicators": indicators_dict,
        "risk_metrics": risk_metrics,
        "votes": votes,
        "signals": signals,
    }


