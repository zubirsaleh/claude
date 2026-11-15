# Architecture and Functional Requirements — V2

## A. Source-video boundary

The ~150-second Phantom Control recording shows management and analytics for pre-installed strategies: Home/Stats; strategy instances ('arms'); activate/deactivate; groups; session/Best Hours research; Best Setups performance comparison; Add Arm with ticker/timeframe/template/account/sizing/time filters; installer. It **does not** disclose actual proprietary entry/exit formulas, a usable NinjaTrader/MT5 API, backend implementation or verified profitability. Build original functionality only.

## B. Non-negotiable integration boundaries

1. **MT5 demo terminal** is the only broker-connected executor initially. MT5 native MCP and/or a first-party, documented MQL5 Expert Advisor can provide account state, approved order actions, trade history and backtests. Confirm permissions and capabilities for installed build. The official Python `MetaTrader5` library is oriented around a local terminal; avoid assuming a Linux-native wheel. Prefer native MT5 MCP / first-party MQL5 EA before Linux-Python hacks. Use no undocumented broker interface.
2. **TradingView** is a distinct *human research and manual paper trade* surface. The official MCP is a personal research tool, not a machine-trading feed. Official TradingView TOS §3/27 bar automated orders through its MCP, webhooks, alerts and data. The dashboard may display user-authored notes, user-provided manual paper-trade journal entries and ordinary links to TradingView. Do **not** ingest TradingView account positions through undocumented endpoints. Do **not** reproduce its UI or resell its data.
3. **SIM** is an internal simulated broker with deterministic market fixtures generated from independently licensed data. It allows full end-to-end tests with no platform logins.
4. **LIVE_DISABLED** is a compiled runtime capability gate that cannot be enabled by UI toggle/config string alone.

## C. Deployment topology

```text
Web browser, personal account (MFA)
                |
          HTTPS:443 / WSS
                |
       Caddy reverse proxy (TLS)
                |
   Docker Compose on Hostinger Ubuntu 24.04
    +-------------------------------+
    | Next.js user dashboard        |
    | Python FastAPI backend        |
    | PostgreSQL migrations/data    |
    | Redis queue/cache             |
    | Worker (strategy research)    |
    | SIM adapter + test harness    |
    +-------------------------------+
                |
   Authenticated internal API / durable commands
                |
  Host-side restricted MT5 connector (systemd)
                |
   127.0.0.1:22346/mcp (MT5 terminal MCP)
   127.0.0.1:22345/mcp (MetaEditor, optional)
                |
        Wine + MT5 demo session
                |
         Selected DEMO broker

Separate personal desktop/Claude session:
  TradingView official MCP -> human-readable research ONLY
  TradingView Paper Trading -> user manual trades ONLY
  (no connection into MT5 execution decision path)
```

- Host-side broker connector is recommended because an MT5 MCP bound to `127.0.0.1` on the VPS is not reachable from `127.0.0.1` inside a normal Docker container. Do **not** solve this by exposing MT5 MCP publicly. Instead, connector communicates with backend via localhost-only authenticated endpoint or restricted Unix-domain socket. Alternative secure topology must be threat-modeled and tested.
- Build MT5 connector as an independent adapter with machine/service account permissions, fixed per-user capability scopes, signed commands, acknowledgements, retries, reconciliation and circuit breaker. MCP server itself is not the risk engine.
- All workloads must recover cleanly across VPS reboot. Verify Wine display/session/terminal autostart, login, data feed, connection and internal MCP independently.

## D. Modular layers

### Frontend

- Next.js/React/TypeScript, dashboard desktop-first but mobile usable.
- Real-time stream with bounded reconnection and stale-state indicators; no direct browser-to-MT5 connection.
- Nav: Overview, Today, Accounts, Positions/Orders, Strategies/Arms, Signals & Approval Queue, Stats, Best Hours, Best Setups, Backtests, Risk Limits, Trade Journal, Connections, Audit, Settings.
- Clear mode banners: internal SIM / MT5 DEMO / TradingView Paper (MANUAL) / LIVE DISABLED.

### Domain API

