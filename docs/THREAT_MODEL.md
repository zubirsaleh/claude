# Threat Model (Phase 1)

Scope: a single-operator, self-hosted control plane on one Hostinger Ubuntu 24.04 VPS, running a
Docker Compose stack plus a host-side MT5 terminal (Wine) and `mt5-agent`.

## Assets

1. Ability to place, modify or close orders on the MT5 demo account (and, in the future, any real account).
2. MT5 MCP API key, broker login, operator token, DB password.
3. Integrity of fills, order history and the audit trail.
4. Availability of risk controls (kill switch, stale-feed blocks).

## Trust boundaries

```
Internet ──443──▶ Caddy ──▶ web (Next.js) ──▶ api (FastAPI) ──▶ Postgres / Redis   [docker: backend net is internal]
                                               ▲
                              authenticated internal channel (Phase 4)
                                               │
                         mt5-agent (systemd, host) ──loopback──▶ MT5 terminal MCP :22346
```

## Threats and controls

| # | Threat | Control (status) |
|---|---|---|
| T1 | MT5 MCP port reachable from the internet, allowing remote trading | Agent refuses non-loopback URLs (**tested**). Compose never maps 22345/22346 (**tested**). The systemd unit restricts the agent to `IPAddressAllow=localhost`. UFW and an external scan are still required (**manual, Phase 6**). |
| T2 | An AI or MCP client places orders without a human | The agent calls only READ_ONLY tools. Trading and destructive tools are blocked even when annotations claim read-only (**tested**). App orders require operator approval, which expires (**tested**). |
| T3 | Order sent to the wrong account, or to a real account | Identity (broker, server, login, type, mode) is captured at proposal and re-checked at approval and immediately before send. The account must be DEMO (**tested**). No live adapter exists (**tested**). |
| T4 | Duplicate orders after a timeout or retry | Idempotency key per command. Atomic APPROVED→SUBMITTING claim. UNKNOWN can only be reconciled, never resubmitted (**tested**). |
| T5 | Trading on stale or missing data | Missing quote, spec, equity, positions or heartbeat makes the gate block. A quote or heartbeat older than the limit, or further in the future than the skew tolerance, blocks (**tested**). |
| T6 | Tampering with fills or audit history | Postgres triggers reject UPDATE and DELETE on `fills`, `order_events` and `audit_log` (**tested**). The audit log is hash-chained with a verify endpoint (**tested**). Encrypted off-host backups arrive in Phase 6. |
| T7 | Secret leakage | Secrets come from files (Docker secrets, mode 0640). `.env`, `.mcp.json`, `*.token` and `secrets/` are gitignored (**tested**). The MCP token is redacted from agent errors (**tested**). Logs never print tokens. |
| T8 | Unauthenticated write actions | All writes need the operator bearer token, compared in constant time. Writes are disabled (503) if no token is configured (**tested**). **Gap:** a single shared token, with no MFA or CSRF protection. Replaced by durable auth and MFA in Phase 2. |
| T9 | TradingView data entering decision logic (licence breach) | No TradingView adapter exists. A static test forbids TradingView data sources in V2 code (**tested**). The legacy Telegram bot is outside V2 and must not be wired in. |
| T10 | Container breakout or lateral movement | Non-root users, `read_only`, `cap_drop: ALL`, `no-new-privileges`, internal backend network. Only Caddy publishes ports (**running locally**). |
| T11 | API docs exposing attack surface | Caddy returns 404 for `/docs`, `/redoc` and `/openapi.json` (**verified in smoke test**). |

## Known gaps (tracked)

- Interim operator-token auth (Phase 2: user accounts, MFA, CSRF, session expiry, rate limits).
- No rate limiting at Caddy yet (stock Caddy lacks it; evaluate a plugin or the app layer in Phase 6).
- The SIM adapter's state is in-memory. Restarting the API loses SIM positions, though persisted fills remain. A durable SIM ledger is planned for Phase 2.
- The `mt5-agent` ↔ API channel is not designed yet (Phase 4: Unix socket or loopback HTTP with signed commands).
- Day-loss limits use a UTC day for SIM. Broker-session day boundaries arrive in Phase 3.
