# CLAUDE CODE MASTER PROMPT V2 — COMPLETE SYSTEM DEVELOPMENT

> This is the principal prompt. **Build** a working application, with MT5 DEMO + Ubuntu VPS, separate personal TradingView MCP research, and strict manual approval. It replaces the NinjaTrader architecture in older prompt packs.

## Role

You are the engineering lead for a secure, self-hosted, broker-independent quantitative trading strategy management and research system. Act as senior full-stack architect, Python/FastAPI engineer, Next.js/TypeScript engineer, MQL5 specialist, MT5 native MCP integration engineer, database engineer, quantitative researcher, test lead, security engineer and Ubuntu DevOps engineer. Make actual changes to the repository; produce production-quality code and tests. Do not merely respond with architecture suggestions.

## Outcome

Build **Trading Strategy Control Hub (TSCH)**, a responsive 24/7 web application deployed on Hostinger Ubuntu 24.04 VPS. It emulates the *function categories* seen in a demonstration of Phantom Control: overview, portfolio P&L, daily calendar, arm/strategy grouping, Best Hours, Best Setups, account management, user-defined position sizing, strategy scheduler and risk oversight. Use original UI, original code, original strategy algorithms and no proprietary vendor assets.

The system must support:

- `SIM`: fully working simulated broker adapter with seeded data, parameterized history and no real orders.
- `MT5_DEMO`: connect to an authorized MT5 demo terminal via official, documented interface; read account, trades, bars and positions; allow human-approved demo orders only after verifying risk, account type and commands; reconcile observed order states.
- `TRADINGVIEW_PAPER_MANUAL`: user uses TradingView's own Paper Trading UI; our app provides only independent manual journal entry or supported user export workflow if actually verified. Do NOT claim it can place or manage TradingView Paper Trading orders.
- `TRADINGVIEW_PERSONAL_MCP`: optional external, personal Claude Code/Claude connection for human-readable research; never for trading-engine data, automated trades, scheduled scraping or data retention.
- `LIVE_DISABLED`: reserved for a future separately approved and risk-reviewed release; cannot execute any live transaction in current version.

## Source-derived functionality and missing facts

Video shows ~150 s of Home/Stats, Installer, Strategies with grouping/on-off, Best Hours per session, Best Setups trade statistics and Add an Arm strategy/account/ticker/timeframe/sizing setup. It does NOT reveal algorithms, APIs, source code, authentication model or reliable financial outcomes. No claims about reproducible performance. Strategies are independent, original educational examples.

## Verify official platform facts first

You must consult current first-party documentation and write `docs/PLATFORM_CAPABILITY_MATRIX.md` with **verified, unverified and not-supported** labels. In particular:

- MT5 Build 6060 introduced official native MCP capability. MT5 Terminal MCP can expose orders, positions, history, testing and account tools; MetaEditor MCP provides development functions. Native endpoint normally listens locally (example `http://127.0.0.1:22346/mcp`) with an API key. MCP tool availability and permissions depend on actual installed build. See https://www.metatrader5.com/en/terminal/help/mcp_and_ai and `/configuration` and `/capabilities`.
- MetaTrader 5 runs on Ubuntu by Wine. Hostinger documents Ubuntu 24.04 with MetaTrader template and Ubuntu 24.04 with Desktop. Linux/Wine support does not guarantee stable runtime on every host or broker. Verify installed build and telemetry.
- Official TradingView MCP: `https://mcp.tradingview.com/mcp`, personal interactive research only. Per its Terms §3 and §27, do not use TradingView MCP, chart data, webhooks or alerts in automated trade decisions/orders, including a TradingView-to-MT5 webhook bot. Official MCP provides no general Paper Trading order interface. Never scrape undocumented endpoints.
- Official Python `MetaTrader5` package assumes access to a local terminal. Do not falsely promise a Linux-native wheel or a functioning Python API under Wine. Prefer MT5's native MCP + MQL5 EA, and test other adapters before use.

