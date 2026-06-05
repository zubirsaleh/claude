"""Analysis microservice (FastAPI).

Orchestrates the pipeline: pull market data from the OANDA service, run the
indicator/pattern-based analyst and risk engine, and return a formatted
report. Optionally enhanced by OpenAI when a key is configured.
"""
from __future__ import annotations

import requests
from fastapi import FastAPI, HTTPException

from shared import config
from shared.logging_config import setup_logging
from shared.models import AnalysisRequest

from analyst import analyze, DISCLAIMER
from risk_engine import build_plan
from analyst import _bias  # reuse bias logic for the /risk sample

log = setup_logging("analysis-service")
app = FastAPI(title="XAU/USD Analysis Service", version="1.0.0")

_TIMEOUT = 30


def _oanda_get(path: str, params: dict | None = None) -> dict:
    url = f"{config.OANDA_SERVICE_URL}{path}"
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        log.error("oanda-service unreachable: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="OANDA data unavailable. Please check API key, account ID, or network.",
        )
    if resp.status_code >= 400:
        detail = _safe_detail(resp)
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


def _safe_detail(resp: requests.Response) -> str:
    try:
        return resp.json().get("detail", resp.text)
    except Exception:
        return resp.text


def _marketdata(timeframe: str) -> dict:
    return _oanda_get(
        "/marketdata",
        {"granularity": timeframe, "count": config.DEFAULT_CANDLE_COUNT},
    )


@app.get("/health")
def health() -> dict:
    oanda_ok = True
    try:
        _oanda_get("/health")
    except HTTPException:
        oanda_ok = False
    return {
        "service": "analysis-service",
        "status": "ok",
        "oanda_service": "online" if oanda_ok else "offline",
        "openai": bool(config.OPENAI_API_KEY),
        "advisory_only": config.ADVISORY_ONLY,
    }


@app.get("/price")
def price() -> dict:
    return _oanda_get("/price")


@app.post("/analyze")
def analyze_endpoint(req: AnalysisRequest) -> dict:
    balance = req.account_balance or config.DEFAULT_ACCOUNT_BALANCE
    risk_pct = req.risk_percent or config.DEFAULT_RISK_PERCENT
    mode = req.mode

    log.info("ANALYSIS REQUEST | mode=%s tf=%s balance=%s risk=%s",
             mode, req.timeframe, balance, risk_pct)

    if mode == "price":
        return _price_response()
    if mode == "risk":
        return _risk_response(req.timeframe or config.DEFAULT_TIMEFRAME, balance, risk_pct)
    if mode == "scalp":
        return _scalp_response(balance, risk_pct)
    if mode == "daily":
        return _daily_response(balance, risk_pct)

    # Default full analysis.
    tf = (req.timeframe or config.DEFAULT_TIMEFRAME).upper()
    if tf not in config.SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported timeframe. Use M1, M5, M15, M30, H1, H4, or D.",
        )
    market = _marketdata(tf)
    return analyze(tf, market, balance, risk_pct)


# --------------------------------------------------------------------------
# Mode helpers
# --------------------------------------------------------------------------
def _price_response() -> dict:
    q = _oanda_get("/price")
    bid, ask, mid = q.get("bid"), q.get("ask"), q.get("mid")
    text = (
        f"XAU/USD OANDA — Price\n"
        f"- Bid: {bid}\n- Ask: {ask}\n- Mid: {mid}\n- Time: {q.get('time')}\n\n"
        f"{DISCLAIMER}"
    )
    return {"instrument": config.OANDA_INSTRUMENT, "timeframe": "-", "text": text,
            "bias": "WAIT", "signal_score": 0, "confidence": "Low",
            "advisory_only": True, "source": "rule-based"}


