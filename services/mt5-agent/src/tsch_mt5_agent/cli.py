"""`tsch-mt5-agent discover` — enumerate the local MT5 MCP tools and print their classification.

Configuration (environment):
  TSCH_MT5_MCP_URL         default http://127.0.0.1:22346/mcp (must be loopback)
  TSCH_MT5_MCP_TOKEN_FILE  path to a file holding the MCP API key (required, chmod 600)
  TSCH_MT5_MCP_AUTH_HEADER default "Authorization" (verify against installed build)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .mcp_client import DEFAULT_URL, McpClient, McpError, read_token


def _client() -> McpClient:
    token_file = os.environ.get("TSCH_MT5_MCP_TOKEN_FILE")
    if not token_file:
        raise McpError("TSCH_MT5_MCP_TOKEN_FILE is not set")
    return McpClient(
        os.environ.get("TSCH_MT5_MCP_URL", DEFAULT_URL),
        read_token(Path(token_file)),
        auth_header=os.environ.get("TSCH_MT5_MCP_AUTH_HEADER", "Authorization"),
    )


def discover() -> int:
    client = _client()
    try:
        info = client.initialize()
        tools = client.list_tools()
    finally:
        client.close()
    print(json.dumps({
        "server": info.get("serverInfo", {}),
        "protocolVersion": info.get("protocolVersion"),
        "tools": [{"name": t.name, "class": t.classification, "annotations": t.annotations,
                   "description": t.description} for t in tools],
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tsch-mt5-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="list and classify MT5 MCP tools (read-only)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "discover":
            sys.exit(discover())
    except McpError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
