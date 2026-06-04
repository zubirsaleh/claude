"""
TradingView MCP Health Check

Verifies:
  1. TradingView WebSocket connectivity
  2. Real-time quote subscription (XAUUSD by default)
  3. MCP server reachability (if --mcp-url is provided)

Usage:
    python tv_health_check.py                        # basic WebSocket check
    python tv_health_check.py --symbol BTCUSD        # different symbol
    python tv_health_check.py --mcp-url http://localhost:8000  # also check MCP server
    python tv_health_check.py --timeout 10           # custom timeout (seconds)
"""

import argparse
import json
import random
import re
import string
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Constants ────────────────────────────────────────────────────────────────

TV_WS_URL = "wss://data.tradingview.com/socket.io/websocket?from=chart%2F&date=2024_06_04-10_00"
TV_WS_ORIGIN = "https://www.tradingview.com"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEOUT = 8  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rand_session_id(n: int = 12) -> str:
    return "qs_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _tv_packet(func: str, args: list) -> str:
    payload = json.dumps({"m": func, "p": args})
    return f"~m~{len(payload)}~m~{payload}"


def _parse_tv_packets(raw: str) -> list[dict]:
    results = []
    for chunk in re.findall(r"~m~\d+~m~(.*?)(?=~m~\d+~m~|$)", raw, re.DOTALL):
        try:
            results.append(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    return results


# ── Check 1: TradingView WebSocket ───────────────────────────────────────────

def check_tradingview_websocket(symbol: str, timeout: int) -> dict:
    result = {"name": "TradingView WebSocket", "status": "FAIL", "latency_ms": None, "detail": ""}
    try:
        import websocket  # websocket-client
    except ImportError:
        result["detail"] = "websocket-client not installed — run: pip install websocket-client"
        return result

    session = _rand_session_id()
    quote_session = _rand_session_id()
    received_data = []
    t_start = time.monotonic()

    def on_open(ws):
        ws.send(_tv_packet("set_auth_token", ["unauthorized_user_token"]))
        ws.send(_tv_packet("quote_create_session", [quote_session]))
        ws.send(_tv_packet("quote_add_symbols", [quote_session, symbol]))
        ws.send(_tv_packet("quote_fast_symbols", [quote_session, symbol]))

    def on_message(ws, msg):
        # TradingView sends a heartbeat ~h~ — respond to keep alive
        if "~h~" in msg:
            ws.send(f"~m~{len(msg)}~m~{msg}")
            return
        packets = _parse_tv_packets(msg)
        for pkt in packets:
            if pkt.get("m") == "qsd":
                received_data.append(pkt)
                ws.close()

    def on_error(ws, err):
        msg = str(err)
        if "403" in msg or "host_not_allowed" in msg:
            msg += " (TradingView blocks server/cloud IPs — WebSocket check works from a local machine only)"
        result["detail"] = msg

    def on_close(ws, *_):
        pass

    ws_app = websocket.WebSocketApp(
        TV_WS_URL,
        header={
            "Origin": TV_WS_ORIGIN,
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    import threading
    t = threading.Thread(target=lambda: ws_app.run_forever(), daemon=True)
    t.start()
    t.join(timeout=timeout)

    latency_ms = round((time.monotonic() - t_start) * 1000)
    result["latency_ms"] = latency_ms

    if received_data:
        pkt = received_data[0]
        fields = pkt.get("p", [{}])[-1].get("v", {})
        price = fields.get("lp") or fields.get("last_price")
        result["status"] = "PASS"
        result["detail"] = (
            f"Received quote for {symbol} — "
            f"price={price or 'n/a'}, "
            f"latency={latency_ms}ms"
        )
    else:
        if not result["detail"]:
            result["detail"] = f"No quote received within {timeout}s"

    return result


# ── Check 2: TradingView REST fallback (symbol search) ───────────────────────

def check_tradingview_rest(symbol: str, timeout: int) -> dict:
    """Uses TradingView's public symbol search API — works from any host."""
    result = {"name": "TradingView REST API", "status": "FAIL", "latency_ms": None, "detail": ""}
    url = (
        f"https://symbol-search.tradingview.com/symbol_search/v3/"
        f"?text={symbol}&hl=1&exchange=&lang=en&search_type=undefined&domain=production&sort_by_country=US"
    )
    t_start = time.monotonic()
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.tradingview.com/",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            latency_ms = round((time.monotonic() - t_start) * 1000)
            result["latency_ms"] = latency_ms
            symbols = body.get("symbols", [])[:3]
            found = [s.get("symbol", "?") for s in symbols]
            result["status"] = "PASS"
            result["detail"] = f"Symbol search OK — top results: {', '.join(found)}, latency={latency_ms}ms"
    except Exception as e:
        result["detail"] = str(e)
    return result


# ── Check 3: Yahoo Finance fallback — verifies XAUUSD data is reachable ──────

def check_yahoo_finance(symbol: str, timeout: int) -> dict:
    """
    Yahoo Finance accepts server-side requests. Used as a fallback to confirm
    XAU/USD price data is reachable when TradingView blocks the connection.
    Yahoo symbol for Gold/USD is GC=F (futures) or XAUUSD=X.
    """
    yahoo_sym = "XAUUSD=X" if "XAU" in symbol.upper() else symbol
    result = {"name": f"Yahoo Finance fallback ({yahoo_sym})", "status": "FAIL", "latency_ms": None, "detail": ""}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=5m&range=1d"
    t_start = time.monotonic()
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            latency_ms = round((time.monotonic() - t_start) * 1000)
            result["latency_ms"] = latency_ms
            meta = body["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            change_pct = ((price - prev_close) / prev_close * 100) if price and prev_close else None
            direction = "BULLISH" if change_pct and change_pct > 0 else "BEARISH" if change_pct and change_pct < 0 else "FLAT"
            result["status"] = "PASS"
            result["detail"] = (
                f"{yahoo_sym} — price=${price:,.2f}, "
                f"change={change_pct:+.2f}% ({direction}), "
                f"latency={latency_ms}ms"
            )
    except Exception as e:
        result["detail"] = str(e)
    return result


# ── Check 4: MCP Server HTTP ping ─────────────────────────────────────────────

def check_mcp_server(url: str, timeout: int) -> dict:
    result = {"name": f"MCP Server ({url})", "status": "FAIL", "latency_ms": None, "detail": ""}
    endpoints = ["/health", "/", "/tools"]
    t_start = time.monotonic()
    for ep in endpoints:
        try:
            req = urllib.request.Request(
                url.rstrip("/") + ep,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                latency_ms = round((time.monotonic() - t_start) * 1000)
                result["latency_ms"] = latency_ms
                result["status"] = "PASS"
                result["detail"] = f"HTTP {resp.status} on {ep}, latency={latency_ms}ms"
                return result
        except urllib.error.HTTPError as e:
            if e.code < 500:
                latency_ms = round((time.monotonic() - t_start) * 1000)
                result["latency_ms"] = latency_ms
                result["status"] = "PASS"
                result["detail"] = f"HTTP {e.code} on {ep} (server reachable), latency={latency_ms}ms"
                return result
        except Exception as e:
            result["detail"] = str(e)
    return result


# ── MCP tools list check ──────────────────────────────────────────────────────

def check_mcp_tools(url: str, timeout: int) -> dict:
    result = {"name": "MCP Tools Endpoint", "status": "FAIL", "latency_ms": None, "detail": ""}
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    t_start = time.monotonic()
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            latency_ms = round((time.monotonic() - t_start) * 1000)
            result["latency_ms"] = latency_ms
            tools = body.get("result", {}).get("tools", [])
            names = [t.get("name", "?") for t in tools[:6]]
            result["status"] = "PASS"
            result["detail"] = f"{len(tools)} tool(s) available: {', '.join(names)}"
    except Exception as e:
        result["detail"] = str(e)
    return result


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(checks: list[dict]) -> bool:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\nTradingView MCP Health Check — {now}")
    print("=" * 60)
    all_pass = True
    for c in checks:
        icon = "✓" if c["status"] == "PASS" else "✗"
        lat = f"  [{c['latency_ms']}ms]" if c["latency_ms"] is not None else ""
        print(f"  {icon} {c['name']}{lat}")
        print(f"      {c['detail']}")
        if c["status"] != "PASS":
            all_pass = False
    print("=" * 60)
    overall = "ALL CHECKS PASSED" if all_pass else "ONE OR MORE CHECKS FAILED"
    print(f"  Result: {overall}\n")
    return all_pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TradingView MCP health check")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Symbol to test (default: XAUUSD)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    parser.add_argument("--mcp-url", default=None, help="MCP server base URL, e.g. http://localhost:8000")
    args = parser.parse_args()

    checks = [
        check_tradingview_websocket(args.symbol, args.timeout),
        check_tradingview_rest(args.symbol, args.timeout),
        check_yahoo_finance(args.symbol, args.timeout),
    ]

    if args.mcp_url:
        checks.append(check_mcp_server(args.mcp_url, args.timeout))
        checks.append(check_mcp_tools(args.mcp_url, args.timeout))

    passed = print_report(checks)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
