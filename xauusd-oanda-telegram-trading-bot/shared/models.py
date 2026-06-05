"""Pydantic data models shared across services.

These define the request/response contracts between the Telegram bot, the
analysis service and the OANDA service. Keeping them in one place means the
services cannot drift apart silently.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Bias = Literal["LONG", "SHORT", "WAIT"]
Confidence = Literal["High", "Medium", "Low"]
Mode = Literal["analyze", "scalp", "daily", "risk", "price"]


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool


class PriceQuote(BaseModel):
    instrument: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    close: Optional[float] = None
    time: Optional[str] = None


class AnalysisRequest(BaseModel):
    mode: Mode = "analyze"
    timeframe: Optional[str] = None
    account_balance: Optional[float] = None
    risk_percent: Optional[float] = None


class RiskPlan(BaseModel):
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float
    risk_per_unit: float
    risk_amount: float
    position_size: float
    account_balance: float
    risk_percent: float


class AnalysisResult(BaseModel):
    instrument: str = "XAU_USD"
    timeframe: str
    text: str = Field(..., description="Formatted, human-readable analysis")
    bias: Bias = "WAIT"
    signal_score: int = 0
    confidence: Confidence = "Low"
    advisory_only: bool = True
    source: Literal["openai", "rule-based"] = "rule-based"
