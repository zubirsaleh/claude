# Backtest report: MTF Pullback Buy Setup on XAU/USD (H1)

**Run date:** 2026-10-13
**Test window:** 2026-03-27 → 2026-10-13 (200 calendar days, 3,084 H1 bars)
**Engine:** `pinescript/backtest_mtf_pullback.py`, a Python port of `mtf_pullback_buy_strategy.pine` with the same default inputs

## Data and assumptions

| Item | Value |
|---|---|
| Instrument | COMEX gold futures, continuous front month (Yahoo `GC=F`), used as a stand-in for spot XAU/USD. TradingView, OANDA and Dukascopy spot feeds could not be reached from the test environment. Futures trade a few dollars above spot and roll every two months, but the H1 structure is almost the same. |
| Warm-up | About 1 year of extra H1 history before the window, so EMA 200 and the daily EMAs are fully formed |
| Entry | Close of the signal candle (`process_orders_on_close = true`) |
| Exit | Stop = pullback low − 0.2 × ATR(14). Target = swing high. When both are hit in the same bar, the backtest follows TradingView's rule: price goes first to whichever extreme is nearer the open. |
| Sizing / costs | 10 % of equity per trade, 0.05 % commission per side, one position at a time |

## Results: 200 days, default settings

| Metric | Value |
|---|---|
| Buy flags | **1** |
| Trades | 1 |
| Wins / losses | 0 / 1 |
| **Win rate** | **0 %** |
| Net result | −1.0 R (−0.05 % of equity at 10 % sizing) |

| Entry (UTC) | Candle | Entry | Stop | Target | Result |
|---|---|---|---|---|---|
| 2026-08-18 16:00 | Inv. Hammer | 4419.0 | 4403.4 | 4493.1 | SL hit 3 h later, −1.0 R |

**Why so few signals:** gold fell over the window (4447 → 4208). The daily EMA 8 > EMA 21 filter was true on only 23.5 % of bars. All 7 conditions lined up just once in 3,084 bars.

| Condition | % of bars where it was true |
|---|---|
| 1 Daily EMA 8 > 21 | 23.5 % |
| 2 H1 EMA 50 > 200 | 38.0 % |
| 3 RSI(6) ≤ 20 (last 4 bars) | 11.3 % |
| 4 Retracement 50–100 % | 24.3 % |
| 5 Bullish candle | 14.9 % |
| 6 Touch EMA / trendline | 55.3 % |
| 7 RR ≥ 1.5 | 60.0 % |

23 bars met **6 of 7** conditions. The condition that blocked them most often was the confirmation candle (11 bars), followed by the daily trend (7), RSI (3) and retracement (2).

## A larger sample: same settings over the full history (2024-12-12 → 2026-10-13)

One trade is too few to judge a win rate, so the same rules were also run over ~22 months.

| Metric | Value |
|---|---|
| Trades | 18 |
| Wins / losses | 6 / 12 |
| **Win rate** | **33.3 %** |
| Average result per trade | **+0.32 R** |
| Profit factor | 1.11 |
| Max drawdown | −0.29 % of equity (at 10 % sizing) |

Winners averaged about +3 R, because the target is the prior swing high. So the strategy can still be slightly profitable while losing two trades out of three.

## Sensitivity (200-day window unless noted)

| Variant | Trades | Win rate | Avg R | Profit factor |
|---|---|---|---|---|
| Default | 1 | 0 % | −1.00 | 0.00 |
| RSI oversold within 6 bars | 1 | 0 % | −1.00 | 0.00 |
| Touch tolerance 0.3 % | 1 | 0 % | −1.00 | 0.00 |
| Retracement ≥ 38.2 % | 1 | 0 % | −1.00 | 0.00 |
| RSI ≤ 30 | 2 | 0 % | −1.00 | 0.00 |
| Relaxed combo (RSI ≤ 30, 6-bar look-back, 0.3 % touch) | 3 | 33.3 % | −0.11 | 1.17 |
| Relaxed combo, full history | 50 | 30.0 % | −0.07 | 0.84 |
| Trade on 6 of 7 conditions (hypothetical) | 14 | 28.6 % | +0.70 | 1.48 |

## Conclusions

1. **Over the requested 200 days the strategy took one trade, and it lost. The win rate is 0 %, but one trade tells you almost nothing statistically.** The main cause is the market regime: gold spent most of the window in a daily downtrend, and condition 1 correctly kept the strategy out.
2. Over ~22 months the default rules won **33 %** of trades with a small positive expectancy (**+0.32 R per trade**, PF 1.11). That's 18 trades, which is still a small sample.
3. Loosening the filters adds trades but doesn't raise the win rate (30 %), and turns expectancy negative. The strict default filters are doing useful work.
4. Expect a low win rate with large winners. Position sizing and patience matter more than how often trades hit.

## Caveats

- The data is futures, not spot, and it is a Python port, not TradingView's own Strategy Tester. Exact bar timing, tie-breaking for swing highs and daily-session boundaries can differ slightly. Confirm in TradingView: chart **OANDA:XAUUSD, 1h**, open **Strategy Tester**, set the date range to the last 200 days.
- No slippage or spread was modelled beyond 0.05 % commission.
- Past performance does not predict future results.
