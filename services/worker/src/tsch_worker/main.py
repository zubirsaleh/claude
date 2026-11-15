"""Phase 1 worker: liveness heartbeat against the API only.

Analytics, reconciliation sweeps and research jobs land here in Phases 3-5.
"""

from __future__ import annotations

import logging
import os
import signal
import threading

import httpx

log = logging.getLogger("tsch.worker")


def run(api_url: str, interval_s: float, stop: threading.Event) -> None:
    with httpx.Client(timeout=5, trust_env=False) as client:
        while not stop.is_set():
            try:
                r = client.get(f"{api_url}/health")
                log.info("api health %s", r.status_code)
            except httpx.HTTPError as exc:
                log.warning("api unreachable: %s", exc.__class__.__name__)
            stop.wait(interval_s)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run(os.environ.get("TSCH_API_URL", "http://api:8000"),
        float(os.environ.get("TSCH_WORKER_INTERVAL_S", "30")), stop)
