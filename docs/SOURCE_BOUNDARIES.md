# Source Boundaries

This file separates three kinds of claims, as required by `docs/spec/v2/CLAUDE_V2_POLICY.md`.

## 1. Seen in the Phantom Control video (function categories only)

The ~150-second recording shows these function categories: Home/Stats, an installer, strategy instances
("arms") with grouping and on/off toggles, Best Hours by session, Best Setups comparison, and an
"Add an Arm" form (strategy, account, ticker, timeframe, sizing, time filters).

The video does **not** reveal any algorithm, API, source code, authentication model, or reliable
performance figure. TSCH copies none of its assets, UI or strategies.

## 2. Proposed TSCH architecture (ours)

Everything under `packages/`, `services/`, `apps/web/` and `infra/` is original work. The strategy
catalog (EMA cross, RSI+BB, VWAP pullback, ORB, MACD+RSI, observer) is a list of generic, textbook
technique families. It is seeded as metadata with `implemented=false`. No performance is claimed or seeded.

## 3. Verified platform/SDK capabilities

See `docs/PLATFORM_CAPABILITY_MATRIX.md`. As of Phase 1, **no MT5 or TradingView capability has
been verified against a first-party source or a real terminal**. The relevant claims are labelled
CLAIMED (spec) or UNVERIFIED.

## Legacy code in this repository

`bot/`, `mcp_server/`, `trading/`, `main.py`, `config.py` and `markov_hedge_fund.py` predate V2.
The Telegram bot and its MCP server fetch TradingView data through `tvdatafeed` and
`tradingview-ta` (unofficial scrapers) and pass it to Claude for trade analysis. That pattern is
**outside V2 policy**. It must never be connected to TSCH order logic, and should be retired or
rewritten to use broker data before any further use. It is excluded from V2 lint, typing and tests.
