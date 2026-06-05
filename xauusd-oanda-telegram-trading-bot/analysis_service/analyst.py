"""Rule-based (and optional OpenAI) trade analyst for XAU/USD.

Given indicators + patterns from the OANDA service, this module:
  * scores the setup (0-100) using the documented weighting,
  * derives a LONG / SHORT / WAIT bias from the documented rules,
  * formats the standard analysis report,
  * optionally lets OpenAI rewrite the commentary (deterministic numbers are
    always produced locally so the result is reproducible and grounded).
"""
from __future__ import annotations

import logging

from shared import config
from shared.models import RiskPlan
from risk_engine import build_plan

log = logging.getLogger("analysis-service.analyst")

DISCLAIMER = "This is analysis only, not financial advice."


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def _score(ind: dict, patterns: dict) -> tuple[int, dict]:
    """Return (signal_score, breakdown) using the documented weighting."""
    price = ind["price"]
    ema21, ema50 = ind["ema_21"], ind["ema_50"]
    ema9, ema200 = ind["ema_9"], ind["ema_200"]
    rsi = ind["rsi_14"]
    hist = ind.get("macd_hist") or 0.0
    hist_prev = ind.get("macd_hist_prev") or 0.0
    atr_pct = ind.get("atr_pct") or 0.0
    support, resistance = ind.get("support"), ind.get("resistance")
    structure = ind.get("market_structure", "")

    bull_struct = "Uptrend" in structure
    bear_struct = "Downtrend" in structure

    b: dict[str, int] = {}

    # Trend alignment (25): price vs EMA50 + structure agreement.
    if price > ema50 and bull_struct:
        b["trend"] = 25
    elif price < ema50 and bear_struct:
        b["trend"] = 25
    elif price > ema50 or price < ema50:
        b["trend"] = 13
    else:
        b["trend"] = 0

    # EMA alignment (20): full stack ordering.
    if ema9 > ema21 > ema50:
        b["ema"] = 20
    elif ema9 < ema21 < ema50:
        b["ema"] = 20
    elif (ema9 > ema21) or (ema9 < ema21):
        b["ema"] = 10
    else:
        b["ema"] = 0

    # MACD (15): histogram sign + momentum direction.
    if hist > 0 and hist >= hist_prev:
        b["macd"] = 15
    elif hist < 0 and hist <= hist_prev:
        b["macd"] = 15
    elif hist != 0:
        b["macd"] = 8
    else:
        b["macd"] = 0

    # RSI (10): healthy trend zone, penalise extremes.
    if 45 <= rsi <= 70 or 30 <= rsi <= 55:
        b["rsi"] = 10
    elif 25 <= rsi <= 75:
        b["rsi"] = 5
    else:
        b["rsi"] = 0

    # Candlestick pattern (10).
    b["pattern"] = 10 if patterns.get("signal") in ("Bullish", "Bearish") else 0

    # Support/resistance location (10): reward room to the next level.
    b["sr"] = 0
    if support and resistance and resistance > support:
        band = resistance - support
        if band > 0:
            pos = (price - support) / band  # 0 at support, 1 at resistance
            # Mid-band (away from both barriers) scores best.
            b["sr"] = 10 if 0.2 <= pos <= 0.8 else 4

    # ATR volatility filter (10): need enough movement, not too wild.
    if 0.05 <= atr_pct <= 1.5:
        b["atr"] = 10
    elif atr_pct > 0:
        b["atr"] = 4
    else:
        b["atr"] = 0

    total = int(sum(b.values()))
    return min(total, 100), b


def _confidence(score: int) -> str:
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    return "Low"


def _score_label(score: int) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    if score >= 40:
        return "Weak"
    return "No trade"


