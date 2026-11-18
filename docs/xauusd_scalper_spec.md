# XAUUSD 1M Scalper — Specification

Status: **Phase 1 (safety foundation) built — awaiting approval for Phase 2 (data & research).**

## Fixed inputs (from account owner)

| Item | Value |
|------|-------|
| Instrument | XAUUSD only (OANDA `XAU_USD`) |
| Timeframe | 1M execution; 5M/15M/1H context only |
| Sessions | Asia, London, New York (all) |
| Chart / signals | TradingView (`OANDA:XAUUSD` feed, so chart = broker prices) |
| Broker | OANDA **practice** account, v20 REST API |
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

## Architecture

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
2. **Data & cost model** — download multi-year XAUUSD bid/ask tick data (Dukascopy),
   build 1M bid/ask bars, cross-check against OANDA candles, and measure the spread
   distribution per session. *Needs network access to `datafeed.dukascopy.com` and an OANDA practice token.*
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
are its filled-in values: XAUUSD, 1M, all sessions, OANDA practice via v20, USD 5,000,
0.4 lot fixed, USD 400 per-trade cut-loss, USD 1,200 daily stop, USD 40,000 paper account,
15% max drawdown, Python.