- FastAPI + Pydantic strict validation + SQLAlchemy + Alembic + PostgreSQL.
- Postgres transaction + transactional outbox for commands/events, Redis for transient streams/queues only; immutable audit/events in Postgres.
- Typed interfaces: `BrokerAdapter`, `HistoricalMarketDataAdapter`, `ResearchAdapter`, `PersonalDisplayResearchProvider`, `OrderPolicy`, `RiskEngine`, `ApprovalWorkflow`.
- `TradingViewPersonalDisplayResearchProvider` is NOT a subtype of `HistoricalMarketDataAdapter` or `BrokerAdapter`; no shared data path to strategy execution.

### BrokerAdapter contract

- `get_identity() -> BrokerIdentity` [account number, server, demo/live, currency, permissions]
- `get_health() -> HealthStatus`
- `get_symbol_specs(symbol) -> SymbolSpecs`
- `get_candles(symbol, timeframe, range) -> MarketBars` [broker-sourced]
- `get_positions() -> Positions`
- `get_open_orders() -> Orders`
- `get_fills(cursor) -> FillEvents`
- `prepare_order(proposal) -> ValidatedOrder` [read-only]
- `submit_approved_demo_order(approved_order) -> BrokerReceipt` [requires risk + approval gates]
- `cancel_demo_order(...)`, `modify_demo_protection(...)`, `close_demo_position(...)` [each guarded, versioned and separately permitted]
- `reconcile() -> ReconciliationReport`
- SIM + MT5_DEMO implementations. No LIVE implementation shipped. No TradingView adapter for orders.

### Order and approval state machine

`DRAFT -> SIGNAL_ONLY -> RISK_CHECKED -> AWAITING_HUMAN_APPROVAL -> APPROVED(expiring) -> SUBMITTING -> ACKED / REJECTED / UNKNOWN -> RECONCILED`

- Risk rejects move to REJECTED. Expired approved orders cannot submit.
- On timeout, order state `UNKNOWN`, reconcile by broker order/deal identifiers before ANY retry; never blindly resubmit.
- Every command includes idempotency key, broker identity, symbol, generation time, expiration, quantity, SL, TP, source strategy version, approval actor, risk snapshot hash and account mode.
- No approval on browser click alone if session expired; require authenticated user action and replay-safe token.

## E. Statistics and Phantom-style research

### Overview/Stats

- Date filters, accounts, instrument, strategy, mode; realized gross/net, open P&L, daily total, transaction costs, count, wins/losses, expectancy, profit factor, max equity drawdown, consecutive wins/losses, trading days and trading calendar.
- Fee accounting, commissions, financing/swap, spread/slippage, account-currency conversions and instrument-specific contract size.
- R-multiple only where genuine initial stop and initial monetary risk were captured. Null otherwise; do not derive it from hindsight.
- Group by close timestamp vs entry timestamp consistently, explicitly label convention.

### Strategies / Arms

- Original template catalog. Each 'arm' binds demo account, symbol, timeframe, strategy version, parameter set, group and session schedule.
- Modes `DRAFT`, `RESEARCH`, `SIM_ENABLED`, `DEMO_SIGNAL_ONLY`, `DEMO_APPROVAL_REQUIRED`, `PAUSED`, `DISABLED`.
- `PAUSE NEW ENTRIES` is different from `CLOSE POSITION`; never conflate.
- Bulk start/pause only acts on eligible states and generates per-arm durable acknowledgments.

### Best Hours / Best Setups

- Breakdown by user-time, broker-time and exchange-session-time; zones: Asia/Kuala_Lumpur, Europe/London, America/New_York. Use DST-aware conversions.
- Every per-hour result shows net P&L, trade count, win rate, R expectation where valid, outlier sensitivity and confidence warning.
- Promote only candidate strategies with enough out-of-sample evidence; no guaranteed edge labels. Control for selection bias, multiple comparisons and changing market regime.
- Include optional conservative risk per unit; symbol specs and stopped-out loss are not assumed constant.

### Original XAUUSD strategies (research + SIM first)