# --------------------------------------------------------------------------
# Bias
# --------------------------------------------------------------------------
def _bias(ind: dict, patterns: dict) -> tuple[str, str]:
    """Return (bias, reason) from the documented LONG/SHORT/WAIT rules."""
    price = ind["price"]
    ema21, ema50 = ind["ema_21"], ind["ema_50"]
    ema9 = ind["ema_9"]
    rsi = ind["rsi_14"]
    hist = ind.get("macd_hist") or 0.0
    hist_prev = ind.get("macd_hist_prev") or 0.0
    atr_pct = ind.get("atr_pct") or 0.0
    support, resistance = ind.get("support"), ind.get("resistance")
    psig = patterns.get("signal")
    structure = ind.get("market_structure", "")

    # WAIT guards first.
    if rsi >= 80 or rsi <= 20:
        return "WAIT", f"RSI extreme ({rsi}); waiting for mean reversion."
    if atr_pct and atr_pct < 0.03:
        return "WAIT", "ATR too low; volatility insufficient for a clean trade."
    near = _near_level(price, support, resistance, ind.get("atr_14") or 0.0)
    if near:
        return "WAIT", f"Price sitting on major {near}; waiting for a break/reject."

    macd_up = hist > 0 or hist > hist_prev
    macd_down = hist < 0 or hist < hist_prev
    bull_pattern = psig == "Bullish" or "Uptrend" in structure
    bear_pattern = psig == "Bearish" or "Downtrend" in structure

    long_ok = (
        price > ema21
        and price > ema50
        and ema9 > ema21
        and macd_up
        and 45 <= rsi <= 70
        and not _too_close(price, resistance, ind.get("atr_14") or 0.0)
        and bull_pattern
    )
    short_ok = (
        price < ema21
        and price < ema50
        and ema9 < ema21
        and macd_down
        and 30 <= rsi <= 55
        and not _too_close(price, support, ind.get("atr_14") or 0.0)
        and bear_pattern
    )

    if long_ok and not short_ok:
        return "LONG", "Price above EMA21/50 with bullish EMA stack, supportive MACD/RSI and structure."
    if short_ok and not long_ok:
        return "SHORT", "Price below EMA21/50 with bearish EMA stack, supportive MACD/RSI and structure."
    return "WAIT", "Indicators conflict or trend conditions are not aligned."


def _too_close(price: float, level, atr: float) -> bool:
    if not level or not atr:
        return False
    return abs(price - level) <= 0.5 * atr


def _near_level(price: float, support, resistance, atr: float):
    if support and atr and abs(price - support) <= 0.25 * atr:
        return "support"
    if resistance and atr and abs(price - resistance) <= 0.25 * atr:
        return "resistance"
    return None


# --------------------------------------------------------------------------
# Report formatting
# --------------------------------------------------------------------------
def _fmt(value, suffix: str = "") -> str:
    return f"{value}{suffix}" if value is not None else "n/a"


def _ema_alignment(ind: dict) -> str:
    e9, e21, e50, e200 = ind["ema_9"], ind["ema_21"], ind["ema_50"], ind["ema_200"]
    if e9 > e21 > e50 > e200:
        return "Bullish (9>21>50>200)"
    if e9 < e21 < e50 < e200:
        return "Bearish (9<21<50<200)"
    if e9 > e21:
        return "Short-term bullish, mixed longer-term"
    return "Short-term bearish, mixed longer-term"


def _pattern_summary(patterns: dict) -> str:
    seq = []
    for c in patterns.get("last_5", []):
        names = ", ".join(c["patterns"]) if c["patterns"] else "-"
        seq.append(f"{'▲' if c['direction'] == 'bull' else '▼'}({names})")
    return " ".join(seq) if seq else "n/a"


def format_report(
    timeframe: str,
    ind: dict,
    patterns: dict,
    bias: str,
    reason: str,
    score: int,
    plan: RiskPlan | None,
) -> str:
    confidence = _confidence(score)
    advisory = config.ADVISORY_ONLY or not config.ALLOW_LIVE_TRADING
    lines: list[str] = []
    a = lines.append

    a(f"XAU/USD OANDA — {timeframe} Analysis")
    a("")
    a("Price Action")
    a(f"- Current Price: {_fmt(ind.get('price'))}")
    a(f"- Recent Trend: {_fmt(ind.get('recent_trend'))}")
    a(f"- Support: {_fmt(ind.get('support'))}")
    a(f"- Resistance: {_fmt(ind.get('resistance'))}")
    a(f"- Market Structure: {_fmt(ind.get('market_structure'))}")
    a("")
    a("Technical Indicators")
    a(f"- RSI: {_fmt(ind.get('rsi_14'))}")
    a(f"- MACD: {_fmt(ind.get('macd'))} (hist {_fmt(ind.get('macd_hist'))})")
    a(f"- Bollinger Bands: {_fmt(ind.get('bb_lower'))} / {_fmt(ind.get('bb_mid'))} / {_fmt(ind.get('bb_upper'))}")
    a(f"- EMA Alignment: {_ema_alignment(ind)}")
    a(f"- Stochastic: K {_fmt(ind.get('stoch_k'))} / D {_fmt(ind.get('stoch_d'))}")
    a(f"- ATR: {_fmt(ind.get('atr_14'))} ({_fmt(ind.get('atr_pct'), '%')})")
    a("")
    a("Candlestick Patterns")
    a(f"- Last 5 candles: {_pattern_summary(patterns)}")
    a(f"- Detected Pattern: {patterns.get('detected', 'None')}")
    a(f"- Signal: {patterns.get('signal', 'Neutral')}")
    a("")
    a("Trading Bias")
    a(f"- Bias: {bias}")
    a(f"- Reason: {reason}")
    a(f"- Signal Score: {score} ({_score_label(score)})")
    a(f"- Confidence: {confidence}")
    a("")
    a("Position Suggestion")
    if plan:
        a(f"- Entry Zone: {plan.entry}")
        a(f"- Stop Loss: {plan.stop_loss}")
        a(f"- Target 1: {plan.target_1}")
        a(f"- Target 2: {plan.target_2}")
        a(f"- Risk/Reward: {plan.risk_reward}")
        a(f"- Position Size: {plan.position_size} units "
          f"(risk {plan.risk_percent}% = {plan.risk_amount} on {plan.account_balance})")
    else:
        a("- Entry Zone: n/a (WAIT — no actionable setup)")
        a("- Stop Loss: n/a")
        a("- Target 1: n/a")
        a("- Target 2: n/a")
        a("- Risk/Reward: n/a")
        a("- Position Size: n/a")
    a(f"- Advisory Mode: {'ON' if advisory else 'OFF'}")
    a("")
    a("Key Risks")
    a(f"- Technical invalidation: {_invalidation(bias, plan)}")
    a(f"- Volatility warning: {_vol_warning(ind)}")
    a("- News warning placeholder: Check the economic calendar for high-impact USD/gold news.")
    a("")
    a(DISCLAIMER)
    return "\n".join(lines)


