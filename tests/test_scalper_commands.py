import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
sc = pytest.importorskip("bot.scalper_commands")


def upd(uid):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid))


def test_empty_allowlist_denies_trading_commands(monkeypatch):
    monkeypatch.setattr(sc, "ALLOWED_USER_IDS", [])
    assert not sc._authorized(upd(42))


def test_allowlist_enforced(monkeypatch):
    monkeypatch.setattr(sc, "ALLOWED_USER_IDS", [42])
    assert sc._authorized(upd(42))
    assert not sc._authorized(upd(7))
