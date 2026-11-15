"""Conservative classification of discovered MCP tools.

Server-supplied annotations are hints and can be wrong, so they can only make a tool
*less* trusted. A tool is READ_ONLY only when its name looks like a read and nothing marks it
as trading or destructive. Anything unrecognised is UNKNOWN and therefore blocked.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any


class ToolClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    TRADING = "TRADING"
    DANGEROUS = "DANGEROUS"
    UNKNOWN = "UNKNOWN"


_DANGEROUS = re.compile(
    r"(shell|exec|command|file|write|delete|remove|compile|install|attach|run_|script|"
    r"terminal_(close|restart|shutdown)|chart_apply|expert)", re.I)
_TRADING = re.compile(
    r"(trade|order_send|send|modify|close|cancel|place|buy|sell|position_(open|close)|"
    r"sl_tp|pending)", re.I)
_READ = re.compile(
    r"^(get|list|read|fetch|query|account|symbol|symbols|history|positions|orders|deals|"
    r"market|quote|tick|rates|bars|info|status|version|ping|terminal_info)", re.I)


def classify_tool(name: str, annotations: dict[str, Any] | None = None) -> ToolClass:
    ann = annotations or {}
    if _DANGEROUS.search(name):
        return ToolClass.DANGEROUS
    if _TRADING.search(name):
        return ToolClass.TRADING
    if ann.get("destructiveHint") is True:
        return ToolClass.DANGEROUS
    if ann.get("readOnlyHint") is False:
        return ToolClass.UNKNOWN
    if _READ.search(name):
        return ToolClass.READ_ONLY
    return ToolClass.UNKNOWN
