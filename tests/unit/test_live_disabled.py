from __future__ import annotations

import pytest
from tsch_api import brokers
from tsch_contracts import AccountMode, BrokerNotConnected, LiveTradingDisabled


def test_live_is_not_compiled_in() -> None:
    assert brokers.LIVE_EXECUTION_COMPILED_IN is False


def test_live_mode_refuses_even_with_env_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("IS_LIVE", "TSCH_IS_LIVE", "LIVE_TRADING", "TSCH_LIVE_ENABLED"):
        monkeypatch.setenv(var, "true")
    with pytest.raises(LiveTradingDisabled):
        brokers.make_adapter(AccountMode.LIVE_DISABLED)


def test_tradingview_has_no_order_adapter() -> None:
    with pytest.raises(BrokerNotConnected, match="manual only"):
        brokers.make_adapter(AccountMode.TRADINGVIEW_PAPER_MANUAL)


def test_mt5_demo_not_faked() -> None:
    with pytest.raises(BrokerNotConnected):
        brokers.make_adapter(AccountMode.MT5_DEMO)
