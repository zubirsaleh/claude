"""High-level analysis combining OHLCV, indicators, patterns, and TradingView TA rating."""
from __future__ import annotations

import logging
from config import TV_USERNAME, TV_PASSWORD
from trading.fetcher import get_ohlcv
from trading.indicators import get_indicators
from trading.patterns import detect_patterns

logger = logging.getLogger(__name__)


def _tv_rating(symbol: str, exchange: str, interval: str) -> dict:
    """Get TradingView's own BUY/SELL/NEUTRAL recommendation via tradingview-ta."""
    try:
        from tradingview_ta import TA_Handler, Interval as TVInterval  # type: ignore

        _iv_map = {
            "1m": TVInterval.INTERVAL_1_MINUTE,
            "5m": TVInterval.INTERVAL_5_MINUTES,
            "15m": TVInterval.INTERVAL_15_MINUTES,
            "30m": TVInterval.INTERVAL_30_MINUTES,
            "1h": TVInterval.INTERVAL_1_HOUR,
            "2h": TVInterval.INTERVAL_2_HOURS,
            "4h": TVInterval.INTERVAL_4_HOURS,
            "1d": TVInterval.INTERVAL_1_DAY,
            "1w": TVInterval.INTERVAL_1_WEEK,
            "1M": TVInterval.INTERVAL_1_MONTH,
        }
        # Determine screener from exchange
        exchange_upper = exchange.upper()
        screener = "crypto"
        if exchange_upper in ("NYSE", "NASDAQ", "AMEX", "NYSE ARCA"):
            screener = "america"
        elif exchange_upper in ("LSE", "LON"):
            screener = "uk"
        elif exchange_upper in ("EUREX", "XETRA"):
            screener = "germany"
        elif exchange_upper in ("TSX", "TSXV"):
            screener = "canada"
        elif exchange_upper in ("ASX",):
            screener = "australia"
        elif exchange_upper in ("FX", "FX_IDC", "FOREXCOM"):
            screener = "forex"

        handler = TA_Handler(
            symbol=symbol.upper(),
            screener=screener,
            exchange=exchange_upper,
            interval=_iv_map.get(interval.lower(), TVInterval.INTERVAL_1_HOUR),
        )
        analysis = handler.get_analysis()
        return {
            "recommendation": analysis.summary.get("RECOMMENDATION", "NEUTRAL"),
            "buy_signals": analysis.summary.get("BUY", 0),
            "sell_signals": analysis.summary.get("SELL", 0),
            "neutral_signals": analysis.summary.get("NEUTRAL", 0),
        }
    except Exception as exc:
        logger.debug("TradingView TA rating failed: %s", exc)
        return {}


def full_analysis(
    symbol: str,
    exchange: str = "BINANCE",
    interval: str = "1h",
    bars: int = 150,
) -> dict:
    """
    Return a complete market analysis dict with:
      - latest OHLCV snapshot
      - recent candles (last 10)
      - technical indicators
      - detected candlestick patterns
      - TradingView overall recommendation
    """
    df = get_ohlcv(symbol, exchange, interval, bars, TV_USERNAME, TV_PASSWORD)

    last_candles = []
    for _, row in df.tail(10).iterrows():
        last_candles.append({
            "time":   str(row.get("datetime", row.name)),
            "open":   round(float(row["open"]), 6),
            "high":   round(float(row["high"]), 6),
            "low":    round(float(row["low"]), 6),
            "close":  round(float(row["close"]), 6),
            "volume": round(float(row.get("volume", 0)), 2),
        })

    indicators = get_indicators(df)
    patterns   = detect_patterns(df, last_n=5)
    tv_rating  = _tv_rating(symbol, exchange, interval)

    return {
        "symbol":      symbol.upper(),
        "exchange":    exchange.upper(),
        "interval":    interval,
        "last_candles": last_candles,
        "indicators":  indicators,
        "patterns":    patterns,
        "tv_rating":   tv_rating,
    }
