"""Disk cache for Mistral API payloads (budget 0 EUR).

API payload cache: results/cache/mistral/<sha256(payload)>.json — a cache hit
never touches the network (never re-embedded / never re-chatted by default).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_API_CACHE_DIR = "results/cache/mistral"


def payload_key(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class JsonDiskCache:
    """Tiny JSON-file disk cache: <key>.json -> parsed content."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            return None

    def put(self, key: str, value: Any) -> None:
        self._path(key).write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )

    def count(self) -> int:
        return sum(1 for _ in self.root.glob("*.json"))
