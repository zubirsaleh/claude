# CLAUDE.md

Guidance for AI assistants (Claude and others) working in this repository. **Read this first.**

## Repository overview

**Repo:** `zubirsaleh/claude`
**Product:** Trading Strategy Control Hub (TSCH). A self-hosted control plane for strategy
research and human-approved MT5 **demo** trading, deployed to a Hostinger Ubuntu 24.04 VPS.
The spec is `docs/spec/v2/` (V2 supersedes all earlier NinjaTrader designs). Current status is in
`docs/PHASE1_REPORT.md`.

## Non-negotiable rules (V2 policy, full text in `docs/spec/v2/CLAUDE_V2_POLICY.md`)

- Modes: `SIM` (default), `MT5_DEMO`, `TRADINGVIEW_PAPER_MANUAL`, `LIVE_DISABLED`. Live execution is
  not compiled in. Never add a live adapter or a config flag that enables live trading.
- **TradingView never feeds order logic, signals, research, backtests or stored data.** The official
  TradingView MCP is for the user's personal interactive research only. `tests/security/test_boundaries.py`
  enforces this for V2 code.
- MT5 is the only intended demo execution backend, through the host-side `mt5-agent` on
  **loopback only**. Never expose MCP ports 22345/22346, and never bind MT5 MCP to `0.0.0.0`.
- Every order needs explicit human approval with an expiry. The deterministic risk gate runs at
  proposal, at approval, and immediately before send. It fails closed on stale or missing data, an
  account identity change, a non-DEMO account, the kill switch, or a risk-engine error. AI is never the sole authoriser.
- Unknown submit outcomes are reconciled by idempotency key and **never** resubmitted.
- The 2% per-trade risk is a hard ceiling, not a recommendation. Size with broker tick size, tick value and
  volume step. Never assume XAUUSD specs across brokers.
- Fills, order events and the audit log are immutable. Show missing metrics as `N/A`; never
  invent values, trades, win rates or performance claims. A backtest is a hypothesis.
- Store timestamps as UTC; display defaults to `Asia/Kuala_Lumpur`; sessions use IANA zones with DST handling.
- Never commit `.env`, `.mcp.json`, tokens, `secrets/`, credentials or cookies. Never put broker
  passwords or MCP tokens in prompts, logs or Git.
- Before using any MCP tool, list the tools and check permissions. Avoid trading, shell and file tools unless explicitly required.
- Label platform facts VERIFIED, CLAIMED or UNVERIFIED (`docs/PLATFORM_CAPABILITY_MATRIX.md`).
  Don't claim an integration works until it has been tested end to end.

## Project structure

```
apps/web               Next.js 16 / React 19 / TypeScript (server components)
services/api           FastAPI + SQLAlchemy 2 + Alembic; SIM broker; order pipeline
services/worker        background jobs
services/mt5-agent     host-side loopback MCP connector (systemd, not Docker)
packages/contracts     domain models, BrokerAdapter protocol, order state machine, openapi.json
packages/risk          pure deterministic sizing + risk gate
infra/docker           compose, Dockerfiles, Caddy
infra/systemd          mt5-agent unit
infra/scripts          dev-secrets.sh, smoke-sim.sh
tests/{unit,integration,security}
docs/                  capability matrix, threat model, data model, phase reports, spec pack
```

Legacy, outside V2 policy, and not to be connected to TSCH: `bot/`, `mcp_server/`, `trading/`,
`main.py`, `config.py`, `markov_hedge_fund.py`, `requirements.txt`. This is the earlier
TradingView → Claude → Telegram bot, which uses unofficial TradingView scrapers. See `docs/SOURCE_BOUNDARIES.md`.

## Common commands

| Task | Command |
|------|---------|
| Install Python deps | `uv sync` |
| Lint / types | `uv run ruff check .` / `uv run mypy` |
| Tests (SQLite) | `uv run pytest` |
| Tests (+PostgreSQL) | `TSCH_TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest` (wipes that DB) |
| Migrations | `cd services/api && uv run alembic upgrade head` / `alembic check` |
| New migration | `cd services/api && uv run alembic revision --autogenerate -m "…"` |
| Regenerate OpenAPI | `uv run tsch-export-openapi` (CI fails on drift) |
| Web | `cd apps/web && npm ci && npm test && npm run typecheck && npm run build` |
| Full stack | `infra/scripts/dev-secrets.sh && TSCH_SITE_ADDRESS=":80" docker compose -f infra/docker/docker-compose.yml up -d --build --wait` |
| E2E smoke | `infra/scripts/smoke-sim.sh` |
| MT5 tool inventory (on VPS) | `TSCH_MT5_MCP_TOKEN_FILE=… tsch-mt5-agent discover` |

## Code conventions

- Python 3.12+, uv workspace, Ruff (line length 100, rules E,F,I,B,UP,S,DTZ), mypy `--strict`.
- Money, prices and volumes are `Decimal`, never float. Datetimes are timezone-aware UTC (`DTZ` rule).
- Pure domain logic lives in `packages/` with no I/O. Adapters and persistence live in `services/`.
- Tests go in `tests/`, named `test_*.py`. API tests run on both SQLite and PostgreSQL through the `harness` fixture.
- TypeScript strict, with `noUncheckedIndexedAccess`. Web unit tests use `node:test` (`lib/*.test.ts`).
- Pin exact versions. New npm or Python dependencies must be at least two weeks old and pass `npm audit`.

## Git workflow

- Primary branch `main`. Feature branches `<area>/<short-description>`; AI branches `claude/<slug>`.
- Commit messages are imperative, present tense, ≤ 72 characters.
- Open a PR for every change. Don't push directly to `main`, and don't open PRs unless asked.

## AI assistant guidelines

- Prefer editing existing files. No speculative abstractions. Comment only when the *why* is non-obvious.
- Security first (OWASP Top 10). No hard-coded secrets. Ask before destructive git operations.
- Run lint, types and tests after non-trivial changes, and report the actual results.
- After each milestone, report: features built, files changed, tests run with results, unresolved
  prerequisites, and next steps. Keep `docs/` current so the project can be restarted from the repo.

## Architecture decisions

> **2026-11-15 — V2: TSCH replaces the bot as the product.** Host-side `mt5-agent` talks to the MT5
> MCP over loopback. The Docker stack never reaches MT5 directly. The SIM adapter carries the full
> order lifecycle until a real terminal is verified.

> **2026-11-15 — Interim auth.** Phase 1 uses a single operator bearer token from a secret file;
> writes are disabled when it is absent. Phase 2 replaces it with user auth + MFA + CSRF.

> **2026-06-05 (legacy)** — The Telegram bot used tvdatafeed and tradingview-ta. Superseded by V2;
> not permitted in TSCH.
