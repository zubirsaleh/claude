# XAUUSD 1M Scalper — Specification

Status: **Phase 2 in progress — data layer built; live TradingView collection pending tvdatafeed install.**

## Fixed inputs (from account owner)

| Item | Value |
|------|-------|
| Instrument | XAUUSD only (OANDA `XAU_USD`) |
| Timeframe | 1M execution; 5M/15M/1H context only |
| Sessions | Asia, London, New York (all) |
| Chart / signals | TradingView (`OANDA:XAUUSD` feed, so chart = broker prices) |
| Broker | **TradingView Paper Trading, executed manually** from Telegram alerts (owner choice B) |
| Account | USD 40,000 (paper) — sized so USD 400 per trade = 1% |
| Position size | **0.4 lot fixed = 40 oz = 40 units** → USD 40 per USD 1.00 move |
| Cut-loss per trade | **USD 400** → stop at most USD 10.00 from entry |
| Daily stop | **3 full losses = USD 1,200**, then locked until next trading day |
| Max drawdown | 15% from equity peak → kill switch, manual restart only |
| Internal clock | UTC; trading day rolls at 17:00 New York |

## Assumptions needing owner confirmation

| Assumption | Value | Why |
|---|---|---|
| Max consecutive losses | 4 → pause until next session | Limits tilt / regime-mismatch damage |
| Max trades/day | 20 | Prevents overtrading on noise |
| Max spread | USD 0.60 | Placeholder until replaced by measured OANDA session medians |
| Stale quote | > 5 s → no trade | 1M scalping needs fresh prices |
| News blackout | ±15 min around high-impact USD events | NFP, CPI, FOMC, PCE |

## Session clock (DST-aware)

| Label | Definition | Entries |
|---|---|---|
| ASIA | 18:05 NY → 08:00 London | allowed |
| LONDON | 08:00–17:00 London, outside NY hours | allowed |
| OVERLAP | London and NY both open | allowed |
| NEW_YORK | 08:00–16:55 NY, after London close | allowed |
| ROLLOVER | 16:55–18:05 NY (daily break, wide spreads) | **blocked** |
| CLOSED | Fri 16:55 NY → Sun 18:05 NY | **blocked** |

No new entries after Friday 16:00 NY.

## Architecture (option B — manual execution)

```
TradingView 1M bars ──► signal (none enabled until validated)
                              │
                              ▼
                      RiskEngine (same hard limits)
                              │ allowed
                              ▼
            Telegram alert #id (valid 2 min) ──► owner executes in TV Paper Trading
                              ▲                       │
   /taken /skip /closed ──────┴───── shadow ledger ◄──┘  stop/target hits seen on 1M bars
                                                       (both touched in one bar ⇒ stop)
```

- `scalper/manual_desk.py` holds the shadow ledger, equity and daily P&L; `bot/scalper_commands.py`
  adds `/taken /skip /closed /status /kill /resume` and a 60 s bar-monitor job.
- Trading commands require `TELEGRAM_ALLOWED_USERS`; an empty allowlist denies them.
- Spread is not in TradingView bars: `ASSUMED_SPREAD_USD = 0.35` until measured.
- `/kill` blocks alerts and tells the owner to close all positions in TradingView by hand.

### Original automated design (OANDA, kept for later)

```
Signals (Python, Pine mirror for charting)  ──suggest──►  Executor
                                                            │ fresh quote, equity, positions from OANDA
                                                            ▼
                                                      RiskEngine (deterministic, persisted state)
                                                            │ allowed?
                                                            ▼
                                                      OANDA v20 market order + stop-loss on fill
                                                            │
                                                      Journal (append-only JSONL)
```

- No AI model sits in the order path. Claude may analyse and suggest only.
- Every order must carry a broker-side stop-loss.
- The kill switch is checked before every order, persists across restarts, and closes all positions.
- Fail closed: any broker error, stale/invalid quote or exception means no order.

## Phase plan (approval required at each gate)

1. **Safety foundation** ✅ — `scalper/settings.py`, `sessions.py`, `risk.py`,
   `broker_oanda.py`, `executor.py`, `journal.py`; tests in `tests/`.
2. **Data & cost model** (owner choice: TradingView only, via the repo's TradingView fetcher/MCP)
   — `scalper/data.py` (UTC normalisation, monthly bar store, quality report) and
   `scripts/collect_xauusd.py` ✅. Limits of this choice:
   - TradingView returns ≤ 5,000 1M bars (~3.5 trading days) per request, so history must be
     **accumulated** by running the collector at least every 2 days. ~3 months of collection
     is needed before a first walk-forward split; ≥ 300 out-of-sample trades before any verdict.
   - `OANDA:XAUUSD` bars on TradingView are bid-based OHLC with tick volume and **no spread**.
     Costs are therefore an explicit assumption (default USD 0.35 spread + USD 0.10 slippage
     per trade) stress-tested at 1.5× and 2×, then replaced by spreads measured in paper trading.
3. **Regime classifier** — TREND / RANGE / VOLATILE-CHOP / NEWS-SHOCK; misclassification report.
4. **Candidate strategies** — Asian-range breakout, London/NY open momentum,
   session-VWAP mean reversion, liquidity sweep reversal, HTF-trend EMA pullback.
   Walk-forward, 1.5×/2× cost stress, random-entry benchmark, deflated Sharpe, ≥300 OOS trades.
   Zero survivors is an acceptable outcome.
5. **Paper trading** — live loop on OANDA practice, Telegram alerts, `/kill` command,
   position reconciliation, ≥4 weeks across all sessions.
6. **Nightly review** — report only; never changes code, parameters or limits.

## Engineering prompt (filled in)

The full engineering prompt is kept in the conversation that produced this spec. These
are its filled-in values: XAUUSD, 1M, all sessions, OANDA practice via v20,
0.4 lot fixed, USD 400 per-trade cut-loss, USD 1,200 daily stop, USD 40,000 paper account,
15% max drawdown, Python.

## Data collection

TradingView returns ~5,000 1M bars (~3.5 trading days) per download, so a gap of more than
~2 days is lost permanently. Collection runs in two places:

1. **Cloud (primary):** scheduled task "XAUUSD 1M daily data collection", daily 03:47 UTC.
   It commits `data/xauusd_m1/*.csv` to branch `ccr-9432a21d-5y2xfh` and push-notifies a summary.
2. **Owner's machine (backup):** keeps its own local store; do not push it (avoids CSV merge conflicts).

   ```bash
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
   .venv/bin/python scripts/collect_xauusd.py --store data/xauusd_m1_local
   ```
   - Linux/macOS cron (daily 15:17 local): `17 15 * * * cd /path/to/claude && .venv/bin/python scripts/collect_xauusd.py --store data/xauusd_m1_local >> logs/collect.log 2>&1`
   - Windows: Task Scheduler → Daily → Program `C:\path\to\claude\.venv\Scripts\python.exe`,
     arguments `scripts\collect_xauusd.py --store data\xauusd_m1_local`, start in `C:\path\to\claude`.

The two stores can be merged later (`BarStore.merge` is idempotent) to fill any gap in the cloud copy.
