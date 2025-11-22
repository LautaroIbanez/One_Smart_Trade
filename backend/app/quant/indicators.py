"""Indicator calculations using pandas over parquet-backed dataframes."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# Filter FutureWarnings about deprecated fillna(method=...) to reduce noise
warnings.filterwarnings("ignore", message=".*fillna with 'method' is deprecated.*", category=FutureWarning)


def ema(df: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
    return df[column].ewm(span=period, adjust=False).mean()


def sma(df: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
    return df[column].rolling(window=period, min_periods=period).mean()


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
    fast_ = ema(df, fast)
    slow_ = ema(df, slow)
    macd_line = fast_ - slow_
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    delta = df[column].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.bfill().fillna(50)


def stoch_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
    r = rsi(df, rsi_period)
    r_min = r.rolling(stoch_period).min()
    r_max = r.rolling(stoch_period).max()
    return ((r - r_min) / (r_max - r_min)).clip(0, 1) * 100


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0, column: str = "close") -> dict[str, pd.Series]:
    mid = sma(df, period, column)
    std = df[column].rolling(period).std()
    return {"upper": mid + std_dev * std, "middle": mid, "lower": mid - std_dev * std}


def keltner(df: pd.DataFrame, period: int = 20, mult: float = 2.0) -> dict[str, pd.Series]:
    mid = ema(df, period)
    a = atr(df, period)
    return {"upper": mid + mult * a, "middle": mid, "lower": mid - mult * a}


def vwap(df: pd.DataFrame) -> pd.Series:
    # Use curated vwap if available, otherwise calculate
    if "vwap" in df.columns and not df["vwap"].empty:
        return df["vwap"]
    pv = (df["close"] * df["volume"]).cumsum()
    vv = df["volume"].cumsum().replace(0, np.nan)
    return (pv / vv).ffill()


def realized_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    returns = df["close"].pct_change()
    return (returns.rolling(window).std() * np.sqrt(252)).fillna(0)


def calculate_all(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Calculate all indicators, using curated columns if available."""
    out: dict[str, pd.Series] = {}

    # Use curated ema_21 if available, otherwise calculate
    if "ema_21" in df.columns:
        out["ema_21"] = df["ema_21"]
    else:
        out["ema_21"] = ema(df, 21)

    out["ema_9"] = ema(df, 9)
    out["ema_50"] = ema(df, 50)

    # Use curated sma if available
    if "sma_20" in df.columns:
        out["sma_20"] = df["sma_20"]
    if "sma_50" in df.columns:
        out["sma_50"] = df["sma_50"]
    else:
        out["sma_50"] = sma(df, 50)

    out["sma_100"] = sma(df, 100)
    out["sma_200"] = sma(df, 200)

    m = macd(df)
    out["macd"] = m["macd"]
    out["macd_signal"] = m["signal"]
    out["macd_histogram"] = m["histogram"]

    # Use curated rsi_14 if available, otherwise calculate
    if "rsi_14" in df.columns:
        out["rsi"] = df["rsi_14"]
    else:
        out["rsi"] = rsi(df)

    out["stoch_rsi"] = stoch_rsi(df)

    # Use curated bollinger if available
    if "bollinger_upper" in df.columns and "bollinger_lower" in df.columns:
        out["bb_upper"] = df["bollinger_upper"]
        out["bb_middle"] = df["bollinger_mid"]
        out["bb_lower"] = df["bollinger_lower"]
    else:
        bb = bollinger(df)
        out["bb_upper"] = bb["upper"]
        out["bb_middle"] = bb["middle"]
        out["bb_lower"] = bb["lower"]

    kc = keltner(df)
    out["kc_upper"] = kc["upper"]
    out["kc_middle"] = kc["middle"]
    out["kc_lower"] = kc["lower"]

    # Use curated atr_14 if available
    if "atr_14" in df.columns:
        out["atr"] = df["atr_14"]
    else:
        out["atr"] = atr(df)

    out["vwap"] = vwap(df)

    # Use curated volatility_30 if available
    if "volatility_30" in df.columns:
        out["realized_vol"] = df["volatility_30"]
    else:
        out["realized_vol"] = realized_volatility(df)

    return out