def _invalidation(bias: str, plan: RiskPlan | None) -> str:
    if not plan:
        return "No position; setup invalid until indicators align."
    if bias == "LONG":
        return f"A close below {plan.stop_loss} invalidates the long."
    return f"A close above {plan.stop_loss} invalidates the short."


def _vol_warning(ind: dict) -> str:
    atr_pct = ind.get("atr_pct") or 0.0
    if atr_pct > 1.2:
        return f"Elevated volatility (ATR {atr_pct}% of price) — widen stops / reduce size."
    if atr_pct < 0.05:
        return f"Very low volatility (ATR {atr_pct}% of price) — moves may be choppy."
    return "Volatility within a normal range."


# --------------------------------------------------------------------------
# Optional OpenAI commentary
# --------------------------------------------------------------------------
def _maybe_openai(report: str, ind: dict, bias: str, score: int) -> str | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        prompt = (
            "You are a disciplined XAU/USD trading analyst. Rewrite the analysis "
            "below into a concise, well-structured Telegram message. Do NOT invent "
            "any numbers, prices or signals — use only what is provided. Keep the "
            "bias, score and all levels exactly as given. End with the disclaimer.\n\n"
            f"Computed bias: {bias}, score: {score}.\n\n"
            f"{report}"
        )
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=900,
        )
        text = resp.choices[0].message.content
        return text.strip() if text else None
    except Exception as exc:  # never let the optional layer break analysis
        log.warning("OpenAI commentary failed, using rule-based output: %s", exc)
        return None


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def analyze(
    timeframe: str,
    market: dict,
    account_balance: float,
    risk_percent: float,
) -> dict:
    """Run the full analysis pipeline and return a serialisable dict."""
    ind = market["indicators"]
    patterns = market["patterns"]
    entry = market.get("current_price") or ind["price"]

    score, breakdown = _score(ind, patterns)
    bias, reason = _bias(ind, patterns)

    # If the score is below the no-trade floor, force WAIT.
    if score < 40 and bias != "WAIT":
        bias = "WAIT"
        reason = f"Signal score {score} below trade threshold (40)."

    plan = build_plan(bias, entry, ind, account_balance, risk_percent)
    report = format_report(timeframe, ind, patterns, bias, reason, score, plan)

    source = "rule-based"
    enhanced = _maybe_openai(report, ind, bias, score)
    if enhanced:
        report = enhanced
        source = "openai"

    log.info(
        "SIGNAL | tf=%s bias=%s score=%s conf=%s breakdown=%s",
        timeframe, bias, score, _confidence(score), breakdown,
    )

    return {
        "instrument": config.OANDA_INSTRUMENT,
        "timeframe": timeframe,
        "text": report,
        "bias": bias,
        "signal_score": score,
        "confidence": _confidence(score),
        "advisory_only": config.ADVISORY_ONLY or not config.ALLOW_LIVE_TRADING,
        "source": source,
    }
