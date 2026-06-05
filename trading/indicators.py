"""Technical indicator computation using pandas-ta."""
from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def get_indicators(df: pd.DataFrame) -> dict:
    """
    Compute RSI, MACD, Bollinger Bands, EMAs, ATR, and Stochastic
    from an OHLCV DataFrame. Returns a flat dict of named values.
    """
    if df.empty or "close" not in df.columns:
        return {}

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    vol   = df["volume"].astype(float) if "volume" in df.columns else pd.Series(dtype=float)

    out: dict = {}

    # RSI
    rsi = ta.rsi(close, length=14)
    if rsi is not None and not rsi.empty:
        out["rsi_14"] = round(float(rsi.iloc[-1]), 2)

    # MACD
    macd_df = ta.macd(close)
    if macd_df is not None and not macd_df.empty:
        cols = macd_df.columns.tolist()
        out["macd"]        = round(float(macd_df[cols[0]].iloc[-1]), 6)
        out["macd_signal"] = round(float(macd_df[cols[1]].iloc[-1]), 6)
        out["macd_hist"]   = round(float(macd_df[cols[2]].iloc[-1]), 6)

    # Bollinger Bands (20, 2)
    bb = ta.bbands(close, length=20)
    if bb is not None and not bb.empty:
        cols = bb.columns.tolist()
        out["bb_lower"]  = round(float(bb[cols[0]].iloc[-1]), 6)
        out["bb_middle"] = round(float(bb[cols[1]].iloc[-1]), 6)
        out["bb_upper"]  = round(float(bb[cols[2]].iloc[-1]), 6)
        out["bb_width"]  = round(float(bb[cols[3]].iloc[-1]), 6)

    # EMAs
    for period in (9, 21, 50, 200):
        ema = ta.ema(close, length=period)
        if ema is not None and not ema.empty:
            out[f"ema_{period}"] = round(float(ema.iloc[-1]), 6)

    # ATR
    atr = ta.atr(high, low, close, length=14)
    if atr is not None and not atr.empty:
        out["atr_14"] = round(float(atr.iloc[-1]), 6)

    # Stochastic
    stoch = ta.stoch(high, low, close)
    if stoch is not None and not stoch.empty:
        cols = stoch.columns.tolist()
        out["stoch_k"] = round(float(stoch[cols[0]].iloc[-1]), 2)
        out["stoch_d"] = round(float(stoch[cols[1]].iloc[-1]), 2)

    # Volume SMA
    if not vol.empty:
        vsma = ta.sma(vol, length=20)
        if vsma is not None and not vsma.empty:
            out["volume_sma_20"] = round(float(vsma.iloc[-1]), 2)
            out["volume_current"] = round(float(vol.iloc[-1]), 2)

    # Current OHLC
    out["open"]  = round(float(df["open"].iloc[-1]), 6)
    out["high"]  = round(float(df["high"].iloc[-1]), 6)
    out["low"]   = round(float(df["low"].iloc[-1]), 6)
    out["close"] = round(float(df["close"].iloc[-1]), 6)

    return out
