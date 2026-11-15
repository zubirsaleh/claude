# Trading Strategy Control Hub — Instructions to Claude Code

## Core truth

This repository targets **MT5 DEMO + broker-independent SIM**, hosted on **Hostinger Ubuntu 24.04**, with optional **TradingView personal research through official MCP**. This supersedes all NinjaTrader-oriented earlier designs. The original video documents a *class* of functionality only, not any proprietary strategy algorithm.

- Build working vertical slices with migrations, APIs, UI, tests and documentation. Never claim code runs without showing actual test/compile result.
- Operating states: `SIM`, `MT5_DEMO`, `TRADINGVIEW_PAPER_MANUAL`, `LIVE_DISABLED`. Default `SIM`.
- Never route TradingView MCP/webhook/market-data output into a trading strategy, order generator, AI trade decision, broker execution system, persistent market-data feed or autonomous analysis agent. TradingView MCP permitted only for user's personal request/response and human-readable display under provider terms.
- MT5 is the only intended demo execution backend; use MT5's **own broker data** for algorithmic/backtest research where licensed/permitted. MT5 MCP is a verified official capability, but specific build/broker/Ubuntu Wine compatibility must be proven. No assumed working connection.
- Human-in-the-loop: no unattended demo order placement by default; each proposed order requires explicit approval with expiry, symbol, side, quantity, estimated risk, account, SL/TP, version and idempotency key. AI must never be sole authorizer.
- LIVE mode is unavailable in runtime and tests by default. No auto-toggle from demo to live. Require distinct live risk controls, manual security review, confirmed account identification and separate deployment secrets.
- Guard account identity and server/type on EVERY order attempt, both before authorization and just before send. Fail closed on changed account / stale heartbeat / missing quotes / risk service error.
- Never expose MT5 MCP ports or tokens publicly; prefer `127.0.0.1` with a restricted host-side agent. No browser-to-MCP direct connection.
- Risk defaults must be configurable and conservative. Initial per-trade ceiling 2% is a **maximum, not a recommended size**. Position sizing uses broker symbol tick size, tick value, contract size and account currency; no GC futures assumptions for XAUUSD CFDs.
- Always store raw fills and immutable audit records; metrics must distinguish realized gross/net, open P&L, costs, currency conversions, stop risk, missing data and synthetic data.
- Market time in UTC at rest; market sessions in IANA zones with DST handling; user display defaults Asia/Kuala_Lumpur.
- Deterministic tests for duplicate commands, stale state, reconnect, partial fills, missed heartbeats, broker rejections and recovery.
- No fabricated win rates, fake actual trades or claims of strategy profitability. Backtest = historical hypothesis, not live performance.
- `docs/SOURCE_BOUNDARIES.md` must distinguish functionality visible in the Phantom video, proposed architecture, and verified SDK capabilities.
- Before every MCP tool use list tools, verify permission, and avoid shell/web or trade tools unless explicitly required. Never log bearer tokens or credentials.
- Use `.env.example`, secret files or secret management; never commit `.env`, `.mcp.json`, credential exports or session cookies.
- After each milestone report features built, files changed, tests run with results, unresolved prerequisites, and exact next steps.
