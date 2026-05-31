#!/usr/bin/env python3
"""TV & streaming service health checker."""

import argparse
import concurrent.futures
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


SERVICES = {
    "Netflix": "https://www.netflix.com",
    "YouTube": "https://www.youtube.com",
    "Disney+": "https://www.disneyplus.com",
    "Amazon Prime Video": "https://www.primevideo.com",
    "Apple TV+": "https://tv.apple.com",
    "Hulu": "https://www.hulu.com",
    "HBO Max": "https://www.max.com",
    "Peacock": "https://www.peacocktv.com",
    "Paramount+": "https://www.paramountplus.com",
    "ESPN+": "https://plus.espn.com",
}

STATUS_OK = "OK"
STATUS_DEGRADED = "DEGRADED"
STATUS_DOWN = "DOWN"

# Thresholds in seconds
LATENCY_WARN = 2.0
LATENCY_TIMEOUT = 10.0

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


@dataclass
class CheckResult:
    name: str
    url: str
    status: str
    latency_ms: Optional[float] = None
    http_code: Optional[int] = None
    error: Optional[str] = None
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def check_service(name: str, url: str, timeout: float = LATENCY_TIMEOUT) -> CheckResult:
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tv-health-check/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.monotonic() - start) * 1000
            code = resp.status
            if latency / 1000 > LATENCY_WARN:
                status = STATUS_DEGRADED
            else:
                status = STATUS_OK
            return CheckResult(name, url, status, latency, code)
    except urllib.error.HTTPError as e:
        latency = (time.monotonic() - start) * 1000
        # 4xx from the service still means it's reachable
        if e.code < 500:
            status = STATUS_OK if latency / 1000 <= LATENCY_WARN else STATUS_DEGRADED
        else:
            status = STATUS_DEGRADED
        return CheckResult(name, url, status, latency, e.code)
    except urllib.error.URLError as e:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(name, url, STATUS_DOWN, latency, error=str(e.reason))
    except Exception as e:  # noqa: BLE001
        latency = (time.monotonic() - start) * 1000
        return CheckResult(name, url, STATUS_DOWN, latency, error=str(e))


def _status_color(status: str) -> str:
    return {STATUS_OK: GREEN, STATUS_DEGRADED: YELLOW, STATUS_DOWN: RED}.get(status, RESET)


def print_table(results: list[CheckResult], no_color: bool = False) -> None:
    col_name = max(len(r.name) for r in results)
    col_name = max(col_name, 8)

    header = f"{'Service':<{col_name}}  {'Status':<10}  {'Latency':>10}  {'HTTP':>4}"
    print(f"\n{BOLD}{header}{RESET}" if not no_color else f"\n{header}")
    print("-" * len(header))

    for r in results:
        latency_str = f"{r.latency_ms:>8.0f}ms" if r.latency_ms is not None else " " * 10
        code_str = str(r.http_code) if r.http_code else "  --"
        detail = r.error if r.error else ""
        color = "" if no_color else _status_color(r.status)
        rst = "" if no_color else RESET
        row = f"{r.name:<{col_name}}  {color}{r.status:<10}{rst}  {latency_str}  {code_str}"
        if detail:
            row += f"  ({detail})"
        print(row)


def print_json(results: list[CheckResult]) -> None:
    data = [
        {
            "name": r.name,
            "url": r.url,
            "status": r.status,
            "latency_ms": round(r.latency_ms, 1) if r.latency_ms else None,
            "http_code": r.http_code,
            "error": r.error,
            "checked_at": r.checked_at,
        }
        for r in results
    ]
    print(json.dumps(data, indent=2))


def run_checks(
    services: dict[str, str],
    workers: int = 8,
    timeout: float = LATENCY_TIMEOUT,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_service, name, url, timeout): name for name, url in services.items()}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: r.name)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the health of popular TV & streaming services.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=LATENCY_TIMEOUT,
        metavar="SECS",
        help=f"Request timeout in seconds (default: {LATENCY_TIMEOUT})",
    )
    parser.add_argument(
        "--services",
        nargs="+",
        metavar="NAME",
        help="Limit checks to specific services by name (case-insensitive substring match)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available services and exit",
    )
    args = parser.parse_args()

    if args.list:
        for name, url in sorted(SERVICES.items()):
            print(f"{name:<25}  {url}")
        return 0

    services = SERVICES
    if args.services:
        filters = [f.lower() for f in args.services]
        services = {
            name: url
            for name, url in SERVICES.items()
            if any(f in name.lower() for f in filters)
        }
        if not services:
            print(f"No matching services found for: {args.services}", file=sys.stderr)
            return 1

    if not args.json:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        label = f"TV Health Check — {ts}"
        print(f"{BOLD}{label}{RESET}" if not args.no_color else label)

    results = run_checks(services, timeout=args.timeout)

    if args.json:
        print_json(results)
    else:
        print_table(results, no_color=args.no_color)
        down = [r for r in results if r.status == STATUS_DOWN]
        degraded = [r for r in results if r.status == STATUS_DEGRADED]
        ok = [r for r in results if r.status == STATUS_OK]
        print(f"\nSummary: {len(ok)} OK  {len(degraded)} degraded  {len(down)} down\n")

    any_down = any(r.status == STATUS_DOWN for r in results)
    return 1 if any_down else 0


if __name__ == "__main__":
    sys.exit(main())
