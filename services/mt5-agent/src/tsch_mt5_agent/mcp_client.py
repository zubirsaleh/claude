"""Minimal MCP (JSON-RPC 2.0 over Streamable HTTP) client for the local MT5 terminal server.

UNVERIFIED against a real MT5 terminal: endpoint path, auth header and tool names come from
the V2 spec pack and must be confirmed by live `tools/list` on the installed build (Phase 4).

Safety properties enforced here regardless of what the server offers:
  * the endpoint must be a loopback address;
  * the token is read from a file and never logged or echoed in errors;
  * only tools classified READ_ONLY may be called (trading/destructive tools are blocked).
"""

from __future__ import annotations

import ipaddress
import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .classify import ToolClass, classify_tool

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_URL = "http://127.0.0.1:22346/mcp"


class McpError(Exception):
    pass


class NonLoopbackEndpoint(McpError):
    pass


class ToolBlocked(McpError):
    pass


def require_loopback(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise NonLoopbackEndpoint(f"unsupported scheme {parts.scheme!r}")
    host = parts.hostname or ""
    if host == "localhost":
        return url
    try:
        if ipaddress.ip_address(host).is_loopback:
            return url
    except ValueError:
        pass
    raise NonLoopbackEndpoint(f"MT5 MCP endpoint must be loopback, got host {host!r}")


def read_token(path: Path) -> str:
    token = path.read_text().strip()
    if not token:
        raise McpError(f"token file {path} is empty")
    return token


@dataclass
class ToolInfo:
    name: str
    description: str
    classification: ToolClass
    annotations: dict[str, Any] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(default_factory=dict)


def _parse_body(resp: httpx.Response, req_id: int) -> dict[str, Any]:
    ctype = resp.headers.get("content-type", "")
    if ctype.startswith("text/event-stream"):
        for block in resp.text.split("\n\n"):
            data = "\n".join(ln[5:].lstrip() for ln in block.splitlines()
                             if ln.startswith("data:"))
            if not data:
                continue
            msg = json.loads(data)
            if isinstance(msg, dict) and msg.get("id") == req_id:
                return msg
        raise McpError("no JSON-RPC response for request in event stream")
    msg = resp.json()
    if not isinstance(msg, dict):
        raise McpError("unexpected JSON-RPC payload")
    return msg


class McpClient:
    def __init__(
        self,
        url: str,
        token: str,
        *,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
        allowed: frozenset[ToolClass] = frozenset({ToolClass.READ_ONLY}),
    ) -> None:
        self.url = require_loopback(url)
        self._token = token
        self._auth_header = auth_header
        self._auth_value = f"{auth_scheme} {token}".strip()
        self._http = httpx.Client(transport=transport, timeout=timeout_s, trust_env=False)
        self._ids = itertools.count(1)
        self._session_id: str | None = None
        self._tools: dict[str, ToolInfo] = {}
        self.allowed = allowed
        self.server_info: dict[str, Any] = {}

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            self._auth_header: self._auth_value,
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        req_id = next(self._ids)
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        try:
            resp = self._http.post(self.url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise McpError(self._redact(f"transport error: {exc!r}")) from None
        if resp.status_code in (401, 403):
            raise McpError(f"MCP auth rejected (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise McpError(f"MCP HTTP {resp.status_code}")
        if sid := resp.headers.get("mcp-session-id"):
            self._session_id = sid
        msg = _parse_body(resp, req_id)
        if "error" in msg:
            raise McpError(self._redact(f"MCP error: {msg['error']}"))
        result = msg.get("result")
        if not isinstance(result, dict):
            raise McpError("MCP result missing")
        return result

    def _notify(self, method: str) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        self._http.post(self.url, json=payload, headers=self._headers())

    def initialize(self) -> dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "tsch-mt5-agent", "version": "0.1.0"},
        })
        self.server_info = result
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> list[ToolInfo]:
        tools: list[ToolInfo] = []
        cursor: str | None = None
        for _ in range(100):
            result = self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            for t in result.get("tools", []):
                ann = t.get("annotations") or {}
                tools.append(ToolInfo(
                    name=t["name"], description=t.get("description", ""),
                    classification=classify_tool(t["name"], ann), annotations=ann,
                    input_schema=t.get("inputSchema") or {},
                ))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self._tools = {t.name: t for t in tools}
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        info = self._tools.get(name)
        if info is None:
            raise ToolBlocked(f"tool {name!r} not in discovered inventory")
        if info.classification not in self.allowed:
            raise ToolBlocked(f"tool {name!r} is {info.classification}; not permitted")
        return self._rpc("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        self._http.close()