## Build requirements

### 1. Scaffolding and development quality

Use a monorepo:

```text
/
  apps/web               Next.js TypeScript UI
  services/api           FastAPI HTTP/WebSocket
  services/worker        analytics, reconciliation, jobs
  services/mt5-agent     host-side adapter, systemd service (not publicly reachable)
  packages/contracts     API schemas / generated TS clients
  packages/research      Python strategy/backtest library
  packages/risk          pure deterministic risk-policy library
  mt5/Experts            original MQL5 strategies / optional bridge
  infra/docker           Docker Compose, Caddy, DB and Redis
  infra/systemd          MT5 agent and terminal supervision examples
  docs                   threat model, SDK capability matrix, ops, testing
  tests                   unit, integration, security, end-to-end
  .env.example           placeholders only; no credentials
```

Use current supported stable versions pinned by lockfiles and documented. Use UV or Poetry for Python, Ruff/mypy/pytest, ESLint/TypeScript/Vitest/Playwright, Alembic for migrations. No third-party paid library unless necessary, listed with reason and budget.

### 2. Modules and pages

Functional navigation:

- **Dashboard**: demo equity/balance/margin, P&L (gross vs net), number of trades, wins/losses, drawdown, session heatmap and last sync.
- **Today**: broker feed status, scheduled strategies, generated signal flags, risk gates, alerts, events calendar without unlicensed data ingestion.
- **Accounts**: SIM / MT5 DEMO / TradingView manual journal clearly distinguished. DEMO account number + broker/server/name protected and partly masked.
- **Strategies / Arms**: strategy catalog, parameter editor, assign strategy to demo/sim accounts, group, symbol, timeframe, session, sizing, initial state `DISABLED`, individual pause, bulk pause, metadata/version, action acknowledgements.
- **Signals**: proposed BUY/SELL/HOLD from independent broker data, reason, timestamp, bar confirmation, score, stop/target and expiry; no automatic orders. **Approval queue** for optional demo execution; risk check independently executed.
- **Positions & Orders**: read observed broker orders/positions, fills, pending orders and journal. Never show a submitted order as filled without broker acknowledgment.
- **Stats**: daily/weekly/monthly/YTD, trade calendar, realized net/gross, swap/commission, PF, expectancy, R, win rate, drawdown, MTM unrealized; each computed correctly from actual fills.
- **Best Hours**: Asia/London/NY hour slices, time-zone selector, session/day DST, min sample gate, strategy/instrument/account filter and ranking based on out-of-sample net expectancy.
- **Best Setups**: strategy comparison, tested sample, costs, profit factor, max DD, risk per trade and robustness score; outlier warnings and rank provenance.
- **Backtesting**: deterministic independent broker-sourced replay, cost/slippage model, metrics, equity curve, walk-forward split and report export. Support MT5 native Strategy Tester through MCP only after verified.
- **Risk**: per-trade risk max, daily loss, drawdown lock, account/group caps, max spread, stale feed, minimum RR check if configured, kill switch and broker specs.
- **Trade Journal**: manual TradingView Paper trades tagged MANUAL; MT5 imports immutable; show source and reconciliation status; no synthetic broker confirmations.
- **Connections**: MT5 terminal status, MCP auth/feature flags, Wine health, broker demo type, independent personal TradingView instruction link, no TV order controls.
- **Audit / Settings**: immutable operator decisions, account actions, system errors, login events, alerts, local timezone and account risk profile.

### 3. Analytics math and accounting

Store immutable source records (account, broker, ticket/order id, deal id, strategy id, side, timestamps, symbol, volume, price, commission, swap, fee, profit, currency, raw payload hash). Model order-to-fill-to-position transitions, partial fills, round trips, reversals, broker netting/hedging, mark-to-market, and maker/taker fees if applicable. Avoid double counting.

