"""Thin OANDA v20 REST client for XAU/USD market data.

Only read-only market-data endpoints are used. No order execution lives here.
All failures are surfaced as ``OandaError`` with a clear message — we never
fabricate prices or candles when the API is unavailable.
"""
from __future__ import annotations

import logging

import pandas as pd
import requests

from shared import config

log = logging.getLogger("oanda-service.client")

_TIMEOUT = 15


class OandaError(RuntimeError):
    """Raised when OANDA data cannot be retrieved."""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.OANDA_API_KEY}",
        "Content-Type": "application/json",
    }


def _request(path: str, params: dict | None = None) -> dict:
    config.validate_oanda()
    url = f"{config.oanda_base_url()}{path}"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        log.error("OANDA request failed: %s", exc)
        raise OandaError(
            "OANDA data unavailable. Please check API key, account ID, or network."
        ) from exc

    if resp.status_code == 401:
        raise OandaError(
            "OANDA rejected the API key (401). Check OANDA_API_KEY and OANDA_ENV."
        )
    if resp.status_code >= 400:
        log.error("OANDA HTTP %s: %s", resp.status_code, resp.text[:500])
        raise OandaError(
            "OANDA data unavailable. Please check API key, account ID, or network."
        )
    return resp.json()


def get_candles(
    instrument: str = "XAU_USD",
    granularity: str = "M15",
    count: int = 150,
    price: str = "M",
) -> pd.DataFrame:
    """Fetch candles from OANDA and return a clean OHLCV DataFrame.

    Columns: time, open, high, low, close, volume, complete.
    Only mid prices (price="M") are parsed. Incomplete (forming) candles are
    kept in the frame but flagged via the ``complete`` column so callers can
    drop them before computing indicators.
    """
    params = {"granularity": granularity, "count": count, "price": price}
    data = _request(f"/v3/instruments/{instrument}/candles", params)

    candles = data.get("candles", [])
    if not candles:
        raise OandaError(
            "OANDA returned no candles. The instrument or timeframe may be invalid."
        )

    rows = []
    for c in candles:
        mid = c.get("mid", {})
        rows.append(
            {
                "time": c.get("time"),
                "open": float(mid.get("o")),
                "high": float(mid.get("h")),
                "low": float(mid.get("l")),
                "close": float(mid.get("c")),
                "volume": float(c.get("volume", 0)),
                "complete": bool(c.get("complete", False)),
            }
        )

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    return df


def get_price(instrument: str = "XAU_USD") -> dict:
    """Fetch the latest streaming-style bid/ask snapshot for the instrument.

    Uses the account pricing endpoint. Returns bid, ask and computed mid.
    """
    config.validate_oanda()
    path = f"/v3/accounts/{config.OANDA_ACCOUNT_ID}/pricing"
    data = _request(path, params={"instruments": instrument})

    prices = data.get("prices", [])
    if not prices:
        raise OandaError("OANDA returned no pricing data for the instrument.")

    p = prices[0]
    bids = p.get("bids") or []
    asks = p.get("asks") or []
    bid = float(bids[0]["price"]) if bids else None
    ask = float(asks[0]["price"]) if asks else None
    mid = round((bid + ask) / 2, 3) if bid is not None and ask is not None else None
    return {
        "instrument": instrument,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "time": p.get("time"),
    }
