#!/usr/bin/env python3
"""
TradingView MCP Server
──────────────────────
Exposes TradingView technical analysis data as MCP tools so Claude can
read live price, indicators, and signals for any symbol.

USAGE (run locally — TradingView blocks cloud IPs):
  pip install tradingview-ta mcp
  python tradingview_mcp_server.py

Then add to ~/.claude/claude_desktop_config.json (Claude Desktop) or
~/.claude/settings.json (Claude Code):

  "mcpServers": {
    "tradingview": {
      "command": "python3",
      "args": ["/path/to/tradingview_mcp_server.py"]
    }
  }

AVAILABLE TOOLS (callable by Claude):
  get_analysis   — full TA: price, RSI, MACD, EMA, BB, ATR, signals
  get_price      — current price + 24h change only
  get_signal     — overall buy/sell/neutral recommendation + strength
  scan_symbols   — check multiple symbols at once
"""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── tradingview-ta import ──────────────────────────────────────────────────
try:
    from tradingview_ta import TA_Handler, Interval
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False

# ── Interval mapping ──────────────────────────────────────────────────────
INTERVAL_MAP = {
    "1m":  Interval.INTERVAL_1_MINUTE,
    "5m":  Interval.INTERVAL_5_MINUTES,
    "15m": Interval.INTERVAL_15_MINUTES,
    "30m": Interval.INTERVAL_30_MINUTES,
    "1h":  Interval.INTERVAL_1_HOUR,
    "2h":  Interval.INTERVAL_2_HOURS,
    "4h":  Interval.INTERVAL_4_HOURS,
    "1d":  Interval.INTERVAL_1_DAY,
    "1W":  Interval.INTERVAL_1_WEEK,
    "1M":  Interval.INTERVAL_1_MONTH,
} if TV_AVAILABLE else {}

# Common XAU/USD configs to try in order
XAUUSD_CONFIGS = [
    ("XAUUSD", "forex",  "OANDA"),
    ("XAUUSD", "cfd",    "TVC"),
    ("GOLD",   "cfd",    "TVC"),
    ("GOLD",   "cfd",    "OANDA"),
    ("XAUUSD", "forex",  "FX_IDC"),
]

# ── Helper ────────────────────────────────────────────────────────────────
def resolve_symbol(symbol: str, screener: str, exchange: str):
    """Try the given config; if it fails and symbol looks like XAUUSD, try fallbacks."""
    symbols_to_try = [(symbol.upper(), screener, exchange)]
    if symbol.upper() in ("XAUUSD", "GOLD", "XAUUSDT"):
        symbols_to_try = XAUUSD_CONFIGS + symbols_to_try
    return symbols_to_try


def fetch_analysis(symbol: str, screener: str, exchange: str, interval: str):
    iv = INTERVAL_MAP.get(interval, Interval.INTERVAL_1_DAY)
    configs = resolve_symbol(symbol, screener, exchange)
    last_err = None
    for sym, scr, exch in configs:
        try:
            handler = TA_Handler(
                symbol=sym,
                screener=scr,
                exchange=exch,
                interval=iv,
            )
            return handler.get_analysis(), sym, scr, exch
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"Could not fetch {symbol}: {last_err}")


def format_signal(summary: dict) -> str:
    rec = summary.get("RECOMMENDATION", "NEUTRAL")
    buy = summary.get("BUY", 0)
    sell = summary.get("SELL", 0)
    neu = summary.get("NEUTRAL", 0)
    total = buy + sell + neu or 1
    strength = abs(buy - sell) / total * 100
    return f"{rec}  (Buy:{buy} Sell:{sell} Neutral:{neu}  strength:{strength:.0f}%)"


