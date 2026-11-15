"""Static guards for the V2 non-negotiable boundaries."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2_CODE = [ROOT / "packages", ROOT / "services", ROOT / "apps/web/app", ROOT / "apps/web/lib"]
FORBIDDEN = re.compile(
    r"(tvdatafeed|tradingview_ta|tradingview-ta|mcp\.tradingview\.com|"
    r"scanner\.tradingview\.com|data\.tradingview\.com|prodata\.tradingview\.com)", re.I)


def _files() -> list[Path]:
    out: list[Path] = []
    for base in V2_CODE:
        if base.exists():
            out += [p for p in base.rglob("*")
                    if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".js", ".json", ".toml"}
                    and "node_modules" not in p.parts and ".next" not in p.parts]
    return out


def test_no_tradingview_data_path_in_v2_code() -> None:
    hits = [str(p.relative_to(ROOT)) for p in _files() if FORBIDDEN.search(p.read_text())]
    assert hits == [], f"TradingView data source referenced in execution-side code: {hits}"


def test_secrets_are_gitignored() -> None:
    for path in (".env", ".mcp.json", "secrets/mt5.token", "x.token"):
        r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
        assert r.returncode == 0, f"{path} is not gitignored"


def test_compose_publishes_only_the_proxy() -> None:
    compose = (ROOT / "infra/docker/docker-compose.yml").read_text()
    published = re.findall(r"^\s*-\s*\"?([\d.]*:?\d+:\d+)\"?\s*$", compose, re.M)
    assert published, "expected the reverse proxy to publish ports"
    assert "22346" not in compose and "22345" not in compose
    for svc in ("postgres", "redis", "api", "worker", "web"):
        block = re.search(rf"^  {svc}:\n((?:    .*\n|\n)+)", compose, re.M)
        assert block, svc
        assert "ports:" not in block.group(1), f"{svc} must not publish ports"
