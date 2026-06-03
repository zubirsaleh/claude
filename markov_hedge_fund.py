"""
Markov Chain Hedge Fund Strategy Simulator

Models market regimes as hidden Markov states and allocates a portfolio
accordingly, then back-tests the strategy against a simple buy-and-hold benchmark.

States (hidden):
    0 — Bull  : trending upward, low volatility
    1 — Bear  : trending downward, elevated volatility
    2 — Crisis: sharp drawdown, very high volatility

Usage:
    python markov_hedge_fund.py                # default run with synthetic data
    python markov_hedge_fund.py --seed 99      # reproducible alternative run
"""

import argparse
import random
import math
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Market regime parameters
# ---------------------------------------------------------------------------

@dataclass
class RegimeParams:
    name: str
    daily_mean: float    # expected daily log-return
    daily_std: float     # daily log-return std-dev


REGIMES: List[RegimeParams] = [
    RegimeParams("Bull",   daily_mean=0.0015, daily_std=0.007),   # stronger, tighter bull
    RegimeParams("Bear",   daily_mean=-0.0003, daily_std=0.016),
    RegimeParams("Crisis", daily_mean=-0.002,  daily_std=0.030),
]

# Transition matrix P[i][j] = prob of moving from regime i to regime j
# Long-bullish: Bull is very sticky; Bear/Crisis escape back to Bull quickly
TRANSITION: List[List[float]] = [
    [0.992, 0.006, 0.002],  # from Bull  — stays bull ~99% of days
    [0.15,  0.80,  0.05],   # from Bear  — 15% chance of recovery each day
    [0.05,  0.20,  0.75],   # from Crisis — escapes faster
]

# Portfolio equity allocation per detected regime (rest goes to cash/bonds)
REGIME_EQUITY_WEIGHT: List[float] = [0.90, 0.40, 0.10]

RISK_FREE_DAILY = 0.000025   # ~0.9 % annual


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_next_state(current: int, rng: random.Random) -> int:
    row = TRANSITION[current]
    r = rng.random()
    cumulative = 0.0
    for j, p in enumerate(row):
        cumulative += p
        if r < cumulative:
            return j
    return len(row) - 1


def _sample_return(regime: int, rng: random.Random) -> float:
    """Box-Muller normal sample."""
    u1, u2 = rng.random(), rng.random()
    z = math.sqrt(-2 * math.log(max(u1, 1e-12))) * math.cos(2 * math.pi * u2)
    p = REGIMES[regime]
    return p.daily_mean + p.daily_std * z


def _simple_moving_average(series: List[float], window: int) -> List[float]:
    out = []
    for i, _ in enumerate(series):
        start = max(0, i - window + 1)
        out.append(sum(series[start : i + 1]) / (i - start + 1))
    return out


# ---------------------------------------------------------------------------
# Regime detector (Viterbi over a rolling observation window)
# ---------------------------------------------------------------------------

class MarkovRegimeDetector:
    """
    Lightweight online regime detector.

    Uses a rolling Viterbi pass on observed returns to infer the most
    likely current regime.  The emission probability is computed as a
    Gaussian likelihood using each regime's parameters.
    """

    def __init__(self, window: int = 20):
        self.window = window
        self._history: List[float] = []
        self.current_regime: int = 0

    def update(self, daily_return: float) -> int:
        self._history.append(daily_return)
        if len(self._history) > self.window:
            self._history.pop(0)

        if len(self._history) < 3:
            return self.current_regime

        self.current_regime = self._viterbi(self._history)
        return self.current_regime

    # --- private ---

    @staticmethod
    def _gaussian_log_prob(x: float, mean: float, std: float) -> float:
        var = std * std
        return -0.5 * math.log(2 * math.pi * var) - (x - mean) ** 2 / (2 * var)

    def _emission_log_probs(self, obs: float) -> List[float]:
        return [
            self._gaussian_log_prob(obs, r.daily_mean, r.daily_std)
            for r in REGIMES
        ]

    def _viterbi(self, obs: List[float]) -> int:
        n_states = len(REGIMES)
        log_trans = [
            [math.log(max(p, 1e-12)) for p in row] for row in TRANSITION
        ]

        # Initialise
        delta = self._emission_log_probs(obs[0])

        for o in obs[1:]:
            emit = self._emission_log_probs(o)
            new_delta = []
            for j in range(n_states):
                best = max(delta[i] + log_trans[i][j] for i in range(n_states))
                new_delta.append(best + emit[j])
            delta = new_delta

        return delta.index(max(delta))


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@dataclass
class Portfolio:
    equity_value: float = 1.0
    cash_value: float = 0.0

    @property
    def total(self) -> float:
        return self.equity_value + self.cash_value

    def rebalance(self, equity_weight: float) -> None:
        total = self.total
        self.equity_value = total * equity_weight
        self.cash_value = total * (1.0 - equity_weight)

    def apply_returns(self, market_return: float) -> None:
        self.equity_value *= (1.0 + market_return)
        self.cash_value *= (1.0 + RISK_FREE_DAILY)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    strategy_values: List[float] = field(default_factory=list)
    benchmark_values: List[float] = field(default_factory=list)
    regimes: List[int] = field(default_factory=list)
    true_regimes: List[int] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)


