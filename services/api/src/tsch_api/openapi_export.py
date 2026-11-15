"""Write the OpenAPI document to packages/contracts/openapi.json (checked in CI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Settings
from .db import make_engine
from .main import create_app


def render() -> str:
    app = create_app(Settings(database_url="sqlite://"), engine=make_engine("sqlite://"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("packages/contracts/openapi.json")
    out.write_text(render())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
