"""
Markov Hedge Fund Method
========================
Quantitative trading strategy using Markov chain state transitions and
optionally a Hidden Markov Model to generate buy/sell signals.

Signal logic: P(bull_tomorrow) - P(bear_tomorrow)
  > 0  → LONG  (size proportional to magnitude)
  < 0  → SHORT (size proportional to magnitude)
  = 0  → NEUTRAL
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Basic Markov model
# ---------------------------------------------------------------------------

STATES = ["bull", "sideways", "bear"]


def classify_states(
    prices: pd.Series,
    lookback: int = 20,
    bull_thresh: float = 0.05,
    bear_thresh: float = -0.05,
) -> pd.Series:
    """
    Label each bar with 'bull', 'bear', or 'sideways' using the cumulative
    return over the previous `lookback` bars.
    """
    daily_ret = prices.pct_change()
    cum_ret = daily_ret.rolling(lookback).sum()

    def _label(r):
        if pd.isna(r):
            return np.nan
        if r >= bull_thresh:
            return "bull"
        if r <= bear_thresh:
            return "bear"
        return "sideways"

    return cum_ret.apply(_label)


def build_transition_matrix(state_series: pd.Series) -> pd.DataFrame:
    """
    Count consecutive-state pairs and normalise each row into probabilities.
    Returns a DataFrame with STATES as both index (current) and columns (next).
    """
    counts = pd.DataFrame(0, index=STATES, columns=STATES, dtype=float)
    clean = state_series.dropna()

    for cur, nxt in zip(clean.iloc[:-1], clean.iloc[1:]):
        counts.loc[cur, nxt] += 1

    row_sums = counts.sum(axis=1)
    # avoid division by zero for unseen states
    row_sums = row_sums.replace(0, np.nan)
    return counts.div(row_sums, axis=0).fillna(0)


def signal_from_state(transition_matrix: pd.DataFrame, current_state: str) -> float:
    """
    P(bull|current) - P(bear|current).
    Positive → LONG, Negative → SHORT. Magnitude = suggested position size.
    """
    row = transition_matrix.loc[current_state]
    return float(row["bull"] - row["bear"])


def interpret_signal(sig: float) -> dict:
    if sig > 0:
        direction = "LONG"
    elif sig < 0:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"
    return {
        "signal": round(sig, 4),
        "direction": direction,
        "position_size_pct": round(abs(sig) * 100, 2),
    }


class MarkovModel:
    """
    Basic Markov Hedge Fund model using human-defined state thresholds.

    Parameters
    ----------
    lookback : int
        Rolling window (bars) used to compute cumulative return for labelling.
    bull_thresh : float
        Cumulative-return threshold above which the state is 'bull'.
    bear_thresh : float
        Cumulative-return threshold below which the state is 'bear'.
    """

    def __init__(
        self,
        lookback: int = 20,
        bull_thresh: float = 0.05,
        bear_thresh: float = -0.05,
    ):
        self.lookback = lookback
        self.bull_thresh = bull_thresh
        self.bear_thresh = bear_thresh
        self.transition_matrix: pd.DataFrame | None = None
        self.states: pd.Series | None = None

    def fit(self, prices: pd.Series) -> "MarkovModel":
        self.states = classify_states(
            prices, self.lookback, self.bull_thresh, self.bear_thresh
        )
        self.transition_matrix = build_transition_matrix(self.states)
        return self

    def predict(self) -> dict:
        current_state = self.states.dropna().iloc[-1]
        sig = signal_from_state(self.transition_matrix, current_state)
        result = interpret_signal(sig)
        result["current_state"] = current_state
        result["transition_matrix"] = self.transition_matrix
        return result

    def backtest_signals(self) -> pd.Series:
        """Return a signal series over history for backtesting."""
        signals = []
        clean = self.states.dropna()
        for state in clean.iloc[:-1]:
            sig = signal_from_state(self.transition_matrix, state)
            signals.append(sig)
        return pd.Series(signals, index=clean.index[:-1], name="signal")


# ---------------------------------------------------------------------------
# Hidden Markov Model (advanced — no hand-crafted thresholds)
# ---------------------------------------------------------------------------

class HiddenMarkovModel:
    """
    Advanced version that lets the data organically discover bull / bear /
    sideways regimes via a Gaussian HMM.  Requires `hmmlearn`.

    States are ranked by their mean return and mapped automatically:
      lowest mean  → 'bear'
      middle mean  → 'sideways'
      highest mean → 'bull'
    """

    def __init__(self, n_components: int = 3, n_iter: int = 200, random_state: int = 42):
        self.n_components = n_components
        self.n_iter = n_iter
        self.random_state = random_state
        self._model = None
        self.states: pd.Series | None = None
        self.transition_matrix: pd.DataFrame | None = None
        self._state_map: dict | None = None

    def fit(self, prices: pd.Series) -> "HiddenMarkovModel":
        try:
            from hmmlearn import hmm
        except ImportError as exc:
            raise ImportError(
                "hmmlearn is required for HiddenMarkovModel.  "
                "Install it with: pip install hmmlearn"
            ) from exc

        returns = prices.pct_change().dropna()
        X = returns.values.reshape(-1, 1)

        model = hmm.GaussianHMM(
            n_components=self.n_components,
            covariance_type="full",
            n_iter=self.n_iter,
            random_state=self.random_state,
        )
        model.fit(X)
        self._model = model

        raw_states = model.predict(X)

        # Map integer states → semantic labels by sorting on mean return
        state_means = {
            s: float(X[raw_states == s].mean()) for s in range(self.n_components)
        }
        sorted_by_mean = sorted(state_means, key=state_means.get)
        semantic = ["bear", "sideways", "bull"]
        self._state_map = {
            sorted_by_mean[i]: semantic[i] for i in range(self.n_components)
        }

        self.states = pd.Series(
            [self._state_map[s] for s in raw_states],
            index=returns.index,
            name="state",
        )
        self.transition_matrix = build_transition_matrix(self.states)
        return self

    def predict(self) -> dict:
        current_state = self.states.iloc[-1]
        sig = signal_from_state(self.transition_matrix, current_state)
        result = interpret_signal(sig)
        result["current_state"] = current_state
        result["transition_matrix"] = self.transition_matrix
        return result

    def backtest_signals(self) -> pd.Series:
        signals = []
        for state in self.states.iloc[:-1]:
            signals.append(signal_from_state(self.transition_matrix, state))
        return pd.Series(signals, index=self.states.index[:-1], name="signal")


# ---------------------------------------------------------------------------
# Backtesting utility
# ---------------------------------------------------------------------------

def run_backtest(prices: pd.Series, signals: pd.Series) -> pd.DataFrame:
    """
    Vectorised backtest: signal sign determines direction, magnitude caps at 1.
    Returns a DataFrame with daily strategy returns and equity curve.
    """
    daily_ret = prices.pct_change()
    # align signals (signal on day t drives position on day t+1)
    position = signals.shift(1).reindex(daily_ret.index).clip(-1, 1).fillna(0)
    strat_ret = position * daily_ret

    equity = (1 + strat_ret).cumprod()
    bh_equity = (1 + daily_ret).cumprod()

    result = pd.DataFrame(
        {
            "price": prices,
            "signal": signals.reindex(prices.index),
            "position": position,
            "strategy_return": strat_ret,
            "strategy_equity": equity,
            "buy_hold_equity": bh_equity,
        }
    )
    return result


def print_backtest_summary(bt: pd.DataFrame) -> None:
    strat = bt["strategy_return"].dropna()
    total = bt["strategy_equity"].iloc[-1] - 1
    bh_total = bt["buy_hold_equity"].iloc[-1] - 1
    sharpe = strat.mean() / strat.std() * np.sqrt(252) if strat.std() else 0

    running_max = bt["strategy_equity"].cummax()
    drawdown = (bt["strategy_equity"] - running_max) / running_max
    max_dd = drawdown.min()

    print(f"{'='*45}")
    print(f"  Strategy total return : {total:+.2%}")
    print(f"  Buy-and-hold return   : {bh_total:+.2%}")
    print(f"  Annualised Sharpe     : {sharpe:.2f}")
    print(f"  Max drawdown          : {max_dd:.2%}")
    print(f"{'='*45}")


# ---------------------------------------------------------------------------
# Quick demo (run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("Install yfinance:  pip install yfinance")

    TICKER = "GC=F"   # Gold futures — closest proxy for XAU/USD
    print(f"\nFetching {TICKER} daily data …")
    raw = yf.download(TICKER, period="5y", auto_adjust=True, progress=False)
    prices = raw["Close"].dropna().squeeze()

    # ---- Basic Markov ----
    print("\n--- Basic Markov Model ---")
    basic = MarkovModel(lookback=20, bull_thresh=0.05, bear_thresh=-0.05)
    basic.fit(prices)
    result = basic.predict()
    print(f"Current state     : {result['current_state']}")
    print(f"Signal            : {result['signal']}")
    print(f"Direction         : {result['direction']}")
    print(f"Suggested size    : {result['position_size_pct']}% of capital")
    print("\nTransition matrix:")
    print(result["transition_matrix"].to_string(float_format="{:.1%}".format))
    signals = basic.backtest_signals()
    bt = run_backtest(prices, signals)
    print("\nBacktest summary:")
    print_backtest_summary(bt)

    # ---- Hidden Markov ----
    try:
        print("\n--- Hidden Markov Model ---")
        hmm_model = HiddenMarkovModel(n_components=3)
        hmm_model.fit(prices)
        hmm_result = hmm_model.predict()
        print(f"Current state     : {hmm_result['current_state']}")
        print(f"Signal            : {hmm_result['signal']}")
        print(f"Direction         : {hmm_result['direction']}")
        print(f"Suggested size    : {hmm_result['position_size_pct']}% of capital")
        print("\nTransition matrix:")
        print(hmm_result["transition_matrix"].to_string(float_format="{:.1%}".format))
        hmm_signals = hmm_model.backtest_signals()
        hmm_bt = run_backtest(prices, hmm_signals)
        print("\nBacktest summary:")
        print_backtest_summary(hmm_bt)
    except ImportError as e:
        print(f"Skipping HMM: {e}")