def _risk_response(timeframe: str, balance: float, risk_pct: float) -> dict:
    tf = timeframe.upper()
    if tf not in config.SUPPORTED_TIMEFRAMES:
        tf = config.DEFAULT_TIMEFRAME
    market = _marketdata(tf)
    ind = market["indicators"]
    entry = market.get("current_price") or ind["price"]
    bias, _ = _bias(ind, market["patterns"])
    # For a risk sample, assume a LONG if no directional bias, just to size it.
    sample_bias = bias if bias in ("LONG", "SHORT") else "LONG"
    plan = build_plan(sample_bias, entry, ind, balance, risk_pct)
    if not plan:
        raise HTTPException(status_code=502, detail="Could not build a risk plan from current data.")
    text = (
        f"XAU/USD OANDA — Risk / Position Sizing ({tf})\n"
        f"- Direction (sample): {sample_bias}\n"
        f"- Account Balance: {plan.account_balance}\n"
        f"- Risk Percent: {plan.risk_percent}%\n"
        f"- Risk Amount: {plan.risk_amount}\n"
        f"- Entry: {plan.entry}\n"
        f"- Stop Loss: {plan.stop_loss}\n"
        f"- Risk per Unit: {plan.risk_per_unit}\n"
        f"- Target 1: {plan.target_1}\n"
        f"- Target 2: {plan.target_2}\n"
        f"- Risk/Reward: {plan.risk_reward}\n"
        f"- Position Size: {plan.position_size} units\n\n"
        f"{DISCLAIMER}"
    )
    return {"instrument": config.OANDA_INSTRUMENT, "timeframe": tf, "text": text,
            "bias": bias, "signal_score": 0, "confidence": "Low",
            "advisory_only": config.ADVISORY_ONLY, "source": "rule-based"}


def _scalp_response(balance: float, risk_pct: float) -> dict:
    """M5 setup confirmed by M15 trend."""
    m5 = _marketdata("M5")
    m15 = _marketdata("M15")
    primary = analyze("M5", m5, balance, risk_pct)
    confirm = analyze("M15", m15, balance, risk_pct)

    agree = primary["bias"] == confirm["bias"] and primary["bias"] != "WAIT"
    final_bias = primary["bias"] if agree else "WAIT"
    note = (
        f"M5 bias {primary['bias']} confirmed by M15 {confirm['bias']}."
        if agree
        else f"No confirmation: M5={primary['bias']} vs M15={confirm['bias']} → WAIT."
    )
    text = (
        f"XAU/USD OANDA — Scalp Setup (M5 + M15 confirmation)\n"
        f"- Bias: {final_bias}\n"
        f"- Note: {note}\n"
        f"- M5 Score: {primary['signal_score']} | M15 Score: {confirm['signal_score']}\n\n"
        f"--- M5 detail ---\n{primary['text']}"
    )
    return {"instrument": config.OANDA_INSTRUMENT, "timeframe": "M5/M15", "text": text,
            "bias": final_bias, "signal_score": primary["signal_score"],
            "confidence": primary["confidence"], "advisory_only": primary["advisory_only"],
            "source": primary["source"]}


def _daily_response(balance: float, risk_pct: float) -> dict:
    """Higher-timeframe bias from H4 + D."""
    h4 = _marketdata("H4")
    d = _marketdata("D")
    h4_a = analyze("H4", h4, balance, risk_pct)
    d_a = analyze("D", d, balance, risk_pct)

    if h4_a["bias"] == d_a["bias"] and h4_a["bias"] != "WAIT":
        htf_bias = h4_a["bias"]
        note = f"H4 and Daily agree on {htf_bias}."
    else:
        htf_bias = d_a["bias"]
        note = f"Daily bias is {d_a['bias']}; H4 is {h4_a['bias']}."
    text = (
        f"XAU/USD OANDA — Higher-Timeframe Bias (H4 + D)\n"
        f"- HTF Bias: {htf_bias}\n"
        f"- Note: {note}\n"
        f"- H4 Score: {h4_a['signal_score']} | Daily Score: {d_a['signal_score']}\n\n"
        f"--- Daily detail ---\n{d_a['text']}"
    )
    return {"instrument": config.OANDA_INSTRUMENT, "timeframe": "H4/D", "text": text,
            "bias": htf_bias, "signal_score": d_a["signal_score"],
            "confidence": d_a["confidence"], "advisory_only": d_a["advisory_only"],
            "source": d_a["source"]}