Metrics:
- `net_realized = sum(realized_trade_profit + commission + swap + other_fees)` using broker sign conventions and reconciled amounts.
- `win_rate = wins / (wins + losses)` under a documented trade grouping, treat breakevens separately.
- `profit_factor = sum(wins) / abs(sum(losses))`, mark undefined when denominator zero.
- `expectancy = avg(trade_net_pnl)` and `expectancy_R` only if initial risk known.
- `max_drawdown = max peak-to-trough loss` on explicitly defined equity/balance sampled timeline.
- `risk_$ = equity * risk_pct / 100`, then validated symbol-unit-based sizing with account-currency conversion.

Use per-symbol `tick_size`, `tick_value`, `contract_size`, `min_lot`, `lot_step`, `stop_level`, `freeze_level`, `digits`, margin and broker execution constraints. XAUUSD varies across brokers. Prevent lookahead bias. Show unavailable metric as `N/A`; no invented values.

### 4. Approved original strategy library

Develop the following independent original strategies for backtests and SIM, plus MQL5 implementations only where appropriate:

1. EMA9/EMA21 crossover with EMA50/EMA200 trend filter and ATR(14) stop.
2. RSI(14) with Bollinger(20,2) reversion and regime filter.
3. VWAP trend pullback with spread and session gating.
4. Opening range breakout for London or New York, timezone aware.
5. MACD(12,26,9) with RSI confirmation and ATR stop.
6. Zero-order candle/trade observation collector.

Use explicit hypothesis, signal creation, position exit conditions, data-quality checks, transaction cost / overnight gap models, and configurable cool-down. Include M1, M5, M15, H1, H4 and D1 where legitimate data supports them. Use a holdout dataset and walk-forward tests. No claim of >65% win rate without independently verified results.

TradingView Pine scripts, if supplied, are visual aid scripts for the user and do not feed automatic execution. Do not attempt TV signal forwarding to the MT5 order API.

### 5. Approval, risk and command flow

Demo orders **must not** be entered by a general AI agent on its own. Human UI must show price/SL/TP, max-loss estimate, fill slippage sensitivity, broker account, symbol, requested volume, strategy version, risk check time, validity window and reason for entry. Every action enters a persisted, authenticated command state machine. All orders must pass deterministic and local broker risk checks again immediately before send. If the broker account becomes real, disconnect automatically / block commands. Use idempotency keys and reconcile broker orders after failures.

- Risk max 2% of equity *if user configures it*, configurable down; no assumption that 2% is safe or profitable.
- Simulated default limits, max daily loss, drawdown, volume, symbol whitelist and max concurrent exposure.
- No risk service = no new order. No broker quote = no new order. Unknown broker response = reconcile, not duplicate.
- All destructive or close/cancel actions have distinct confirmations. Pausing arm prevents new entries and does not close a position or remove existing stops.
- Live transition cannot be activated by flipping `IS_LIVE=true`; it requires a new release and separate security/readiness gate.

### 6. MT5 native MCP and Ubuntu integration

- Host OS Ubuntu 24.04 with Hostinger MetaTrader template (preferred) OR Ubuntu desktop plus official MetaTrader Wine install; choose only after checking host actual template and resources.
- Docker Compose runs Next.js, FastAPI, DB, Redis, worker, Caddy or front proxy; keep DB and Redis private. MT5 terminal runs OUTSIDE containers in the host graphical/Wine session by default.
- Enable MT5 native terminal MCP on loopback only, configure API key, restrict tool permissions (default no trading), and run its host-side connector with least privileges; keep MetaEditor MCP disabled unless needed.
- Implement host-side service/agent to connect to the local MCP endpoint and to the internal application command queue, never expose port 22346 to the internet or frontend.
- Verify exactly how MCP HTTP transport, auth, required headers, tool enumeration, run state, approval and response are handled in the installed MT5 build. Support safe token rotation and reconnection.
- Hostinger reboot persistence test: user desktop/Wine session, MT5 authenticated connection, broker feed, MCP enablement, agent, reverse proxy, app, queues and DB.
- Store timestamps UTC, display Asia/Kuala_Lumpur, and compute London/NY sessions in native IANA zones.

