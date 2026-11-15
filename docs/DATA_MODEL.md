# Data Model (migration `0001_initial_schema`)

All timestamps are `timestamptz` in UTC. Money, prices and volumes are `NUMERIC(28,10)`, held as Python `Decimal`.

| Table | Purpose | Mutability |
|---|---|---|
| `accounts` | One row per broker account per mode. Stores the login **masked** plus a SHA-256 hash, never the raw login. | mutable |
| `strategies` | Strategy catalog `(key, version)`, default params, `implemented` flag | mutable |
| `arms` | Strategy × account × symbol × timeframe × group × session. `state` defaults to `DISABLED` (Phase 2 UI). | mutable |
| `order_commands` | One command per proposal: state, idempotency key, identity snapshot, risk snapshot hash and reasons, estimated loss at SL, approval and expiry, broker ids, outcome, optimistic `version` | mutable (state machine only) |
| `order_events` | Every state transition with actor and detail | **append-only** (trigger) |
| `fills` | Raw broker deals with commission, swap, fee, profit and currency, plus a payload hash. Unique on `(account_id, deal_id)` and on `payload_hash`. | **append-only** (trigger) |
| `audit_log` | Operator and system actions, hash-chained (`prev_hash` → `hash`) | **append-only** (trigger) |
| `system_state` | Kill switch, fill cursors, day-start and peak equity trackers | mutable |

## Order state machine

```
DRAFT ─▶ RISK_CHECKED ─▶ AWAITING_HUMAN_APPROVAL ─▶ APPROVED(expiring) ─▶ SUBMITTING ─▶ ACKED ─▶ RECONCILED
  │                              │                     │                    │  └──▶ UNKNOWN ─▶ (ACKED|RECONCILED)
  └─▶ REJECTED ◀─────────────────┴──── EXPIRED/CANCELLED ┘                    └──▶ REJECTED
```

- The risk gate runs at **proposal**, at **approval**, and **immediately before send** (after the atomic claim).
- `UNKNOWN` is resolved only by looking up the idempotency key at the broker. It can never go back to `SUBMITTING`.
- A stale `SUBMITTING` (process crash) is moved to `UNKNOWN` by reconcile, then resolved the same way.
