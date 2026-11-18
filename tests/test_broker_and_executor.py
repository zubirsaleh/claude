from datetime import datetime, timedelta, timezone

import pytest

from scalper.broker_oanda import BrokerError, OandaClient, Quote, parse_oanda_time
from scalper.executor import Executor
from scalper.journal import Journal
from scalper.risk import OrderRequest, RiskEngine
from scalper.settings import OandaConfig


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.headers = {}
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs))
        for (m, suffix), resp in self.routes.items():
            if m == method and url.endswith(suffix):
                return resp
        return FakeResponse(404, {"errorMessage": "not found"})


CFG = OandaConfig(token="t", account_id="101-001-1")


def test_parse_nanosecond_time():
    t = parse_oanda_time("2026-11-17T18:00:00.123456789Z")
    assert t == datetime(2026, 11, 17, 18, 0, 0, 123456, tzinfo=timezone.utc)


def test_quote_and_order_payload():
    http = FakeHttp({
        ("GET", "/pricing"): FakeResponse(200, {"prices": [{
            "bids": [{"price": "4000.100"}], "asks": [{"price": "4000.400"}],
            "time": "2026-11-17T18:00:00.000000000Z", "tradeable": True}]}),
        ("POST", "/orders"): FakeResponse(201, {"orderFillTransaction": {"id": "9"}}),
    })
    client = OandaClient(CFG, session=http)
    q = client.quote()
    assert (q.bid, q.ask, q.tradeable) == (4000.1, 4000.4, True)
    client.market_order("SELL", 4, stop_price=4005.12345, take_profit_price=3995.5)
    order = http.calls[-1][2]["json"]["order"]
    assert order["units"] == "-4"
    assert order["instrument"] == "XAU_USD"
    assert order["stopLossOnFill"] == {"price": "4005.123"}
    assert order["takeProfitOnFill"] == {"price": "3995.500"}
    assert http.headers["Authorization"] == "Bearer t"


def test_http_error_raises():
    client = OandaClient(CFG, session=FakeHttp({}))
    with pytest.raises(BrokerError):
        client.equity()


def test_close_all_closes_both_sides():
    http = FakeHttp({
        ("GET", "/openPositions"): FakeResponse(200, {"positions": [{
            "instrument": "XAU_USD", "long": {"units": "4"}, "short": {"units": "0"}}]}),
        ("PUT", "/positions/XAU_USD/close"): FakeResponse(200, {}),
    })
    OandaClient(CFG, session=http).close_all()
    assert http.calls[-1][2]["json"] == {"longUnits": "ALL"}


class FakeBroker:
    def __init__(self, quote_age=1.0, fail_quote=False, fill=True):
        self.quote_age = quote_age
        self.fail_quote = fail_quote
        self.fill = fill
        self.orders = []
        self.closed = False

    def quote(self):
        if self.fail_quote:
            raise BrokerError("timeout")
        now = datetime.now(timezone.utc)
        return Quote(4000.0, 4000.3, now - timedelta(seconds=self.quote_age), True)

    def equity(self):
        return 5000.0

    def open_position_count(self):
        return 0

    def market_order(self, side, units, stop, tp):
        self.orders.append((side, units, stop, tp))
        return {"orderFillTransaction": {"id": "1"}} if self.fill else {"orderCancelTransaction": {}}

    def close_all(self):
        self.closed = True
        return []


@pytest.fixture
def parts(tmp_path, monkeypatch):
    # Pin the session clock to a tradeable time so the test is not time-of-day dependent.
    monkeypatch.setattr("scalper.risk.sessions.entries_allowed", lambda ts: True)
    monkeypatch.setattr("scalper.risk.sessions.in_news_blackout", lambda *a: False)
    risk = RiskEngine(tmp_path / "risk.json")
    journal = Journal(tmp_path / "journal.jsonl")
    return risk, journal, tmp_path


def test_executor_sends_valid_order(parts):
    risk, journal, tmp = parts
    broker = FakeBroker()
    d = Executor(broker, risk, journal).submit(OrderRequest("BUY", 4, 3995.0))
    assert d.allowed, d.reasons
    assert broker.orders == [("BUY", 4, 3995.0, None)]
    assert risk.state.trades_today == 1
    assert "order_sent" in (tmp / "journal.jsonl").read_text()


def test_executor_blocks_on_kill_switch(parts):
    risk, journal, _ = parts
    broker = FakeBroker()
    ex = Executor(broker, risk, journal)
    ex.kill("manual test")
    assert broker.closed
    assert not ex.submit(OrderRequest("BUY", 4, 3995.0)).allowed
    assert broker.orders == []


def test_executor_fails_closed_on_broker_error(parts):
    risk, journal, _ = parts
    broker = FakeBroker(fail_quote=True)
    ex = Executor(broker, risk, journal)
    for _ in range(3):
        assert not ex.submit(OrderRequest("BUY", 4, 3995.0)).allowed
    assert broker.orders == []
    assert risk.state.kill_switch


def test_executor_reports_unfilled(parts):
    risk, journal, _ = parts
    d = Executor(FakeBroker(fill=False), risk, journal).submit(OrderRequest("BUY", 4, 3995.0))
    assert not d.allowed
