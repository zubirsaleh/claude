"""Append-only JSONL decision log."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