- EMA(9/21) trend filter + EMA(50/200) context + ATR protective stop.
- RSI(14) and Bollinger(20,2) mean reversion, session/regime gate.
- VWAP pullback with bounded volatility and no look-ahead.
- London/NY opening range breakout based on independently licensed broker market data.
- MACD(12,26,9) and RSI confirmation + time-of-day filter.
- Zero-order observations collector.
- Each template includes a Pine Script reference indicator for **visual/manual analysis only**, and separately an MQL5 SIM EA or broker-based backtest implementation using broker-sourced data. Do not copy TradingView chart data into execution tests.
- Pine Script alerts must not be wired to MT5 order automation without written permission confirming this specific use.

## F. Risk engine

Risk controls are deterministic and run before any broker send, with server-side and MT5-side protections where feasible. Start with explicit default policy (adjustable, not broker-enforced facts):

- Per-order risk **max**: 2% of current account equity; optionally lower initial setting. User must configure values.
- Configurable daily realized loss, total drawdown, trailing drawdown, simultaneous positions, max notionals, symbol allowed, min stop distance, max spread, max slippage, stale quotes, session and cooldown.
- Overnight exposure, weekend / rollover swap avoidance and event blackouts configurable, not claimed inherent profits.
- Size: `volume = allowed_monetary_loss / (abs(entry - stop) / tick_size * tick_value_per_lot)`, only if broker tick value is correct in account currency and order size validated against min/max/step, stop/freeze levels and available margin. Prefer `OrderCalcProfit`/native platform calculation where possible; reject unsupported specs.
- Account ID, server and DEMO status must match both approval and just-before-submit snapshot.
- Broker disconnection = no new entries; account state stale = no new entries; repeated trade reject = circuit breaker; manual kill switch = no new entries. Stopping a strategy doesn't automatically flatten existing positions.
- Do not allow live broker credentials to be supplied to a DEMO execution adapter.

## G. Independent AI / MCP layer

- MT5 official MCP: deploy for *on-demand*, explicitly approved account research, history, strategy backtesting and restricted demo operations. Ask tool listing/permissions at runtime. Gate `trade_send_market_order`, `trade_send_pending_order`, `trade_modify_sl_tp`, `trade_close_single_position` and destructive file/shell tools. Default read-only in AI assistant.
- Native MT5 MCP may have tools for compilation, strategy tests, EA attachment and terminal management. Verify availability and terminal stability under Wine before enabling.
- TradingView official MCP: intended only in your **personal interactive Claude Code/Claude session** for readable answers; do not proxy it through publicly accessible dashboard. Never use a server-side scheduled agent to store/mine data or generate orders based on its content.
- Maintain clear source labels for analysis: `BROKER_MT5`, `SIMULATED`, `MANUAL_TRADE_JOURNAL`, `PERSONAL_TV_DISPLAY`. Never merge personal TradingView-derived results into execution feature vectors.

## H. Reliability / security / tests

- RBAC (single-user initially), MFA, audit log, request signing, CSRF protection, HTTPS, secure cookies, per-account secrets, no raw MT5 MCP token in frontend.
- Docker containers unprivileged, bind web application via reverse proxy, backups encrypted off-host, retention, recovery drill, host firewall and SSH key-only login, systemd process supervision.
- NTP/chrony, UTC, DST tests, broker-time / user-time conversion, timeouts, Rabbit? Do not introduce additional infrastructure without need.
- Test suite: unit, property-based for volume rounding, integration API/Postgres, simulated order lifecycle, end-to-end browser, security/replay, broker reconnect, MT5 mocked contract, explicit manual MT5 integration and Wine smoke test checklist.
- Include observability: service heartbeat, MT5 terminal uptime, authenticated MCP status, broker reconnects, stale quotes, signal latency, pending approvals, rejected orders, audit discrepancy and order reconciliation warnings.

## I. Migration to live broker

- New adapter/capability and isolated secrets; never simply replace `demo_account_number` in environment to go live.
- Require documented suitability/compliance, new UI and management approval workflow, operational readiness review, account-type discovery, trade sizing min/step, limit tests, kill-switch proof, disaster recovery and operator runbook.
- Audit signed go/no-go acceptance. Default release **does not include live execution capability**.
