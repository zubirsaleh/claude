"""OANDA market-data microservice (FastAPI).

Exposes clean, JSON endpoints for candles, the latest price, indicators and
candlestick patterns for XAU/USD. This service is the only component that
talks to OANDA. It performs no order execution.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from shared import config
from shared.logging_config import setup_logging

from oanda_client import OandaError, get_candles, get_price
from indicators import compute_indicators
from patterns import detect_patterns

log = setup_logging("oanda-service")
app = FastAPI(title="OANDA Market Data Service", version="1.0.0")


def _validate_timeframe(tf: str) -> str:
    tf = tf.upper()
    if tf not in config.SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported timeframe. Use M1, M5, M15, M30, H1, H4, or D.",
        )
    return tf


@app.get("/health")
def health() -> dict:
    return {
        "service": "oanda-service",
        "status": "ok",
        "instrument": config.OANDA_INSTRUMENT,
        "environment": "live" if config.using_live() else "practice",
    }


@app.get("/price")
def price() -> dict:
    try:
        return get_price(config.OANDA_INSTRUMENT)
    except OandaError as exc:
        log.error("price error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/candles")
def candles(
    granularity: str = Query(default=config.DEFAULT_TIMEFRAME),
    count: int = Query(default=config.DEFAULT_CANDLE_COUNT, ge=30, le=5000),
) -> dict:
    tf = _validate_timeframe(granularity)
    try:
        df = get_candles(config.OANDA_INSTRUMENT, tf, count, "M")
    except OandaError as exc:
        log.error("candles error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    df = df.copy()
    df["time"] = df["time"].astype(str)
    return {"instrument": config.OANDA_INSTRUMENT, "granularity": tf, "candles": df.to_dict("records")}


@app.get("/marketdata")
def marketdata(
    granularity: str = Query(default=config.DEFAULT_TIMEFRAME),
    count: int = Query(default=config.DEFAULT_CANDLE_COUNT, ge=30, le=5000),
) -> dict:
    """Bundle everything the analysis service needs in a single call:

    indicators + patterns + the latest price, all computed from *completed*
    candles only.
    """
    tf = _validate_timeframe(granularity)
    log.info("marketdata request | tf=%s count=%s", tf, count)
    try:
        df = get_candles(config.OANDA_INSTRUMENT, tf, count, "M")
    except OandaError as exc:
        log.error("marketdata error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    completed = df[df["complete"]].reset_index(drop=True)
    if len(completed) < 30:
        raise HTTPException(
            status_code=502,
            detail="Not enough completed candles returned by OANDA for analysis.",
        )

    try:
        indicators = compute_indicators(completed)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    patterns = detect_patterns(completed)

    # Best-effort live price; fall back to the last completed close.
    try:
        quote = get_price(config.OANDA_INSTRUMENT)
        current_price = quote.get("mid") or float(completed["close"].iloc[-1])
    except OandaError as exc:
        log.warning("price unavailable, using last close: %s", exc)
        quote = {"instrument": config.OANDA_INSTRUMENT, "bid": None, "ask": None}
        current_price = float(completed["close"].iloc[-1])

    return {
        "instrument": config.OANDA_INSTRUMENT,
        "granularity": tf,
        "current_price": current_price,
        "quote": quote,
        "indicators": indicators,
        "patterns": patterns,
        "candles_used": len(completed),
    }