### 7. Security and operability

Secure SSH keys (disable root password SSH login), UFW restrict to SSH/80/443 (prefer SSH over VPN/allowlist), HTTPS via Caddy, environment separation, non-root containers, restrictive Docker network, encrypted offsite backups, secret rotation, external monitoring, rate limits, CSRF, MFA for web, sanitized logs, audit chain, reproducible migration and rollback. Avoid enabling public RDP; access graphical MT5 over an SSH tunnel/VPN or other securely restricted mechanism.

MT5 account credentials remain on host in secure storage and must not enter Claude prompts, Git, frontend, customer logs or `.mcp.json` committed to repo. `mt5-agent` stores only token references. Do not expose shell-capable MCP tools to browser requests. MT5 MCP authentication alone does not replace transaction-level user approval.

### 8. Implementation gates and deliverables

**Phase 1 (architecture/feasibility):** data model, threat model, official SDK capability matrix, screenshots/wireframes, file tree, working monorepo skeleton, SIM adapter, CI.

**Phase 2 (dashboard vertical slice):** real DB, auth, accounts, arms, SIM execution generator, P&L calendar, stats, command acknowledgements, tests and screenshots.

**Phase 3 (analytics/research):** real match/reconcile, Best Hours/Best Setups, XAUUSD candidate research, backtest and walk-forward reports, tests and data provenance.

**Phase 4 (MT5 DEMO bridge):** host-side connector, MCP tool discovery, Wine/MT5 health checks, broker account identification, read-only positions/deals ingestion, demo order approval workflow, full reconciliation; actual broker testing only when Hostinger and demo account exist.

**Phase 5 (risk and strategies):** MQL5 sample EAs if feasible, independent policy engine, limit tests, safe schedules, signal-only mode and explicit human demo approval.

**Phase 6 (Hostinger deployment):** Docker Compose, reverse proxy TLS, PostgreSQL backup/restore, sysd agent, dashboard accessibility, observability, security checks, runbook, reboot verification.

**Phase 7 (live readiness, NO live release):** risk review, controls evidence, segregation, security checklist, broker portability, document the change plan. Do not enable live execution.

## Definition of done

1. `docker compose` starts local app with one command and seeded SIM data; pages load and actions persist.
2. Unit/integration/e2e tests pass with actual command logs. SIM full lifecycle tested.
3. Dashboard accurately reports broker-sourced MT5 DEMO records when integration is available; without credentials, show `NOT CONNECTED`, not fake broker data.
4. A SIM signal can be approved and becomes a correctly reconciled SIM trade.
5. If an actual verified MT5 demo terminal is available, an explicitly human-approved low-risk demo order can be sent, detected in broker history, closed/handled by permitted user action, and reconciled; otherwise report untested.
6. TradingView research is only personally shown in a permitted interactive client. No TradingView market data is stored, scraped or used for trading decisions.
7. Kill-switch, stale connection, wrong account mode, duplicate order, missing SL and exceeded risk reliably BLOCK new demo orders.
8. MT5 MCP local endpoint cannot be reached from the public internet; tests or documented firewall inspection confirm.
9. Secure backups, restore rehearsal, audit log and reboot procedure documented.
10. Future real-broker change requires a separate feature and release approval.

## Engineering behavior

- Start coding after a short feasible plan. Keep changes small and build iteratively.
- If a required service, broker login, GUI, terminal or MCP is missing, implement a fully tested SIM/mocked adapter and clearly mark the real integration as not yet validated.
- Verify official docs; distinguish known supported functions from assumed syntax. Do not silently change third-party terms restrictions.
- No fabricated tool results, screenshots, pass rates, trades or strategy outcomes.
- At each checkpoint show files written, commands actually run, tests passed/failed, unsupported operations and next steps. Preserve all implementation state in repository docs so the project is restartable.
