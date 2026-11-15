# Claude Code Phase Prompts V2

Run these separately in the same repository after the master prompt. **Never start live trading as part of any phase.**

## Phase 1 — Validate MCP & Ubuntu feasibility, scaffold

Read all V2 prompt pack docs. Verify MT5 native MCP Build 6060+ terminal tools, API key and loopback endpoint from the actual installed terminal where available; identify which tools are authorized, which are read-only and which are potentially destructive. Check Hostinger Ubuntu 24.04 MetaTrader image and Wine/MT5 compatibility. Document the TradingView MCP Terms of Use constraints; never integrate TradingView market data into the execution path. Create an executable monorepo skeleton, Docker Compose, CI, OpenAPI, first DB migration, SIM adapter, tests, capability matrix and threat model. No credentials required for SIM. Run the stack and tests. State unverified platform integration explicitly.

## Phase 2 — Build complete dashboard and arm management

Build Next.js frontend and FastAPI/Postgres backend with durable authentication, account tables, strategy catalog, editable arm assignments, mode badges and exact feature pages: Home, Stats, Today, Strategies, Add Arm, Best Hours, Best Setups, Accounts, Positions, Approval Queue, Backtests, Trade Journal, Risk, Connections and Audit. Start with SIM broker adapter and genuine persistent state. Group start/stop returns per-arm durable command status and observed SIM acknowledgment; UI must not just toggle itself. Implement a full sample data generator labeled synthetic. Run migrations, tests, browser smoke tests and produce accessible screenshots.

## Phase 3 — Analytics and research

Implement immutable fills, order/position reconciliation, broker math, mark-to-market, commission/swap/fees, R calculations only with known initial stop-risk, day calendar, session DST grouping, Best Hours heatmap, Best Setups ranking, quality/confidence gates, out-of-sample walk-forward and CSV/HTML reports. Research uses only separately licensed broker data or synthetic fixtures, NEVER TradingView MCP content. Build unit tests for partial fills, netting, hedging, reversals, XAUUSD point/tick/lot mismatches, timezone/DST, missing costs, market close and disconnects. Run and report results.

## Phase 4 — MT5 DEMO host-side connector and MCP integration

Build a restricted `mt5-agent` host service connecting to `http://127.0.0.1:22346/mcp` via supported MT5 native MCP transport and an API key stored outside Git. Document MT5 MCP setup in GUI Tools > Options > MCP, permission control and tool discovery. Do not publish MT5 MCP on VPS interface. Agent fetches approved internal commands and publishes observed broker account identity, positions, orders, deals, market bars and health. On Hostinger with a real demo login, verify exact tool names, versions, session persistence, Wine process health and broker semantics. If the terminal does not exist, provide exhaustive contract mocks and an honest manual acceptance checklist. Confirm `demo` account type immediately before every order action.

## Phase 5 — Human-approved demo order flow and risk policy

Implement proposed signal -> deterministic risk check -> authenticated human approval -> expiring command -> MT5-demo send -> acknowledgment/unknown -> reconciliation. No unattended AI order execution. Apply max per-trade risk cap configurable up to 2%, daily/total drawdown stop, symbol/volume/margin/spread checks, broker-currency conversion and order-level idempotency. Add local circuit breaker and no-new-entries kill switch. Prove wrong-account-mode, lost auth, stale broker, duplicate fill and unknown submit outcomes fail closed. Add original signal-only XAUUSD strategies and optional MQL5 demo EA gated by human approval and installed broker capabilities. Keep TradingView completely out of this execution loop.

## Phase 6 — Deploy to Hostinger Ubuntu VPS

Write production Docker Compose for frontend/API/worker/Postgres/Redis/reverse proxy and host-side systemd MT5 agent. Support Hostinger Ubuntu 24.04 with MetaTrader template (desktop + Wine). Restrict SSH and remote desktop, secure TLS, disable public MT5 MCP exposure, configure DB backups and offsite restore, log rotation, health checks, OS reboot recovery and metrics. Document domain/DNS, firewall, secrets, system requirements and deployment rollback. Don't claim a successful Hostinger deployment without actual VPS SSH and GUI validation. Run local Compose and CI checks.

## Phase 7 — Acceptance and later live broker design, DO NOT ENABLE LIVE

Audit code/security/reconciliation/risk, complete release acceptance checklist and carry out offline/SIM tests, then MT5 DEMO tests if actual broker available. Prepare a separate future proposal for live brokers including account segregation, live risk limits, approvals, operational monitoring and rollback. Live trading must remain technically disabled. Produce defect register with severity, test report, operator runbook, screenshots and final known limitations.