# ── MCP Server ───────────────────────────────────────────────────────────
server = Server("tradingview")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_analysis",
            description=(
                "Fetch full TradingView technical analysis for a symbol. "
                "Returns price, RSI, MACD, EMA (9/21/50/200), Bollinger Bands, "
                "ATR, SuperTrend, and buy/sell/neutral signals."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol":   {"type": "string", "description": "e.g. XAUUSD, BTCUSD, EURUSD, AAPL"},
                    "interval": {"type": "string", "enum": list(INTERVAL_MAP.keys()), "default": "1d"},
                    "screener": {"type": "string", "description": "forex / crypto / america / cfd", "default": "forex"},
                    "exchange": {"type": "string", "description": "OANDA / BINANCE / NASDAQ etc.", "default": "OANDA"},
                },
                "required": ["symbol"],
            },
        ),
        types.Tool(
            name="get_price",
            description="Get current price and 24h change for a symbol.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol":   {"type": "string"},
                    "screener": {"type": "string", "default": "forex"},
                    "exchange": {"type": "string", "default": "OANDA"},
                },
                "required": ["symbol"],
            },
        ),
        types.Tool(
            name="get_signal",
            description=(
                "Get TradingView's overall buy/sell/neutral recommendation "
                "for a symbol on a given timeframe."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol":   {"type": "string"},
                    "interval": {"type": "string", "enum": list(INTERVAL_MAP.keys()), "default": "1d"},
                    "screener": {"type": "string", "default": "forex"},
                    "exchange": {"type": "string", "default": "OANDA"},
                },
                "required": ["symbol"],
            },
        ),
        types.Tool(
            name="scan_symbols",
            description="Scan multiple symbols at once and return their signal summary.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "symbol":   {"type": "string"},
                                "screener": {"type": "string"},
                                "exchange": {"type": "string"},
                            },
                            "required": ["symbol"],
                        },
                    },
                    "interval": {"type": "string", "default": "1d"},
                },
                "required": ["symbols"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if not TV_AVAILABLE:
        return [types.TextContent(type="text", text="ERROR: tradingview-ta not installed. Run: pip install tradingview-ta")]

    try:
        if name == "get_price":
            symbol   = arguments["symbol"]
            screener = arguments.get("screener", "forex")
            exchange = arguments.get("exchange", "OANDA")
            analysis, sym, scr, exch = fetch_analysis(symbol, screener, exchange, "1d")
            ind = analysis.indicators
            close = ind.get("close", 0)
            prev  = ind.get("open", close)
            chg   = close - prev
            chg_pct = chg / prev * 100 if prev else 0
            result = {
                "symbol":   sym,
                "exchange": exch,
                "price":    round(close, 4),
                "change":   round(chg, 4),
                "change_pct": round(chg_pct, 2),
                "high":     round(ind.get("high", 0), 4),
                "low":      round(ind.get("low", 0), 4),
                "volume":   ind.get("volume"),
            }
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_signal":
            symbol   = arguments["symbol"]
            interval = arguments.get("interval", "1d")
            screener = arguments.get("screener", "forex")
            exchange = arguments.get("exchange", "OANDA")
            analysis, sym, scr, exch = fetch_analysis(symbol, screener, exchange, interval)
            result = {
                "symbol":     sym,
                "exchange":   exch,
                "interval":   interval,
                "signal":     format_signal(analysis.summary),
                "summary":    analysis.summary,
                "oscillators": analysis.oscillators.get("RECOMMENDATION"),
                "moving_avgs": analysis.moving_averages.get("RECOMMENDATION"),
            }
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_analysis":
            symbol   = arguments["symbol"]
            interval = arguments.get("interval", "1d")
            screener = arguments.get("screener", "forex")
            exchange = arguments.get("exchange", "OANDA")
            analysis, sym, scr, exch = fetch_analysis(symbol, screener, exchange, interval)
            ind = analysis.indicators
            close = ind.get("close", 0)

            result = {
                "symbol":   sym,
                "exchange": exch,
                "interval": interval,
                "price": {
                    "close":  round(close, 4),
                    "open":   round(ind.get("open",  0), 4),
                    "high":   round(ind.get("high",  0), 4),
                    "low":    round(ind.get("low",   0), 4),
                    "volume": ind.get("volume"),
                },
                "signal": format_signal(analysis.summary),
                "summary": analysis.summary,
                "oscillators": {
                    "RSI":    round(ind.get("RSI",  0), 2),
                    "MACD":   round(ind.get("MACD.macd", 0), 4),
                    "MACD_signal": round(ind.get("MACD.signal", 0), 4),
                    "Stoch_K":  round(ind.get("Stoch.K", 0), 2),
                    "Stoch_D":  round(ind.get("Stoch.D", 0), 2),
                    "CCI":    round(ind.get("CCI20", 0), 2),
                    "ADX":    round(ind.get("ADX", 0), 2),
                    "Williams_R": round(ind.get("W.R", 0), 2),
                    "recommendation": analysis.oscillators.get("RECOMMENDATION"),
                },
                "moving_averages": {
                    "EMA9":   round(ind.get("EMA9",  close), 4),
                    "EMA20":  round(ind.get("EMA20", close), 4),
                    "EMA50":  round(ind.get("EMA50", close), 4),
                    "EMA200": round(ind.get("EMA200", close), 4),
                    "SMA20":  round(ind.get("SMA20",  close), 4),
                    "SMA50":  round(ind.get("SMA50",  close), 4),
                    "SMA200": round(ind.get("SMA200", close), 4),
                    "BB_upper": round(ind.get("BB.upper", 0), 4),
                    "BB_lower": round(ind.get("BB.lower", 0), 4),
                    "recommendation": analysis.moving_averages.get("RECOMMENDATION"),
                },
                "atr":      round(ind.get("ATR", 0), 4),
                "pivot_classic": {
                    "R3": round(ind.get("Pivot.M.Classic.R3", 0), 4),
                    "R2": round(ind.get("Pivot.M.Classic.R2", 0), 4),
                    "R1": round(ind.get("Pivot.M.Classic.R1", 0), 4),
                    "P":  round(ind.get("Pivot.M.Classic.Middle", 0), 4),
                    "S1": round(ind.get("Pivot.M.Classic.S1", 0), 4),
                    "S2": round(ind.get("Pivot.M.Classic.S2", 0), 4),
                    "S3": round(ind.get("Pivot.M.Classic.S3", 0), 4),
                },
            }
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "scan_symbols":
            symbols  = arguments["symbols"]
            interval = arguments.get("interval", "1d")
            rows = []
            for item in symbols:
                sym  = item["symbol"]
                scr  = item.get("screener", "forex")
                exch = item.get("exchange", "OANDA")
                try:
                    analysis, rsym, rscr, rexch = fetch_analysis(sym, scr, exch, interval)
                    ind   = analysis.indicators
                    close = ind.get("close", 0)
                    rows.append({
                        "symbol":   rsym,
                        "exchange": rexch,
                        "price":    round(close, 4),
                        "RSI":      round(ind.get("RSI", 0), 1),
                        "signal":   analysis.summary.get("RECOMMENDATION", "N/A"),
                        "buy":      analysis.summary.get("BUY", 0),
                        "sell":     analysis.summary.get("SELL", 0),
                        "neutral":  analysis.summary.get("NEUTRAL", 0),
                    })
                except Exception as e:
                    rows.append({"symbol": sym, "error": str(e)})
            return [types.TextContent(type="text", text=json.dumps(rows, indent=2))]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [types.TextContent(type="text", text=f"ERROR: {e}")]


# ── Entry point ───────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
