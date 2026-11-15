# Phase 1 Report: Scaffold, SIM Vertical Slice, Feasibility

Date: 2026-11-15. Spec: `docs/spec/v2/` (V2 supersedes the NinjaTrader design).

## Built

| Area | What exists | Where |
|---|---|---|
| Monorepo | uv workspace (Python 3.12+), Next.js app, infra, docs | `pyproject.toml`, `uv.lock` |
| Contracts | Pydantic domain models (Decimal money, UTC-aware times), `BrokerAdapter` protocol, order state machine | `packages/contracts` |
| Risk | Pure position sizing (floors to volume step, rejects below minimum, hard 2% ceiling) and a fail-closed pre-trade gate with 20+ checks and a deterministic snapshot hash | `packages/risk` |
| SIM broker | Deterministic synthetic prices and candles, idempotent fills, close with realised P&L and commission, fault injection (timeout-after-fill, timeout-before-placement, reject), disconnect and stale-heartbeat switches | `services/api/src/tsch_api/brokers/sim.py` |
| API | FastAPI: modes, connections, accounts (masked), strategies, the order pipeline (propose → approve → submit → reconcile), fills, hash-chained audit and verify, kill switch, SIM close with explicit confirmation | `services/api` |
| DB | SQLAlchemy 2 models plus Alembic `0001`, with Postgres append-only triggers on fills, order events and audit | `services/api/alembic` |
| mt5-agent | Loopback-only MCP client (JSON + SSE, session id), token from file with redaction, conservative tool classifier, READ_ONLY-only `call_tool`, `discover` CLI | `services/mt5-agent` |
| Worker | Heartbeat stub | `services/worker` |
| Web | Server-rendered overview: mode banner, connection states (MT5 = NOT CONNECTED), masked accounts, recent commands, catalog (no performance figures) | `apps/web` |
| Infra | Compose (Postgres, Redis, API, worker, web, Caddy). Only Caddy publishes ports. Hardened containers, Docker secrets, hardened systemd unit for the agent | `infra/` |
| CI | ruff, mypy --strict, pytest on SQLite + Postgres, migration round-trip and drift check, OpenAPI drift, web audit, typecheck, tests and build, compose validation | `.github/workflows/tsch-ci.yml` |
| Docs | Capability matrix, threat model, source boundaries, data model, this report | `docs/` |

## Commands run and results (this session)

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy` (strict, 24 files) | No issues |
| `TSCH_TEST_DATABASE_URL=… uv run pytest -q` | **149 passed, 2 skipped** (skips are intentional: one PG-only test on SQLite, one wall-clock test on PG) |
| `alembic upgrade head → downgrade base → upgrade head → check` (PostgreSQL 16) | All succeeded; no drift |
| `tsch-export-openapi` diff | Up to date (16 paths) |
| `apps/web`: `npm test` / `npm run typecheck` / `npm run build` / `npm audit` | 6 passed / ok / ok / 0 vulnerabilities |
| `docker compose up -d --wait` (images built locally) | All 6 services up; postgres, redis and api healthy |
| `infra/scripts/smoke-sim.sh` through Caddy | Full lifecycle PROPOSED → APPROVED → ACKED → RECONCILED/FILLED; resubmit 409; close books an OUT fill (−$0.20 spread + −$0.035 commission per side at 0.01 lot); kill switch blocks; audit chain ok; `/docs` 404; unauthenticated write 401 |
| Playwright screenshots at 1280 px and 390 px | No horizontal overflow (`docs/screenshots/`) |

### Defects found and fixed during Phase 1

1. **Quote freshness false-negative with a real clock.** "now" was read before the quote was fetched, so the quote age came out slightly negative and the gate blocked every order. The fake-clock tests could not see it; the end-to-end smoke test caught it. Fixed by reading "now" after fetching and adding an explicit clock-skew tolerance. Regression tests were added: a unit test for skew and an API test on a real wall clock.
2. Compose: Redis couldn't change user under `cap_drop: ALL`; the venv shebang paths differed between build and runtime stages; bind-mounted secrets weren't readable by the non-root API user. All fixed.
3. Next.js 15.5.4 had critical advisories; pinned 16.4.3 / React 19.3.1. vitest's dependency tree carried advisories and broke npm 10's resolver, so web unit tests now use the built-in `node:test`.

## Not verified (needs your VPS, broker or network access)

- **Every MT5 native MCP fact** (build 6060, port 22346, auth header, tool names, loopback binding, permission modes). The first-party docs could not be fetched because this environment's network policy blocks metatrader5.com, metaquotes.com and tradingview.com. See `PLATFORM_CAPABILITY_MATRIX.md`.
- MT5 under Wine on the Hostinger "Ubuntu 24.04 with MetaTrader" template, including reboot persistence.
- Compose on the Hostinger VPS, TLS issuance for your domain, UFW, and an external port scan.
- The image build here needed this sandbox's proxy CA, passed as an optional BuildKit secret (`extra_ca`). Normal hosts don't need it.

## Next steps

1. **You:** provision the VPS, run `tsch-mt5-agent discover` against the real terminal, and share the tool inventory output. It never prints the token. That lets the capability matrix move from CLAIMED to VERIFIED.
2. **Phase 2:** durable user auth with MFA and CSRF; arms CRUD with per-arm durable commands; the remaining pages (Stats, Today, Strategies, Add Arm, Approval Queue, Positions, Journal, Risk, Connections, Audit); a durable SIM ledger; a labelled synthetic data generator.
3. **Phase 3:** analytics math (round trips, netting/hedging, MTM), DST-aware Best Hours, Best Setups, backtests and walk-forward on broker or synthetic data only.
