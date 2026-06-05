"""
Claude API handler with TradingView tools.
Maintains per-user conversation history and handles the tool-use loop.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

import anthropic
from config import ANTHROPIC_API_KEY, MAX_HISTORY

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_history: dict[int, list[dict]] = defaultdict(list)

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "get_market_data",
        "description": (
            "Fetch OHLCV (open/high/low/close/volume) candlestick data for any symbol "
            "from TradingView. Use this to inspect price action, recent candles, and "
            "basic market state. Supports stocks, crypto, forex, indices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Ticker symbol, e.g. BTCUSDT, AAPL, EURUSD"},
                "exchange": {"type": "string", "description": "Exchange, e.g. BINANCE, NASDAQ, FX. Default BINANCE"},
                "interval": {
                    "type": "string",
                    "enum": ["1m","3m","5m","15m","30m","1h","2h","4h","1d","1w","1M"],
                    "description": "Candle interval. Default 1h",
                },
                "bars": {"type": "integer", "description": "Number of historical bars (max 500). Default 100"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_technical_indicators",
        "description": (
            "Compute technical indicators (RSI, MACD, Bollinger Bands, EMAs, ATR, "
            "Stochastic) plus TradingView's own BUY/SELL/NEUTRAL recommendation. "
            "Use this to assess momentum, trend strength, overbought/oversold conditions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Ticker symbol"},
                "exchange": {"type": "string", "description": "Exchange. Default BINANCE"},
                "interval": {
                    "type": "string",
                    "enum": ["1m","3m","5m","15m","30m","1h","2h","4h","1d","1w","1M"],
                    "description": "Candle interval. Default 1h",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "detect_candlestick_patterns",
        "description": (
            "Detect candlestick patterns (Doji, Hammer, Engulfing, Morning Star, etc.) "
            "in the most recent candles. Returns each pattern found with its signal "
            "(bullish/bearish) and the candle timestamp."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Ticker symbol"},
                "exchange": {"type": "string", "description": "Exchange. Default BINANCE"},
                "interval": {
                    "type": "string",
                    "enum": ["1m","3m","5m","15m","30m","1h","2h","4h","1d","1w","1M"],
                    "description": "Candle interval. Default 1h",
                },
                "last_n": {
                    "type": "integer",
                    "description": "How many recent candles to scan for patterns. Default 5",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "full_market_analysis",
        "description": (
            "Run a comprehensive analysis: recent candles + technical indicators + "
            "candlestick patterns + TradingView recommendation — all in one call. "
            "Use this when the user asks for a full read, position idea, or 'what do you see'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Ticker symbol"},
                "exchange": {"type": "string", "description": "Exchange. Default BINANCE"},
                "interval": {
                    "type": "string",
                    "enum": ["1m","3m","5m","15m","30m","1h","2h","4h","1d","1w","1M"],
                    "description": "Candle interval. Default 1h",
                },
            },
            "required": ["symbol"],
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

def _execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "get_market_data":
            from trading.fetcher import get_ohlcv
            from config import TV_USERNAME, TV_PASSWORD
            df = get_ohlcv(
                symbol=inputs["symbol"],
                exchange=inputs.get("exchange", "BINANCE"),
                interval=inputs.get("interval", "1h"),
                bars=min(int(inputs.get("bars", 100)), 500),
                username=TV_USERNAME,
                password=TV_PASSWORD,
            )
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
            return json.dumps({"symbol": inputs["symbol"], "candles": rows}, indent=2)

        if name == "get_technical_indicators":
            from trading.fetcher import get_ohlcv
            from trading.indicators import get_indicators
            from trading.analysis import _tv_rating
            from config import TV_USERNAME, TV_PASSWORD
            df = get_ohlcv(
                symbol=inputs["symbol"],
                exchange=inputs.get("exchange", "BINANCE"),
                interval=inputs.get("interval", "1h"),
                bars=250,
                username=TV_USERNAME,
                password=TV_PASSWORD,
            )
            indicators = get_indicators(df)
            rating = _tv_rating(
                inputs["symbol"],
                inputs.get("exchange", "BINANCE"),
                inputs.get("interval", "1h"),
            )
            return json.dumps({"indicators": indicators, "tv_rating": rating}, indent=2)

        if name == "detect_candlestick_patterns":
            from trading.fetcher import get_ohlcv
            from trading.patterns import detect_patterns
            from config import TV_USERNAME, TV_PASSWORD
            df = get_ohlcv(
                symbol=inputs["symbol"],
                exchange=inputs.get("exchange", "BINANCE"),
                interval=inputs.get("interval", "1h"),
                bars=150,
                username=TV_USERNAME,
                password=TV_PASSWORD,
            )
            patterns = detect_patterns(df, last_n=int(inputs.get("last_n", 5)))
            return json.dumps({"patterns": patterns}, indent=2)

        if name == "full_market_analysis":
            from trading.analysis import full_analysis
            result = full_analysis(
                symbol=inputs["symbol"],
                exchange=inputs.get("exchange", "BINANCE"),
                interval=inputs.get("interval", "1h"),
            )
            return json.dumps(result, indent=2)

        return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return json.dumps({"error": str(exc)})


# ── Claude conversation loop ──────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional trading analyst connected to live TradingView data.

When the user asks about a market, chart, or position:
1. Call the appropriate tool(s) to fetch real data first.
2. Analyse the data — describe the trend, key levels, momentum, and any notable patterns.
3. Give a clear, concise position suggestion (long / short / wait) with reasoning.
4. State the key invalidation level (stop loss) and a target if the setup is valid.

Be direct and specific. Use trading terminology but keep it readable.
Never fabricate prices or indicators — always use the tool data.
Format responses with clear sections using bold headers (**)."""


def chat(user_id: int, message: str) -> str:
    """
    Send a user message and return Claude's response (including any tool calls).
    Maintains rolling conversation history per user_id.
    """
    history = _history[user_id]
    history.append({"role": "user", "content": message})

    # Keep history within limit (pairs of user/assistant turns)
    while len(history) > MAX_HISTORY * 2:
        history.pop(0)
        history.pop(0)

    messages = list(history)

    # Agentic tool-use loop
    while True:
        response = _client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Build assistant message with all content blocks
            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call: %s %s", block.name, block.input)
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Final text response
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        history.append({"role": "assistant", "content": text})
        return text


def clear_history(user_id: int) -> None:
    _history[user_id].clear()
