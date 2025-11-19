"""Signal engine consolidating strategies with SL/TP and confidence."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.data.signal_data_provider import SignalDataInputs
from app.quant import indicators as ind
from app.quant.factors import cross_timeframe
from app.quant.regime import RegimeClassifier
from app.quant.strategies import (
    breakout_strategy,
    mean_reversion_strategy,
    momentum_strategy,
    volatility_strategy,
    PARAMS as STRATEGY_PARAMS,
)
from app.utils.seeding import generate_deterministic_seed


def _entry_range(df: pd.DataFrame, signal: str, current_price: float) -> dict[str, float]:
    recent = df.tail(100)
    support_raw = float(recent["low"].min())
    resistance_raw = float(recent["high"].max())
    # Use curated vwap if available, otherwise calculate
    if "vwap" in df.columns and not df["vwap"].empty:
        vwap_val = float(df["vwap"].iloc[-1])
    else:
        vwap_val = float(ind.vwap(df).iloc[-1])

    band = 0.02  # 2% anchor band around current price
    support_anchor = float(np.clip(support_raw, current_price * (1 - band), current_price))
    resistance_anchor = float(np.clip(resistance_raw, current_price, current_price * (1 + band)))
    vwap_buy_anchor = float(np.clip(vwap_val, current_price * (1 - band / 2), current_price))
    vwap_sell_anchor = float(np.clip(vwap_val, current_price, current_price * (1 + band / 2)))

    if signal == "BUY":
        anchor = max(support_anchor, vwap_buy_anchor)
        anchor = min(anchor, current_price * (1 - band / 4))
        lower = max(anchor * 0.995, current_price * (1 - band))
        upper_candidates = [
            current_price * 0.999,
            anchor * 1.01,
            resistance_anchor,
        ]
        upper_candidates = [val for val in upper_candidates if val > lower]
        upper = min(upper_candidates) if upper_candidates else lower * 1.01
        upper = min(upper, current_price)
    elif signal == "SELL":
        anchor = min(resistance_anchor, vwap_sell_anchor)
        anchor = max(anchor, current_price * (1 + band / 4))
        upper = min(anchor * 1.005, current_price * (1 + band))
        lower_candidates = [
            current_price * 1.001,
            anchor * 0.99,
            support_anchor,
        ]
        lower_candidates = [val for val in lower_candidates if val < upper]
        lower = max(lower_candidates) if lower_candidates else upper * 0.99
        lower = max(lower, current_price)
    else:
        lower = current_price * 0.998
        upper = current_price * 1.002

    if upper <= lower:
        midpoint = (lower + upper) / 2 if upper != lower else lower
        adjust = abs(current_price) * 0.002 or 1.0
        lower = midpoint - adjust
        upper = midpoint + adjust

    opt = np.clip((lower + upper) / 2, lower, upper)
    return {"min": round(lower, 2), "max": round(upper, 2), "optimal": round(opt, 2)}


def _sl_tp(df: pd.DataFrame, signal: str, entry: float) -> dict[str, float]:
    # Use curated atr if available, otherwise calculate
    if "atr_14" in df.columns and not df["atr_14"].empty:
        a = float(df["atr_14"].iloc[-1])
    elif "atr" in df.columns and not df["atr"].empty:
        a = float(df["atr"].iloc[-1])
    else:
        a = ind.atr(df).iloc[-1]

    # Use curated volatility if available, otherwise calculate
    if "volatility_30" in df.columns and not df["volatility_30"].empty:
        vol = float(df["volatility_30"].iloc[-1])
    elif "realized_volatility" in df.columns and not df["realized_volatility"].empty:
        vol = float(df["realized_volatility"].iloc[-1])
    else:
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


def _mc_confidence(df: pd.DataFrame, entry: float, sl: float, tp: float, trials: int = 2000, seed: int | None = None) -> float:
    rets = np.log(df["close"]).diff().dropna().tail(750)
    if len(rets) < 50:
        return 50.0
    drift = float(rets.mean())
    vol = float(rets.std())
    dt = 1.0 / 24.0
    steps = 72
    # Use deterministic seed if provided
    if seed is not None:
        rng = np.random.default_rng(seed)
        shocks = rng.normal(drift * dt, vol * np.sqrt(dt), size=(trials, steps))
    else:
        shocks = np.random.normal(drift * dt, vol * np.sqrt(dt), size=(trials, steps))
    price_paths = entry * np.exp(np.cumsum(shocks, axis=1))
    price_paths = np.concatenate([np.full((trials, 1), entry), price_paths], axis=1)
    hit_tp = np.maximum.accumulate((price_paths >= tp).astype(int), axis=1)[:, -1].astype(bool)
    hit_sl = np.maximum.accumulate((price_paths <= sl).astype(int), axis=1)[:, -1].astype(bool)
    wins = np.logical_and(hit_tp, np.logical_not(hit_sl)).sum()
    exp_return = np.mean((price_paths[:, -1] - entry) / entry)
    win_prob = wins / trials
    adjusted = 0.7 * win_prob + 0.3 * max(0.0, exp_return)
    return float(np.clip(adjusted * 100.0, 5.0, 95.0))


def generate_signal(df_1h: pd.DataFrame, df_1d: pd.DataFrame, *, mc_trials: int | None = None, seed: int | None = None) -> dict[str, Any]:
    """
    Generate trading signal from 1h and 1d dataframes.
    
    Args:
        df_1h: Hourly dataframe
        df_1d: Daily dataframe
        mc_trials: Number of Monte Carlo trials (optional)
        seed: Random seed for deterministic Monte Carlo (optional, will be auto-generated if None)
    
    Returns:
        Dictionary with signal, confidence, entry_range, stop_loss_take_profit, seed, etc.
    """
    # Validate inputs
    if df_1d is None or df_1d.empty:
        raise ValueError("df_1d is required and cannot be empty")
    if df_1h is None or df_1h.empty:
        df_1h = df_1d  # Fallback to 1d data

    # Ensure required columns exist
    required_cols = ["open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df_1d.columns:
            raise ValueError(f"Missing required column '{col}' in df_1d")
        if col not in df_1h.columns:
            raise ValueError(f"Missing required column '{col}' in df_1h")
    
    # Generate deterministic seed if not provided
    if seed is None:
        # Extract date from latest candle
        if "open_time" in df_1d.columns:
            latest_date = df_1d["open_time"].iloc[-1]
            if hasattr(latest_date, "date"):
                seed_date = latest_date.date()
            elif hasattr(latest_date, "strftime"):
                seed_date = latest_date
            else:
                seed_date = str(latest_date)[:10]
        else:
            # Fallback: use current date
            from datetime import datetime

            seed_date = datetime.utcnow().date()

        # Extract symbol from dataframe if available
        symbol = "BTCUSDT"  # Default
        if "symbol" in df_1d.columns:
            symbol = str(df_1d["symbol"].iloc[-1]) if not df_1d["symbol"].empty else "BTCUSDT"

        # Deterministic seed per (date, symbol) pair
        seed = generate_deterministic_seed(seed_date, symbol)

    # Calculate indicators
    ind_1d = ind.calculate_all(df_1d)
    ind_1h = ind.calculate_all(df_1h)
    factors = cross_timeframe(df_1h, df_1d, ind_1h, ind_1d)

    aggregate_params = STRATEGY_PARAMS.get("aggregate", {})
    buy_threshold = float(aggregate_params.get("buy_threshold", 0.2))
    sell_threshold = float(aggregate_params.get("sell_threshold", -0.2))
    risk_reward_floor = float(aggregate_params.get("risk_reward_floor", 1.2))
    base_conf_multiplier = float(aggregate_params.get("base_conf_multiplier", 140.0))
    default_mc_trials = int(aggregate_params.get("mc_trials", 2000))
    mc_trials_effective = default_mc_trials if mc_trials is None else mc_trials

    vector_bias_cfg = aggregate_params.get("vector_bias", {})
    momentum_bias_weight = float(vector_bias_cfg.get("momentum_bias_weight", 0.2))
    momentum_alignment_bias = float(vector_bias_cfg.get("momentum_alignment", 0.1))
    breakout_slope_weight = float(vector_bias_cfg.get("breakout_slope_weight", 0.1))
    vol_mid_bias = float(vector_bias_cfg.get("volatility_mid_bias", 0.05))
    vol_high_bias = float(vector_bias_cfg.get("volatility_high_bias", 0.1))
    vol_low_bias = float(vector_bias_cfg.get("volatility_low_bias", -0.05))
    
    regime_cfg = aggregate_params.get("regime_classifier", {})
    use_regime_classifier = regime_cfg.get("enabled", False)
    regime_method = regime_cfg.get("method", "hmm")
    regime_exponential_factor = float(regime_cfg.get("exponential_factor", 2.0))

    mtf_cfg = aggregate_params.get("multi_timeframe", {})
    slope_scale = float(mtf_cfg.get("slope_scale", 80.0))
    intraday_scale = float(mtf_cfg.get("intraday_scale", 6.0))
    ema21_slope_weight = float(mtf_cfg.get("ema21_slope_weight", 0.2))
    intraday_momentum_weight = float(mtf_cfg.get("intraday_momentum_weight", 0.15))
    alignment_shift = float(mtf_cfg.get("alignment_shift", 0.05))

    s1 = momentum_strategy(df_1d, ind_1d)
    s2 = mean_reversion_strategy(df_1d, ind_1d)
    s3 = breakout_strategy(df_1d, ind_1d)
    s4 = volatility_strategy(df_1d, ind_1d)
    signals = [s1, s2, s3, s4]

    strat_labels = ["momentum", "mean_reversion", "breakout", "volatility"]
    
    regime_proba = None
    if use_regime_classifier:
        try:
            regime_classifier = RegimeClassifier(method=regime_method, n_regimes=3)
            regime_proba = regime_classifier.fit_predict_proba(df_1d)
            if not regime_proba.empty:
                regime_proba = regime_proba.iloc[-1]
        except Exception:
            use_regime_classifier = False
    
    signal_vectors = []
    for label, strat in zip(strat_labels, signals):
        direction = {"BUY": 1.0, "SELL": -1.0}.get(strat["signal"], 0.0)
        strength = strat.get("confidence", 0.0) / 100.0
        quality = 0.7 if "missing" in strat.get("reason", "") else 1.0
        bias = 0.0
        alignment_flag = 2 * factors.get("momentum_alignment", 0.0) - 1.0
        if alignment_flag == -1.0:
            alignment_flag = -1.0
        if label == "momentum":
            bias = momentum_bias_weight * np.tanh(factors.get("mom_1d", 0.0) * 6.0)
            bias += momentum_alignment_bias * alignment_flag
        elif label == "mean_reversion":
            bias = -momentum_alignment_bias * alignment_flag
        elif label == "breakout":
            bias = breakout_slope_weight * np.tanh(factors.get("slope_1d", 0.0) * 50.0)
            if use_regime_classifier and regime_proba is not None:
                p_stress = regime_proba.get("stress", 0.0) if isinstance(regime_proba, pd.Series) else 0.0
                p_high_vol = p_stress
                adaptive_weight = np.exp(regime_exponential_factor * p_high_vol)
                bias *= adaptive_weight
        elif label == "volatility":
            if use_regime_classifier and regime_proba is not None:
                p_calm = regime_proba.get("calm", 0.33) if isinstance(regime_proba, pd.Series) else 0.33
                p_balanced = regime_proba.get("balanced", 0.33) if isinstance(regime_proba, pd.Series) else 0.33
                p_stress = regime_proba.get("stress", 0.33) if isinstance(regime_proba, pd.Series) else 0.33
                bias = p_calm * vol_low_bias + p_balanced * vol_mid_bias + p_stress * vol_high_bias
            else:
                regime = factors.get("vol_regime_1d", 1)
                if regime == 2:
                    bias = vol_high_bias
                elif regime == 1:
                    bias = vol_mid_bias
                else:
                    bias = vol_low_bias
        signal_vectors.append(direction * (strength * quality + bias))

    multi_bias = 0.0
    slope_component = ema21_slope_weight * np.tanh(factors.get("slope_1h", 0.0) * slope_scale)
    ratio_component = 0.5 * ema21_slope_weight * np.tanh(factors.get("slope_ratio", 0.0) * slope_scale / 10.0)
    intraday_component = intraday_momentum_weight * np.tanh(factors.get("mom_1h", 0.0) * intraday_scale)
    alignment_component = alignment_shift * (1.0 if factors.get("momentum_alignment", 0.0) >= 0.5 else -1.0)
    
    if use_regime_classifier and regime_proba is not None:
        p_calm = regime_proba.get("calm", 0.33) if isinstance(regime_proba, pd.Series) else 0.33
        p_balanced = regime_proba.get("balanced", 0.33) if isinstance(regime_proba, pd.Series) else 0.33
        p_stress = regime_proba.get("stress", 0.33) if isinstance(regime_proba, pd.Series) else 0.33
        vol_component = p_calm * vol_low_bias * 0.5 + p_balanced * vol_mid_bias * 0.5 + p_stress * vol_high_bias * 0.5
    else:
        vol_regime = factors.get("vol_regime_1h", 1)
        vol_component = 0.0
        if vol_regime == 2:
            vol_component = vol_high_bias * 0.5
        elif vol_regime == 1:
            vol_component = vol_mid_bias * 0.5
        else:
            vol_component = vol_low_bias * 0.5
    
    multi_bias = slope_component + ratio_component + intraday_component + alignment_component + vol_component
    signal_vectors.append(multi_bias)
    strat_labels.append("multi_timeframe")

    aggregate_score = float(np.sum(signal_vectors))
    raw_aggregate_score = float(aggregate_score)
    if aggregate_score > buy_threshold:
        final_signal = "BUY"
    elif aggregate_score < sell_threshold:
        final_signal = "SELL"
    else:
        final_signal = "HOLD"

    base_conf = min(95.0, abs(aggregate_score) * base_conf_multiplier)
    agreement = np.clip(np.mean([abs(s) for s in signal_vectors]) * 100.0, 0.0, 100.0)

    votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for strat in signals:
        votes[strat["signal"]] += 1

    price = float(df_1d["close"].iloc[-1])
    entry = _entry_range(df_1d, final_signal, price)
    levels = _sl_tp(df_1d, final_signal, entry["optimal"])

    support_raw = df_1d["support"].iloc[-1] if "support" in df_1d else np.nan
    resistance_raw = df_1d["resistance"].iloc[-1] if "resistance" in df_1d else np.nan
    support = float(support_raw) if not pd.isna(support_raw) else entry["min"]
    resistance = float(resistance_raw) if not pd.isna(resistance_raw) else entry["max"]

    if final_signal == "BUY":
        levels["stop_loss"] = max(levels["stop_loss"], support * 0.99)
        min_tp = max(entry["optimal"] + abs(entry["optimal"] - levels["stop_loss"]) * 1.2, resistance * 0.99)
        if levels["take_profit"] <= min_tp:
            levels["take_profit"] = min_tp
    elif final_signal == "SELL":
        levels["stop_loss"] = min(levels["stop_loss"], resistance * 1.01)
        max_tp = min(entry["optimal"] - abs(levels["stop_loss"] - entry["optimal"]) * 1.2, support * 1.01)
        if levels["take_profit"] >= max_tp:
            levels["take_profit"] = max_tp

    risk = 0.0
    reward = 0.0
    if final_signal == "BUY":
        risk = entry["optimal"] - levels["stop_loss"]
        reward = levels["take_profit"] - entry["optimal"]
    elif final_signal == "SELL":
        risk = levels["stop_loss"] - entry["optimal"]
        reward = entry["optimal"] - levels["take_profit"]

    rr_ratio = abs(reward / risk) if risk else 0.0
    rr_rejected = False
    if final_signal in {"BUY", "SELL"}:
        if risk <= 0 or reward <= 0:
            rr_rejected = True
        elif rr_ratio < risk_reward_floor:
            rr_rejected = True

    if rr_rejected:
        final_signal = "HOLD"
        aggregate_score = float(np.clip(aggregate_score, -0.05, 0.05))
        entry = _entry_range(df_1d, final_signal, price)
        levels = _sl_tp(df_1d, final_signal, entry["optimal"])
        risk = 0.0
        reward = 0.0

    if final_signal in {"BUY", "SELL"} and mc_trials_effective > 0:
        mc_conf = _mc_confidence(df_1d, entry["optimal"], levels["stop_loss"], levels["take_profit"], trials=mc_trials_effective, seed=seed)
    else:
        mc_conf = base_conf

    # Calculate risk metrics
    sl_prob = max(0.0, 100.0 - mc_conf)
    tp_prob = np.clip(mc_conf, 0.0, 100.0)

    expected_dd = abs(entry["optimal"] - levels["stop_loss"])
    # Use curated volatility if available, otherwise calculate
    if "volatility_30" in df_1d.columns and not df_1d["volatility_30"].empty:
        vol = float(df_1d["volatility_30"].iloc[-1])
    elif "realized_volatility" in df_1d.columns and not df_1d["realized_volatility"].empty:
        vol = float(df_1d["realized_volatility"].iloc[-1])
    else:
        vol_series = ind.realized_volatility(df_1d)
        vol = float(vol_series.iloc[-1]) if not vol_series.empty else 0.0

    risk_metrics = {
        "risk_reward_ratio": round(rr_ratio, 2),
        "sl_probability": round(sl_prob, 1),
        "tp_probability": round(tp_prob, 1),
        "expected_drawdown": round(expected_dd, 2),
        "volatility": round(vol, 2),
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "risk_reward_floor": risk_reward_floor,
    }
    if rr_rejected:
        risk_metrics["risk_reward_ratio"] = round(rr_ratio, 2)
        risk_metrics["rejected_reason"] = "risk_reward_floor"
        risk_metrics["risk"] = 0.0
        risk_metrics["reward"] = 0.0

    if final_signal in {"BUY", "SELL"}:
        rr_boost = np.clip(risk_metrics["risk_reward_ratio"] / 3.0, 0.7, 1.3) if risk_metrics["risk_reward_ratio"] else 0.7
        final_conf = float(np.clip((0.5 * base_conf + 0.5 * mc_conf) * rr_boost, 5.0, 97.0))
    else:
        final_conf = float(np.clip(max(base_conf * 0.6, 5.0), 5.0, 60.0))

    # Prepare indicators dict (extract last values from Series, handling NaN)
    import math
    indicators_dict = {}
    for k, v in ind_1d.items():
        if isinstance(v, pd.Series) and not v.empty:
            try:
                val = float(v.iloc[-1])
                # Skip NaN and Inf values
                if not (math.isnan(val) or math.isinf(val)):
                    indicators_dict[k] = val
            except (ValueError, IndexError, TypeError):
                pass
        elif isinstance(v, (int, float)):
            val = float(v)
            if not (math.isnan(val) or math.isinf(val)):
                indicators_dict[k] = val

    # Add volume to indicators for narrative
    if "volume" in df_1d.columns and not df_1d["volume"].empty:
        try:
            vol_val = float(df_1d["volume"].iloc[-1])
            if not (math.isnan(vol_val) or math.isinf(vol_val)):
                indicators_dict["volume"] = vol_val
        except (ValueError, IndexError, TypeError):
            pass

    # Alias curated-friendly keys for narrative/analytics
    if "rsi" in indicators_dict and "rsi_14" not in indicators_dict:
        indicators_dict["rsi_14"] = indicators_dict["rsi"]
    if "atr" in indicators_dict and "atr_14" not in indicators_dict:
        indicators_dict["atr_14"] = indicators_dict["atr"]
    if "realized_vol" in indicators_dict and "volatility_30" not in indicators_dict:
        indicators_dict["volatility_30"] = indicators_dict["realized_vol"]

    payload = {
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
        "seed": seed,  # Include seed for reproducibility
        "signal_breakdown": {
            "vectors": {label: float(val) for label, val in zip(strat_labels, signal_vectors)},
            "narrative": [
                f"{label.replace('_', ' ').title()} {float(val):+.2f}"
                for label, val in zip(strat_labels, signal_vectors)
            ],
            "aggregate_score": aggregate_score,
            "raw_aggregate_score": raw_aggregate_score,
            "base_confidence": base_conf,
            "agreement": agreement,
            "risk_adjusted_confidence": final_conf,
        },
    }

    return payload


class DailySignalEngine:
    """
    Unified signal engine that consolidates strategies, filters, and guardrails.
    
    This is the single entry point for generating BUY/SELL/HOLD signals.
    It combines multiple strategies, applies risk filters, and enforces guardrails
    to produce deterministic, reproducible trading signals.
    
    Usage:
        engine = DailySignalEngine()
        signal = engine.generate(df_1h, df_1d)
    """
    
    def __init__(self, mc_trials: int | None = None):
        """
        Initialize the daily signal engine.
        
        Args:
            mc_trials: Number of Monte Carlo trials for confidence calculation.
                      If None, uses default from strategy parameters.
        """
        self.mc_trials = mc_trials
    
    def generate(self, df_1h: pd.DataFrame, df_1d: pd.DataFrame, seed: int | None = None) -> dict[str, Any]:
        """
        Generate a trading signal from 1h and 1d dataframes.
        
        This is the single entry point that produces BUY/SELL/HOLD signals.
        It consolidates all strategies, applies filters, and enforces guardrails.
        
        Args:
            df_1h: Hourly dataframe with OHLCV data
            df_1d: Daily dataframe with OHLCV data
            seed: Optional deterministic seed for reproducibility.
                  If None, a seed will be auto-generated based on date and symbol.
        
        Returns:
            Dictionary containing:
            - signal: "BUY", "SELL", or "HOLD"
            - confidence: Confidence score (0-100)
            - entry_range: Min/max/optimal entry prices
            - stop_loss_take_profit: SL/TP levels and percentages
            - risk_metrics: Risk/reward ratio, probabilities, etc.
            - indicators: Technical indicators
            - factors: Cross-timeframe factors
            - signal_breakdown: Detailed breakdown of signal components
            - seed: Seed used for deterministic calculations
            - And other metadata
        
        Raises:
            ValueError: If required data is missing or invalid
        """
        return generate_signal(df_1h, df_1d, mc_trials=self.mc_trials, seed=seed)


