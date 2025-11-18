"""Recommendation engine that generates trading signals."""
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from app.core.logging import logger
from app.data.curation import DataCuration
from app.indicators.technical import TechnicalIndicators
from app.strategies.strategy_ensemble import StrategyEnsemble
from app.strategies.weight_store import MetaWeightStore


class RecommendationEngine:
    """Engine for generating trading recommendations."""

    def __init__(self):
        self.curation = DataCuration()
        self.indicators_calc = TechnicalIndicators()
        weight_store = MetaWeightStore()
        self.ensemble = StrategyEnsemble(weight_store=weight_store)

    def _calculate_entry_range(self, df: pd.DataFrame, signal: str, current_price: float) -> dict[str, float]:
        """Calculate entry price range."""
        recent_data = df.tail(50)
        support = recent_data["low"].min()
        resistance = recent_data["high"].max()
        vwap = df.get("vwap", pd.Series([current_price])).iloc[-1] if "vwap" in df.columns else current_price

        if signal == "BUY":
            min_entry = max(support, current_price * 0.995)
            max_entry = min(current_price * 1.01, vwap * 1.005)
            optimal = (min_entry + max_entry) / 2
        elif signal == "SELL":
            min_entry = max(current_price * 0.99, vwap * 0.995)
            max_entry = min(resistance, current_price * 1.005)
            optimal = (min_entry + max_entry) / 2
        else:
            min_entry = current_price * 0.998
            max_entry = current_price * 1.002
            optimal = current_price

        return {"min": round(min_entry, 2), "max": round(max_entry, 2), "optimal": round(optimal, 2)}

    def _calculate_sl_tp(self, df: pd.DataFrame, signal: str, entry_price: float) -> dict[str, float]:
        """Calculate stop loss and take profit levels."""
        atr = df.get("atr", pd.Series([entry_price * 0.02])).iloc[-1] if "atr" in df.columns else entry_price * 0.02
        volatility = df.get("realized_volatility", pd.Series([0.3])).iloc[-1] if "realized_volatility" in df.columns else 0.3

        atr_multiplier = 2.0
        if volatility > 0.5:
            atr_multiplier = 2.5
        elif volatility < 0.2:
            atr_multiplier = 1.5

        if signal == "BUY":
            stop_loss = entry_price - (atr * atr_multiplier)
            take_profit = entry_price + (atr * atr_multiplier * 2.5)
            stop_loss_pct = ((stop_loss - entry_price) / entry_price) * 100
            take_profit_pct = ((take_profit - entry_price) / entry_price) * 100
        elif signal == "SELL":
            stop_loss = entry_price + (atr * atr_multiplier)
            take_profit = entry_price - (atr * atr_multiplier * 2.5)
            stop_loss_pct = ((stop_loss - entry_price) / entry_price) * 100
            take_profit_pct = ((take_profit - entry_price) / entry_price) * 100
        else:
            stop_loss = entry_price * 0.98
            take_profit = entry_price * 1.02
            stop_loss_pct = -2.0
            take_profit_pct = 2.0

        return {
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "stop_loss_pct": round(stop_loss_pct, 2),
            "take_profit_pct": round(take_profit_pct, 2),
        }

    def _calculate_risk_metrics(self, df: pd.DataFrame, signal: str, entry: float, sl: float, tp: float) -> dict[str, Any]:
        """Calculate risk metrics."""
        atr = df.get("atr", pd.Series([entry * 0.02])).iloc[-1] if "atr" in df.columns else entry * 0.02
        volatility = df.get("realized_volatility", pd.Series([0.3])).iloc[-1] if "realized_volatility" in df.columns else 0.3

        sl_distance = abs(entry - sl)
        tp_distance = abs(tp - entry)
        risk_reward = tp_distance / sl_distance if sl_distance > 0 else 0

        sl_probability = 0.3
        tp_probability = 0.5
        if volatility > 0.5:
            sl_probability = 0.4
            tp_probability = 0.4
        elif volatility < 0.2:
            sl_probability = 0.2
            tp_probability = 0.6

        expected_drawdown = sl_distance * sl_probability

        return {
            "risk_reward_ratio": round(risk_reward, 2),
            "sl_probability": round(sl_probability * 100, 1),
            "tp_probability": round(tp_probability * 100, 1),
            "expected_drawdown": round(expected_drawdown, 2),
            "volatility": round(volatility * 100, 2),
        }

    def _generate_analysis(self, signal_data: dict[str, Any], indicators: dict[str, float], risk_metrics: dict[str, Any]) -> str:
        """Generate textual analysis."""
        signal = signal_data["signal"]
        confidence = signal_data["confidence"]
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        volatility = risk_metrics.get("volatility", 30)

        analysis_parts = []

        if signal == "BUY":
            analysis_parts.append("Señal de compra generada basada en análisis multi-timeframe.")
        elif signal == "SELL":
            analysis_parts.append("Señal de venta generada basada en análisis multi-timeframe.")
        else:
            analysis_parts.append("Señal neutral - se recomienda esperar mejores condiciones de entrada.")

        confidence_raw = signal_data.get("confidence_raw", confidence)
        confidence_calibrated = signal_data.get("confidence_calibrated", confidence_raw)
        band = signal_data.get("confidence_band")
        analysis_parts.append(f"Confianza heurística: {confidence_raw:.1f}%.")
        if confidence_calibrated is not None:
            if band:
                analysis_parts.append(
                    f"Confianza calibrada (histórica): {confidence_calibrated:.1f}% "
                    f"(intervalo observado {band.get('lower', confidence_calibrated):.1f}%–{band.get('upper', confidence_calibrated):.1f}%)."
                )
            else:
                analysis_parts.append(f"Confianza calibrada (histórica): {confidence_calibrated:.1f}%.")

        if rsi < 30:
            analysis_parts.append("RSI indica condiciones de sobreventa, potencial rebote alcista.")
        elif rsi > 70:
            analysis_parts.append("RSI indica condiciones de sobrecompra, posible corrección.")

        if macd > 0:
            analysis_parts.append("MACD positivo sugiere momentum alcista.")
        else:
            analysis_parts.append("MACD negativo sugiere momentum bajista.")

        if volatility > 50:
            analysis_parts.append("Alta volatilidad detectada - mayor riesgo y potencial recompensa.")
        elif volatility < 20:
            analysis_parts.append("Baja volatilidad - mercado en consolidación.")

        analysis_parts.append(f"Ratio riesgo/recompensa: {risk_metrics.get('risk_reward_ratio', 0):.2f}.")
        if band:
            analysis_parts.append("Intervalo basado en calibración histórica; no garantiza resultados futuros.")
        analysis_parts.append("Recuerde: Este análisis es solo para fines educativos. Trading conlleva riesgos significativos.")

        return " ".join(analysis_parts)

    async def generate_recommendation(self) -> Optional[dict[str, Any]]:
        """Generate today's trading recommendation."""
        try:
            df_1d = self.curation.get_latest_curated("1d")
            if df_1d is None or df_1d.empty:
                logger.warning("No daily data available")
                return None

            df_1h = self.curation.get_latest_curated("1h")
            if df_1h is None or df_1h.empty:
                df_1h = df_1d

            df = df_1d.copy()
            if len(df) < 200:
                logger.warning("Insufficient data for recommendation")
                return None

            indicators_dict = self.indicators_calc.calculate_all(df)
            signal_data = self.ensemble.consolidate_signals(df, indicators_dict)

            latest = df.iloc[-1]
            current_price = float(latest["close"])

            entry_range = self._calculate_entry_range(df, signal_data["signal"], current_price)
            sl_tp = self._calculate_sl_tp(df, signal_data["signal"], entry_range["optimal"])
            risk_metrics = self._calculate_risk_metrics(df, signal_data["signal"], entry_range["optimal"], sl_tp["stop_loss"], sl_tp["take_profit"])

            indicators_latest = self.indicators_calc.get_latest_values(indicators_dict)
            analysis = self._generate_analysis(signal_data, indicators_latest, risk_metrics)

            recommendation = {
                "signal": signal_data["signal"],
                "entry_range": entry_range,
                "stop_loss_take_profit": sl_tp,
                "confidence": round(signal_data["confidence"], 1),
                "current_price": round(current_price, 2),
                "analysis": analysis,
                "indicators": {
                    "rsi": round(indicators_latest.get("rsi", 0), 2),
                    "macd": round(indicators_latest.get("macd", 0), 4),
                    "atr": round(indicators_latest.get("atr", 0), 2),
                    "adx": round(indicators_latest.get("adx", 0), 2),
                    "momentum": round(indicators_latest.get("momentum", 0), 2),
                },
                "risk_metrics": risk_metrics,
                "timestamp": datetime.utcnow().isoformat(),
                "disclaimer": "This is not financial advice. Trading cryptocurrencies involves significant risk. Use at your own risk.",
            }

            return recommendation
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}")
            return None

