"""Load a project-root .env into os.environ (setdefault — never overrides).

Secrets live in .env (gitignored) and are only ever read through os.environ;
values are never logged, printed, or committed. Each CLI script calls
``load_env()`` once at startup so ``just <recipe>`` works without exporting
anything by hand.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env(path: Path | str = ".env") -> int:
    """Load KEY=VALUE lines from path into os.environ (existing vars win).

    Returns the number of variables set. A missing file returns 0. Blank
    lines and #-comments are ignored; surrounding quotes are stripped.
    """
    path = Path(path)
    if not path.is_file():
        return 0
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            n += 1
    return n