def simulate(n_days: int = 1000, seed: int = 42) -> SimResult:
    rng = random.Random(seed)
    detector = MarkovRegimeDetector(window=20)

    portfolio = Portfolio(equity_value=1.0)
    benchmark = Portfolio(equity_value=1.0)

    result = SimResult()
    state = 0  # start in Bull

    for _ in range(n_days):
        state = _sample_next_state(state, rng)
        mkt_return = _sample_return(state, rng)

        detected = detector.update(mkt_return)
        eq_weight = REGIME_EQUITY_WEIGHT[detected]

        portfolio.rebalance(eq_weight)
        portfolio.apply_returns(mkt_return)

        # Benchmark: fully invested in equity
        benchmark.equity_value *= (1.0 + mkt_return)

        result.strategy_values.append(portfolio.total)
        result.benchmark_values.append(benchmark.total)
        result.regimes.append(detected)
        result.true_regimes.append(state)
        result.daily_returns.append(mkt_return)

    return result


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _drawdown(values: List[float]) -> float:
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _annualised_return(values: List[float]) -> float:
    total_return = values[-1] / values[0] - 1.0
    n_years = len(values) / 252
    return (1.0 + total_return) ** (1.0 / n_years) - 1.0


def _sharpe(values: List[float]) -> float:
    daily = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    excess = [r - RISK_FREE_DAILY for r in daily]
    if not excess:
        return 0.0
    mean_e = sum(excess) / len(excess)
    var = sum((x - mean_e) ** 2 for x in excess) / len(excess)
    std = math.sqrt(var) if var > 0 else 1e-12
    return mean_e / std * math.sqrt(252)


def _regime_accuracy(detected: List[int], true: List[int]) -> float:
    correct = sum(d == t for d, t in zip(detected, true))
    return correct / len(detected) if detected else 0.0


def print_report(result: SimResult) -> None:
    s = result.strategy_values
    b = result.benchmark_values

    strat_ret   = _annualised_return(s)
    bench_ret   = _annualised_return(b)
    strat_sharpe = _sharpe(s)
    bench_sharpe = _sharpe(b)
    strat_dd    = _drawdown(s)
    bench_dd    = _drawdown(b)
    accuracy    = _regime_accuracy(result.regimes, result.true_regimes)

    regime_counts = [result.regimes.count(i) for i in range(len(REGIMES))]
    total_days = len(result.regimes)

    print("=" * 58)
    print("  Markov Hedge Fund — Back-test Report")
    print("=" * 58)
    print(f"  Simulation days     : {total_days}  ({total_days/252:.1f} years)")
    print()
    print(f"  {'Metric':<22}  {'Strategy':>10}  {'Benchmark':>10}")
    print(f"  {'-'*22}  {'-'*10}  {'-'*10}")
    print(f"  {'Ann. Return':<22}  {strat_ret:>9.2%}  {bench_ret:>9.2%}")
    print(f"  {'Sharpe Ratio':<22}  {strat_sharpe:>10.2f}  {bench_sharpe:>10.2f}")
    print(f"  {'Max Drawdown':<22}  {strat_dd:>9.2%}  {bench_dd:>9.2%}")
    print(f"  {'Final Value ($1 start)':<22}  {s[-1]:>10.4f}  {b[-1]:>10.4f}")
    print()
    print(f"  Regime detection accuracy : {accuracy:.1%}")
    print()
    print("  Time spent in each detected regime:")
    for i, name in enumerate(r.name for r in REGIMES):
        pct = regime_counts[i] / total_days
        bar = "#" * int(pct * 30)
        print(f"    {name:<8} {pct:>6.1%}  {bar}")
    print("=" * 58)

    # Equity curve snapshot — simple ASCII plot
    _ascii_plot(
        [s, b],
        labels=["Strategy", "Benchmark"],
        title="Equity Curve (normalised)",
        height=10,
        width=58,
    )


def _ascii_plot(
    series_list: List[List[float]],
    labels: List[str],
    title: str,
    height: int = 10,
    width: int = 58,
) -> None:
    # Downsample to width
    n = len(series_list[0])
    step = max(1, n // width)
    sampled = [[s[i] for i in range(0, n, step)][:width] for s in series_list]

    all_vals = [v for s in sampled for v in s]
    lo, hi = min(all_vals), max(all_vals)
    span = hi - lo or 1.0

    chars = ["*", "o", "+", "x"]
    print()
    print(f"  {title}")
    for row in range(height - 1, -1, -1):
        line = "  "
        threshold_hi = lo + span * (row + 1) / height
        threshold_lo = lo + span * row / height
        for col in range(len(sampled[0])):
            cell = " "
            for si, s in enumerate(sampled):
                if threshold_lo <= s[col] < threshold_hi:
                    cell = chars[si % len(chars)]
                    break
            line += cell
        print(line)
    print(f"  {'':>{width}}  hi={hi:.3f}")
    legend = "  " + "  ".join(f"{chars[i]}={labels[i]}" for i in range(len(labels)))
    print(legend)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Markov Hedge Fund Simulator")
    parser.add_argument("--days", type=int, default=1000, help="Trading days to simulate (default 1000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    args = parser.parse_args()

    result = simulate(n_days=args.days, seed=args.seed)
    print_report(result)


if __name__ == "__main__":
    main()
