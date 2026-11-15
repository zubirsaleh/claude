from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from tsch_mt5_agent.classify import ToolClass, classify_tool
from tsch_mt5_agent.mcp_client import (
    McpClient,
    McpError,
    NonLoopbackEndpoint,
    ToolBlocked,
    require_loopback,
)

TOKEN = "s3cret-mcp-token-value"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:22346/mcp", "http://localhost:22346/mcp", "http://[::1]:22346/mcp",
    "http://127.0.0.2:1/mcp",
])
def test_loopback_accepted(url: str) -> None:
    assert require_loopback(url) == url


@pytest.mark.parametrize("url", [
    "http://0.0.0.0:22346/mcp", "http://10.0.0.5:22346/mcp", "http://203.0.113.9/mcp",
    "http://127.0.0.1.evil.example/mcp", "http://mt5.example.com/mcp", "file:///etc/passwd",
    "http://host.docker.internal:22346/mcp",
])
def test_non_loopback_rejected(url: str) -> None:
    with pytest.raises(NonLoopbackEndpoint):
        require_loopback(url)


@pytest.mark.parametrize("name,ann,expected", [
    ("trade_send_market_order", {}, ToolClass.TRADING),
    ("trade_send_pending_order", {}, ToolClass.TRADING),
    ("trade_modify_sl_tp", {}, ToolClass.TRADING),
    ("trade_close_single_position", {}, ToolClass.TRADING),
    # a lying annotation must not unlock a trading tool
    ("trade_send_market_order", {"readOnlyHint": True}, ToolClass.TRADING),
    ("account_info", {"readOnlyHint": True}, ToolClass.READ_ONLY),
    ("get_positions", {}, ToolClass.READ_ONLY),
    ("history_deals", {}, ToolClass.READ_ONLY),
    ("symbol_info", {}, ToolClass.READ_ONLY),
    ("get_positions", {"destructiveHint": True}, ToolClass.DANGEROUS),
    ("get_thing", {"readOnlyHint": False}, ToolClass.UNKNOWN),
    ("shell_exec", {}, ToolClass.DANGEROUS),
    ("file_write", {}, ToolClass.DANGEROUS),
    ("compile_expert", {}, ToolClass.DANGEROUS),
    ("frobnicate", {}, ToolClass.UNKNOWN),
])
def test_classification(name: str, ann: dict[str, Any], expected: ToolClass) -> None:
    assert classify_tool(name, ann) == expected


class FakeMcp:
    """Simulates a Streamable-HTTP MCP server; tool names here are illustrative only."""

    def __init__(self, sse: bool = False) -> None:
        self.sse = sse
        self.requests: list[httpx.Request] = []
        self.calls: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if req.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401)
        body = json.loads(req.content)
        if "id" not in body:
            return httpx.Response(202)
        method, rid = body["method"], body["id"]
        if method == "initialize":
            result: dict[str, Any] = {"protocolVersion": "2025-06-18",
                                      "serverInfo": {"name": "fake-mt5"}, "capabilities": {}}
        elif method == "tools/list":
            if body["params"].get("cursor") is None:
                result = {"tools": [{"name": "account_info"},
                                    {"name": "trade_send_market_order"}], "nextCursor": "p2"}
            else:
                result = {"tools": [{"name": "get_positions"}, {"name": "shell_exec"}]}
        elif method == "tools/call":
            self.calls.append(body["params"]["name"])
            result = {"content": [{"type": "text", "text": "{}"}]}
        else:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                                             "error": {"code": -32601, "message": "nope"}})
        msg = {"jsonrpc": "2.0", "id": rid, "result": result}
        headers = {"mcp-session-id": "sess-1"}
        if self.sse:
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(msg)}\n\n",
                                  headers={**headers, "content-type": "text/event-stream"})
        return httpx.Response(200, json=msg, headers=headers)


@pytest.mark.parametrize("sse", [False, True])
def test_discovery_and_blocking(sse: bool) -> None:
    fake = FakeMcp(sse=sse)
    c = McpClient("http://127.0.0.1:22346/mcp", TOKEN, transport=httpx.MockTransport(fake))
    c.initialize()
    tools = {t.name: t.classification for t in c.list_tools()}
    assert tools == {"account_info": ToolClass.READ_ONLY,
                     "trade_send_market_order": ToolClass.TRADING,
                     "get_positions": ToolClass.READ_ONLY,
                     "shell_exec": ToolClass.DANGEROUS}
    assert fake.requests[-1].headers["mcp-session-id"] == "sess-1"

    c.call_tool("account_info", {})
    for blocked in ("trade_send_market_order", "shell_exec", "not_discovered"):
        with pytest.raises(ToolBlocked):
            c.call_tool(blocked, {})
    assert fake.calls == ["account_info"]


def test_bad_token_and_no_token_leak() -> None:
    fake = FakeMcp()
    c = McpClient("http://127.0.0.1:22346/mcp", "wrong-token",
                  transport=httpx.MockTransport(fake))
    with pytest.raises(McpError, match="auth rejected") as ei:
        c.initialize()
    assert "wrong-token" not in str(ei.value)


def test_transport_error_redacts_token() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed with header {req.headers['authorization']}")

    c = McpClient("http://127.0.0.1:22346/mcp", TOKEN, transport=httpx.MockTransport(boom))
    with pytest.raises(McpError) as ei:
        c.initialize()
    assert TOKEN not in str(ei.value)


def test_client_refuses_public_endpoint() -> None:
    with pytest.raises(NonLoopbackEndpoint):
        McpClient("http://0.0.0.0:22346/mcp", TOKEN)
