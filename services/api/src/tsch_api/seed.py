"""Idempotent seed: SIM account + original strategy catalog metadata.

Catalog entries are descriptions only (`implemented=False`) until Phase 3/5 ships the
research implementations. No performance figures are seeded.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session
from tsch_contracts import BrokerIdentity

from .db import Account, Strategy, append_audit

CATALOG: list[dict[str, object]] = [
    {"key": "ema_cross_trend", "name": "EMA 9/21 cross + EMA 50/200 trend filter",
     "description": "Enter on EMA9/EMA21 cross in direction of EMA50 vs EMA200; ATR(14) stop.",
     "default_params": {"fast": 9, "slow": 21, "trend_fast": 50, "trend_slow": 200,
                        "atr": 14, "atr_mult": 1.5}},
    {"key": "rsi_bb_reversion", "name": "RSI(14) + Bollinger(20,2) mean reversion",
     "description": "Fade band excursions confirmed by RSI extremes, gated by a regime filter.",
     "default_params": {"rsi": 14, "bb": 20, "bb_dev": 2.0, "rsi_lo": 30, "rsi_hi": 70}},
    {"key": "vwap_pullback", "name": "VWAP trend pullback",
     "description": "Trade pullbacks to session VWAP in trend direction; spread/session gated.",
     "default_params": {"max_spread_points": 30, "session": "LONDON"}},
    {"key": "opening_range_breakout", "name": "London / New York opening range breakout",
     "description": "Breakout of the first N minutes of the session, IANA-timezone aware.",
     "default_params": {"session": "LONDON", "range_minutes": 30}},
    {"key": "macd_rsi_confirm", "name": "MACD(12,26,9) + RSI confirmation",
     "description": "MACD signal cross confirmed by RSI side; ATR stop; time-of-day filter.",
     "default_params": {"fast": 12, "slow": 26, "signal": 9, "rsi": 14, "atr": 14}},
    {"key": "observer", "name": "Zero-order observation collector",
     "description": "Records candles and context; never proposes orders.",
     "default_params": {}},
]


def login_hash(login: str) -> str:
    return hashlib.sha256(login.encode()).hexdigest()


def ensure_account(s: Session, ident: BrokerIdentity, label: str = "") -> Account:
    h = login_hash(ident.login)
    acct = s.scalars(select(Account).where(
        Account.mode == ident.mode.value, Account.broker == ident.broker,
        Account.server == ident.server, Account.login_sha256 == h,
    )).first()
    if acct is None:
        acct = Account(mode=ident.mode.value, broker=ident.broker, server=ident.server,
                       login_masked=ident.masked_login, login_sha256=h,
                       account_type=ident.account_type.value, currency=ident.currency,
                       label=label)
        s.add(acct)
        s.flush()
        append_audit(s, "system", "account.registered",
                     {"account_id": acct.id, "mode": acct.mode, "login": acct.login_masked})
    return acct


def seed(s: Session, sim_identity: BrokerIdentity) -> None:
    ensure_account(s, sim_identity, label="Internal SIM (synthetic)")
    for entry in CATALOG:
        exists = s.scalars(select(Strategy).where(
            Strategy.key == entry["key"], Strategy.version == "0.1.0")).first()
        if exists is None:
            s.add(Strategy(version="0.1.0", implemented=False, **entry))
    s.commit()
