# Trading Strategy Control Hub (TSCH)

Self-hosted control plane for strategy research and **human-approved** demo trading.

- **SIM:** working now. Deterministic simulated broker; all prices are synthetic.
- **MT5_DEMO:** not connected. The host-side `mt5-agent` is scaffolded (read-only discovery). It hasn't been tested against a real terminal yet.
- **TRADINGVIEW_PAPER_MANUAL:** manual only. TradingView data never enters this app.
- **LIVE_DISABLED:** live execution is not compiled in.

Status and evidence: `docs/PHASE1_REPORT.md`. Spec: `docs/spec/v2/`.

## Quick start (local)

```bash
uv sync                                   # Python workspace (3.12+)
uv run pytest                             # unit + integration (SQLite)
infra/scripts/dev-secrets.sh              # creates gitignored secrets/
TSCH_SITE_ADDRESS=":80" docker compose -f infra/docker/docker-compose.yml up -d --build --wait
infra/scripts/smoke-sim.sh                # end-to-end SIM lifecycle through the proxy
open http://localhost/
```

Write actions need `Authorization: Bearer $(cat secrets/operator_token)`. This is interim, single-operator auth, replaced in Phase 2.

Run the Postgres-backed tests with `TSCH_TEST_DATABASE_URL=postgresql+psycopg://…`. That database is wiped on every run.

## Layout

```
apps/web               Next.js overview UI
services/api           FastAPI, SQLAlchemy, Alembic, SIM broker, order pipeline
services/worker        background jobs (Phase 1: heartbeat)
services/mt5-agent     host-side loopback MCP connector (systemd, never in Docker)
packages/contracts     domain models, BrokerAdapter protocol, order state machine, openapi.json
packages/risk          pure sizing + fail-closed risk gate
infra/                 docker compose, Caddy, systemd, scripts
docs/                  capability matrix, threat model, data model, reports, spec pack
```

## Legacy

`bot/`, `mcp_server/`, `trading/` and `main.py` are the earlier TradingView → Claude → Telegram bot. It uses unofficial TradingView scrapers and is **outside V2 policy** (see `docs/SOURCE_BOUNDARIES.md`). It is kept unchanged and isolated, and must not be connected to TSCH.
