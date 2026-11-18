from datetime import datetime, timedelta, timezone

import pytest

from scalper.risk import MarketSnapshot, OrderRequest, RiskEngine
from scalper.settings import LIMITS

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)  # Tuesday, NY session


@pytest.fixture
def engine(tmp_path):
    return RiskEngine(tmp_path / "risk.json")


def mkt(equity=40000.0, bid=4000.00, ask=4000.30, age=1.0, open_positions=0, news=None):
    return MarketSnapshot(bid=bid, ask=ask, quote_time=NOW - timedelta(seconds=age),
                          equity=equity, open_positions=open_positions,
                          news_events=news or [])


def buy(stop=3995.00, units=LIMITS.units):
    return OrderRequest(side="BUY", units=units, stop_price=stop)


def test_limits_match_account():
    assert LIMITS.units == 40
    assert LIMITS.max_risk_per_trade_usd == 400.0
    assert LIMITS.max_daily_loss_usd == 1200.0


def test_valid_order_allowed(engine):
    d = engine.check_order(buy(), mkt(), NOW)
    assert d.allowed, d.reasons


@pytest.mark.parametrize("order,needle", [
    (OrderRequest("BUY", 40, None), "no stop-loss"),
    (buy(stop=4001.0), "wrong side"),
    (buy(stop=3990.0), "trade risk"),        # 10.30 * 40 = 412 > 400
    (buy(stop=4000.0), "x spread"),          # 0.30 stop vs 0.30 spread
    (buy(units=4), "units"),
    (OrderRequest("HOLD", 40, 3995.0), "invalid side"),
])
def test_bad_orders_denied(engine, order, needle):
    d = engine.check_order(order, mkt(), NOW)
    assert not d.allowed
    assert any(needle in r for r in d.reasons), d.reasons


def test_sell_stop_must_be_above(engine):
    assert engine.check_order(OrderRequest("SELL", 40, 4005.0), mkt(), NOW).allowed
    assert not engine.check_order(OrderRequest("SELL", 40, 3999.0), mkt(), NOW).allowed


@pytest.mark.parametrize("snapshot,needle", [
    (mkt(ask=4000.90), "spread"),
    (mkt(age=10), "stale"),
    (mkt(age=-5), "future"),
    (mkt(bid=0, ask=0), "invalid quote"),
    (mkt(open_positions=1), "open positions"),
    (mkt(news=[NOW + timedelta(minutes=5)]), "news"),
])
def test_bad_market_denied(engine, snapshot, needle):
    d = engine.check_order(buy(), snapshot, NOW)
    assert not d.allowed
    assert any(needle in r for r in d.reasons), d.reasons


def test_rollover_session_denied(engine):
    t = datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc)
    d = engine.check_order(buy(), MarketSnapshot(4000.0, 4000.3, t, 40000.0, 0), t)
    assert not d.allowed and any("ROLLOVER" in r for r in d.reasons)


def test_daily_loss_lock(engine):
    engine.update_equity(40000.0, NOW)
    d = engine.check_order(buy(), mkt(equity=38800.0), NOW)  # 3 x 400 lost
    assert not d.allowed and any("daily loss" in r for r in d.reasons)


def test_trade_cannot_exceed_remaining_daily_budget(engine):
    engine.update_equity(40000.0, NOW)
    d = engine.check_order(buy(), mkt(equity=39000.0), NOW)  # 200 left, trade risks 212
    assert not d.allowed and any("remaining daily budget" in r for r in d.reasons)


def test_daily_counters_reset_next_trading_day(engine):
    engine.update_equity(40000.0, NOW)
    engine.state.trades_today = LIMITS.max_trades_per_day
    assert not engine.check_order(buy(), mkt(), NOW).allowed
    tomorrow = NOW + timedelta(days=1)
    snap = MarketSnapshot(4000.0, 4000.3, tomorrow, 39500.0, 0)
    assert engine.check_order(buy(), snap, tomorrow).allowed
    assert engine.state.day_start_equity == 39500.0


def test_drawdown_trips_persistent_kill_switch(tmp_path):
    path = tmp_path / "risk.json"
    engine = RiskEngine(path)
    engine.update_equity(40000.0, NOW)
    d = engine.check_order(buy(), mkt(equity=34000.0), NOW)
    assert not d.allowed and "kill switch" in d.reasons[0]
    reloaded = RiskEngine(path)
    assert reloaded.state.kill_switch
    assert not reloaded.check_order(buy(), mkt(equity=40000.0), NOW).allowed


def test_drawdown_measured_from_peak(engine):
    engine.update_equity(42000.0, NOW)
    engine.update_equity(35699.0, NOW)  # just over 15% below 42000
    assert engine.state.kill_switch


def test_consecutive_losses_pause_session(engine):
    engine.update_equity(40000.0, NOW)
    for _ in range(LIMITS.max_consecutive_losses):
        engine.record_trade_closed(-5.0, NOW)
    d = engine.check_order(buy(), mkt(equity=39980.0), NOW)
    assert not d.allowed and any("consecutive losses" in r for r in d.reasons)
    engine.record_trade_closed(+3.0, NOW)
    assert engine.check_order(buy(), mkt(equity=39983.0), NOW).allowed


def test_api_errors_trip_kill_switch(engine):
    for _ in range(LIMITS.max_consecutive_api_errors):
        engine.record_api_error()
    assert engine.state.kill_switch


def test_exception_fails_closed(engine):
    d = engine.check_order(buy(), mkt(), datetime(2026, 11, 17, 18, 0))  # naive
    assert not d.allowed and "risk check error" in d.reasons[0]
