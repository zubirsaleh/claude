# Trading Strategy Control Hub V2 — MT5 Demo + TradingView Research + Hostinger Ubuntu

**Status:** implementation specification and Claude Code build prompts, **not a deployed or tested trading application**. Updated for publicly documented capabilities as of 2026-11-15.

## Read this first

This V2 replaces the earlier NinjaTrader integration plan. The application is designed for one individual trader, initially using:

- **MT5 demo account** as the primary broker-connected environment for account/position visibility, historical deals, technical research, and **explicitly approved** demo transactions.
- **TradingView** as an independent charting and manual Paper Trading environment. Its official MCP server can assist with **your personal, human-readable research**; it must not feed algorithmic decisions, automated orders, signal bots, replicated databases, or the trading execution subsystem.
- **Hostinger VPS running Ubuntu 24.04** as the hosted environment, with MT5 via Wine + desktop session and Dockerized application services.
- **Claude Code** as the engineering tool. Production AI assistance must be permission-limited and must never bypass deterministic risk controls.

**Critical legal/technical restriction:** TradingView Terms of Use §3 and §27 prohibit use of TradingView MCP, content, alerts and webhooks for automated trade generation/execution or other prohibited non-display use. No supported public general-purpose TradingView Paper Trading order API is documented. Keep TradingView-side trades manual and separate from automated MT5 processes unless TradingView explicitly approves the intended use in writing.

MT5's native MCP (Build 6060, July 2026) is real: terminal, marketdata and metaeditor MCP servers. The terminal exposes account/orders/trading/history/backtest tools. Its terminal MCP server is a **local service with an API key**. It is **not** inherently an internet-safe execution service. Never expose it publicly.

## Files

1. `CLAUDE_CODE_MASTER_PROMPT_V2.md`: full end-to-end project mandate and acceptance criteria.
2. `CLAUDE_CODE_PHASE_PROMPTS_V2.md`: incremental implementation instructions; apply in sequence.
3. `CLAUDE.md`: persistent, concise Claude Code repo policy.
4. `HOSTINGER_DEPLOYMENT_AND_MCP.md`: deployment, network topology, security and connection instructions.
5. `ARCHITECTURE_AND_REQUIREMENTS.md`: diagrams, adapter contract, modules and non-functional requirements.
6. `SOURCES_AND_VERIFICATION.md`: official references and which claims must be verified in your environment.

## Starting Claude Code

```text
Read README_START_HERE.md, CLAUDE.md, ARCHITECTURE_AND_REQUIREMENTS.md,
HOSTINGER_DEPLOYMENT_AND_MCP.md and CLAUDE_CODE_MASTER_PROMPT_V2.md.
Treat V2 as the source of truth; supersede all older NinjaTrader-oriented instructions.

Start with Phase 1 from CLAUDE_CODE_PHASE_PROMPTS_V2.md. Build the first
working vertical slice, not merely a report. Use a fully deterministic SIM
adapter until you can verify an actual MT5 demo terminal and MCP connection.
Never enable live trading, and never connect TradingView content to order
logic. Run tests, log failures, fix what is testable, and explicitly enumerate
integration checks that require my Hostinger VPS / broker credentials.
```

## What you must supply later (securely, not in prompts)

- Hostinger VPS access and a domain (or private-access setup).
- MT5 demo broker, demo server name and credentials; **never paste passwords into AI prompts, logs, Git or repo files**.
- Appropriate TradingView subscription for official MCP, if desired.
- Approval when testing demo trades. Real-account access requires a separate change-control milestone.

Do not claim a real account, TradingView Paper account or MT5 demo account is linked until access and end-to-end reconciliation have been tested.
