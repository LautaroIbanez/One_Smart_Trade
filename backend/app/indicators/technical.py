"""Technical indicators calculation."""
from typing import Any

import pandas as pd


class TechnicalIndicators:
    """Calculate technical indicators."""

    @staticmethod
    def ema(df: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
        """Calculate Exponential Moving Average."""
        return df[column].ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(df: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
        """Calculate Simple Moving Average."""
        return df[column].rolling(window=period).mean()

    @staticmethod
    def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
        """Calculate MACD."""
        ema_fast = TechnicalIndicators.ema(df, fast)
        ema_slow = TechnicalIndicators.ema(df, slow)
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return {"macd": macd_line, "signal": signal_line, "histogram": histogram}

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = df[column].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def stoch_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
        """Calculate Stochastic RSI."""
        rsi = TechnicalIndicators.rsi(df, rsi_period)
        rsi_min = rsi.rolling(window=stoch_period).min()
        rsi_max = rsi.rolling(window=stoch_period).max()
        return (rsi - rsi_min) / (rsi_max - rsi_min) * 100

    @staticmethod
    def bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: int = 2, column: str = "close") -> dict[str, pd.Series]:
        """Calculate Bollinger Bands."""
        sma = TechnicalIndicators.sma(df, period, column)
        std = df[column].rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return {"upper": upper, "middle": sma, "lower": lower}

    @staticmethod
    def keltner_channels(df: pd.DataFrame, period: int = 20, atr_multiplier: float = 2.0) -> dict[str, pd.Series]:
        """Calculate Keltner Channels."""
        ema = TechnicalIndicators.ema(df, period)
        atr = TechnicalIndicators.atr(df, period)
        upper = ema + (atr * atr_multiplier)
        lower = ema - (atr * atr_multiplier)
        return {"upper": upper, "middle": ema, "lower": lower}

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index."""
        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr = TechnicalIndicators.atr(df, period)
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        return adx

    @staticmethod
    def momentum(df: pd.DataFrame, period: int = 10, column: str = "close") -> pd.Series:
        """Calculate Momentum."""
        return df[column].diff(period)

    @staticmethod
    def calculate_all(df: pd.DataFrame) -> dict[str, Any]:
        """Calculate all indicators and return as dictionary."""
        indicators = {}
        indicators["ema_9"] = TechnicalIndicators.ema(df, 9)
        indicators["ema_21"] = TechnicalIndicators.ema(df, 21)
        indicators["ema_50"] = TechnicalIndicators.ema(df, 50)
        indicators["sma_100"] = TechnicalIndicators.sma(df, 100)
        indicators["sma_200"] = TechnicalIndicators.sma(df, 200)
        macd_data = TechnicalIndicators.macd(df)
        indicators["macd"] = macd_data["macd"]
        indicators["macd_signal"] = macd_data["signal"]
        indicators["macd_histogram"] = macd_data["histogram"]
        indicators["rsi"] = TechnicalIndicators.rsi(df)
        indicators["stoch_rsi"] = TechnicalIndicators.stoch_rsi(df)
        bb = TechnicalIndicators.bollinger_bands(df)
        indicators["bb_upper"] = bb["upper"]
        indicators["bb_middle"] = bb["middle"]
        indicators["bb_lower"] = bb["lower"]
        kc = TechnicalIndicators.keltner_channels(df)
        indicators["kc_upper"] = kc["upper"]
        indicators["kc_middle"] = kc["middle"]
        indicators["kc_lower"] = kc["lower"]
        indicators["atr"] = TechnicalIndicators.atr(df)
        indicators["adx"] = TechnicalIndicators.adx(df)
        indicators["momentum"] = TechnicalIndicators.momentum(df)
        return indicators

    @staticmethod
    def get_latest_values(indicators: dict[str, pd.Series]) -> dict[str, float]:
        """Get latest values from indicator series."""
        return {key: float(series.iloc[-1]) if not series.empty and not pd.isna(series.iloc[-1]) else 0.0 for key, series in indicators.items()}

