# Platform Capability Matrix

Last updated 2026-11-15 (Phase 1).

**How to read this.** Every row is labelled:

- **VERIFIED (code):** proven by tests or by running it in this repository.
- **CLAIMED (spec):** stated in the V2 spec pack (`docs/spec/v2/`). Not checked against a first-party source by us yet.
- **UNVERIFIED:** must be confirmed on the real platform before anything relies on it.
- **NOT SUPPORTED:** deliberately absent.

> **Verification gap.** During Phase 1 the build environment's network policy blocked
> `www.metatrader5.com`, `www.metaquotes.com` and `www.tradingview.com`, so none of the
> first-party pages listed in `docs/spec/v2/SOURCES_AND_VERIFICATION.md` could be read. Every
> MT5 and TradingView fact below is therefore **CLAIMED** or **UNVERIFIED**. Nothing in this
> repository depends on those claims being true: the MT5 path is mocked and default-deny.

## MetaTrader 5 native MCP

| Capability | Status | Notes / how we verify |
|---|---|---|
| Native MCP introduced in MT5 Build 6060 (Jul 2026) | CLAIMED (spec) | Check `Help > About` build on the VPS terminal. |
| Terminal MCP endpoint `http://127.0.0.1:22346/mcp` | CLAIMED (spec) | `tsch-mt5-agent discover` against the real terminal (Phase 4). |
| MetaEditor MCP `127.0.0.1:22345` | CLAIMED (spec) | Keep disabled. Not used by TSCH. |
| Market-data MCP server | CLAIMED (spec) | Not used in Phase 1. |
| Transport: Streamable HTTP, JSON-RPC 2.0 | UNVERIFIED | Agent handles both `application/json` and `text/event-stream` responses plus `Mcp-Session-Id`. Tested against a mock only. |
| Auth: bearer API key generated in the GUI | CLAIMED (spec) | Header name is configurable (`TSCH_MT5_MCP_AUTH_HEADER`). Confirm on install. |
| Binds to loopback only | UNVERIFIED | Confirm with `ss -ltnp` on the VPS and an external port scan (deployment checklist item 7). |
| Tool names (e.g. `trade_send_market_order`, `trade_modify_sl_tp`, `trade_close_single_position`) | CLAIMED (spec) | Live `tools/list` enumeration on the installed build. The agent classifies by name and blocks anything not clearly read-only. |
| Per-tool permission / confirmation modes in the MT5 AI assistant | UNVERIFIED | Set to "no trade" in the GUI. App-side approval is mandatory regardless. |
| MT5 runs on Ubuntu 24.04 via Wine | CLAIMED (spec) | Hostinger "Ubuntu 24.04 with MetaTrader" template. Reboot-persistence test in Phase 6. |
| Official Python `MetaTrader5` package on Linux | NOT SUPPORTED (by us) | Windows-terminal oriented. Not used. |

## TradingView

| Capability | Status | Notes |
|---|---|---|
| Official MCP at `https://mcp.tradingview.com/mcp`, OAuth | CLAIMED (spec) | Personal Claude session only. Never configured in this app. |
| Terms §3 / §27 prohibit automated trading use of MCP, data, alerts and webhooks | CLAIMED (spec) | Treated as binding. Enforced by `tests/security/test_boundaries.py` (no TradingView data paths in V2 code). |
| Paper Trading order API | NOT SUPPORTED | None documented. TSCH offers a manual journal only (Phase 2+). |
| Using TradingView data for research, backtests or signals | NOT SUPPORTED | Research uses broker or synthetic data only. |

## Hostinger

| Capability | Status | Notes |
|---|---|---|
| "Ubuntu 24.04 with MetaTrader" VPS template | CLAIMED (spec) | Validate at provisioning. Changing templates can wipe the VPS. |
| Docker Engine + Compose on the same VPS | UNVERIFIED on Hostinger | **VERIFIED (code)** locally: the stack builds and runs (see `docs/PHASE1_REPORT.md`). |

## TSCH itself (Phase 1)

| Capability | Status |
|---|---|
| SIM adapter: deterministic synthetic prices, fills, idempotent submit, fault injection | VERIFIED (code) |
| Risk gate: fails closed on stale, missing or changed state | VERIFIED (code) |
| Order state machine: approval expiry, atomic claim, no resubmit from UNKNOWN | VERIFIED (code) |
| Append-only fills, order events and audit log (PostgreSQL triggers) | VERIFIED (code) |
| Hash-chained audit with tamper detection | VERIFIED (code) |
| LIVE execution | NOT SUPPORTED (not compiled in) |
| MT5_DEMO execution | NOT SUPPORTED yet (Phase 4/5) |
