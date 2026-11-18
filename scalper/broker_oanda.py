"""Minimal OANDA v20 REST client (practice environment) for XAU_USD."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests

from scalper.settings import INSTRUMENT, OandaConfig

PRICE_DECIMALS = 3


class BrokerError(RuntimeError):
    pass


def parse_oanda_time(value: str) -> datetime:
    """OANDA returns RFC3339 with nanoseconds; Python parses at most microseconds."""
    head, _, frac = value.rstrip("Z").partition(".")
    frac = (frac + "000000")[:6]
    return datetime.fromisoformat(f"{head}.{frac}+00:00")


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    time: datetime
    tradeable: bool


class OandaClient:
    def __init__(self, cfg: OandaConfig, session: requests.Session | None = None,
                 timeout: float = 5.0) -> None:
        self.cfg = cfg
        self.timeout = timeout
        self.http = session or requests.Session()
        self.http.headers.update({
            "Authorization": f"Bearer {cfg.token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        })

    def _url(self, path: str) -> str:
        return f"{self.cfg.rest_url}/v3{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self.http.request(method, self._url(path), timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise BrokerError(f"{method} {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise BrokerError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def account_summary(self) -> dict:
        return self._request("GET", f"/accounts/{self.cfg.account_id}/summary")["account"]

    def equity(self) -> float:
        return float(self.account_summary()["NAV"])

    def quote(self) -> Quote:
        data = self._request(
            "GET", f"/accounts/{self.cfg.account_id}/pricing",
            params={"instruments": INSTRUMENT},
        )
        prices = data.get("prices") or []
        if not prices:
            raise BrokerError("no price returned")
        p = prices[0]
        return Quote(
            bid=float(p["bids"][0]["price"]),
            ask=float(p["asks"][0]["price"]),
            time=parse_oanda_time(p["time"]),
            tradeable=bool(p.get("tradeable", False)),
        )

    def candles_m1(self, count: int = 500) -> list[dict]:
        """Completed M1 candles with bid and ask OHLC."""
        data = self._request(
            "GET", f"/instruments/{INSTRUMENT}/candles",
            params={"granularity": "M1", "count": count, "price": "BA"},
        )
        return [c for c in data.get("candles", []) if c.get("complete")]

    def open_positions(self) -> list[dict]:
        data = self._request("GET", f"/accounts/{self.cfg.account_id}/openPositions")
        return [p for p in data.get("positions", []) if p.get("instrument") == INSTRUMENT]

    def open_position_count(self) -> int:
        count = 0
        for p in self.open_positions():
            count += int(float(p["long"]["units"]) != 0) + int(float(p["short"]["units"]) != 0)
        return count

    def market_order(self, side: str, units: int, stop_price: float,
                     take_profit_price: float | None = None) -> dict:
        signed = units if side == "BUY" else -units
        order: dict = {
            "type": "MARKET",
            "instrument": INSTRUMENT,
            "units": str(signed),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": f"{stop_price:.{PRICE_DECIMALS}f}"},
        }
        if take_profit_price is not None:
            order["takeProfitOnFill"] = {"price": f"{take_profit_price:.{PRICE_DECIMALS}f}"}
        return self._request("POST", f"/accounts/{self.cfg.account_id}/orders",
                             json={"order": order})

    def close_all(self) -> list[dict]:
        results = []
        for p in self.open_positions():
            body = {}
            if float(p["long"]["units"]) != 0:
                body["longUnits"] = "ALL"
            if float(p["short"]["units"]) != 0:
                body["shortUnits"] = "ALL"
            if body:
                results.append(self._request(
                    "PUT", f"/accounts/{self.cfg.account_id}/positions/{INSTRUMENT}/close",
                    json=body,
                ))
        return results
