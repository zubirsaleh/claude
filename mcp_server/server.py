"""
TradingView MCP Server — exposes market data and analysis as MCP tools.

Run directly:
    python mcp_server/server.py

Or add to Claude Code's .claude/settings.json:
    {
      "mcpServers": {
        "tradingview": {
          "command": "python",
          "args": ["mcp_server/server.py"],
          "env": {
            "TRADINGVIEW_USERNAME": "...",
            "TRADINGVIEW_PASSWORD": "..."
          }
        }
      }
    }
"""
from __future__ import annotations

import json
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("TradingView Analysis Server")


@mcp.tool()
def get_market_data(
    symbol: str,
    exchange: str = "BINANCE",
    interval: str = "1h",
    bars: int = 100,
) -> str:
    """
    Fetch OHLCV candlestick data for a symbol from TradingView.

    Args:
        symbol:   Ticker, e.g. BTCUSDT, AAPL, EURUSD
        exchange: Exchange name, e.g. BINANCE, NASDAQ, FX
        interval: Candle interval: 1m 3m 5m 15m 30m 1h 2h 4h 1d 1w 1M
        bars:     Number of bars to fetch (max 500)
    """
    from trading.fetcher import get_ohlcv
    tv_user = os.getenv("TRADINGVIEW_USERNAME", "")
    tv_pass = os.getenv("TRADINGVIEW_PASSWORD", "")
    try:
        df = get_ohlcv(symbol, exchange, interval, min(bars, 500), tv_user, tv_pass)
        rows = []
        for _, row in df.tail(20).iterrows():
            rows.append({
                "time":   str(row.get("datetime", row.name)),
                "open":   round(float(row["open"]), 6),
                "high":   round(float(row["high"]), 6),
                "low":    round(float(row["low"]), 6),
                "close":  round(float(row["close"]), 6),
                "volume": round(float(row.get("volume", 0)), 2),
            })
        return json.dumps({"symbol": symbol.upper(), "exchange": exchange.upper(),
                           "interval": interval, "candles": rows}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def get_technical_indicators(
    symbol: str,
    exchange: str = "BINANCE",
    interval: str = "1h",
) -> str:
    """
    Compute RSI, MACD, Bollinger Bands, EMAs (9/21/50/200), ATR, Stochastic
    and fetch TradingView's BUY/SELL/NEUTRAL recommendation for a symbol.

    Args:
        symbol:   Ticker, e.g. BTCUSDT, AAPL
        exchange: Exchange name
        interval: Candle interval
    """
    from trading.fetcher import get_ohlcv
    from trading.indicators import get_indicators
    from trading.analysis import _tv_rating
    tv_user = os.getenv("TRADINGVIEW_USERNAME", "")
    tv_pass = os.getenv("TRADINGVIEW_PASSWORD", "")
    try:
        df = get_ohlcv(symbol, exchange, interval, 250, tv_user, tv_pass)
        indicators = get_indicators(df)
        rating = _tv_rating(symbol, exchange, interval)
        return json.dumps({"symbol": symbol.upper(), "interval": interval,
                           "indicators": indicators, "tv_rating": rating}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def detect_candlestick_patterns(
    symbol: str,
    exchange: str = "BINANCE",
    interval: str = "1h",
    last_n: int = 5,
) -> str:
    """
    Detect candlestick patterns in the most recent candles.
    Recognises: Doji, Hammer, Inverted Hammer, Shooting Star, Engulfing,
    Morning/Evening Star, Three White Soldiers, Three Black Crows,
    Harami, Piercing Line, Dark Cloud Cover, Dragonfly/Gravestone Doji,
    Spinning Top, Marubozu.

    Args:
        symbol:   Ticker
        exchange: Exchange
        interval: Candle interval
        last_n:   Number of recent candles to scan (default 5)
    """
    from trading.fetcher import get_ohlcv
    from trading.patterns import detect_patterns
    tv_user = os.getenv("TRADINGVIEW_USERNAME", "")
    tv_pass = os.getenv("TRADINGVIEW_PASSWORD", "")
    try:
        df = get_ohlcv(symbol, exchange, interval, 150, tv_user, tv_pass)
        patterns = detect_patterns(df, last_n=last_n)
        return json.dumps({"symbol": symbol.upper(), "interval": interval,
                           "patterns": patterns}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def full_market_analysis(
    symbol: str,
    exchange: str = "BINANCE",
    interval: str = "1h",
) -> str:
    """
    Run a complete market analysis: recent candles + technical indicators +
    candlestick patterns + TradingView recommendation — all in one call.

    Args:
        symbol:   Ticker, e.g. BTCUSDT, AAPL, EURUSD
        exchange: Exchange, e.g. BINANCE, NASDAQ, FX
        interval: Candle interval: 1h 4h 1d etc.
    """
    from trading.analysis import full_analysis
    try:
        result = full_analysis(symbol, exchange, interval)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    mcp.run()
