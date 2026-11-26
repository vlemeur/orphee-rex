"""Minimal robots.txt parser — only what the crawler needs.

Extracts the Crawl-delay and Disallow rules of the ``User-agent: *`` group,
plus the (group-independent) Sitemap lines. Not a full RFC 9309 parser.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class RobotsPolicy:
    crawl_delay_s: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    disallow: list[str] = field(default_factory=list)

    def is_allowed(self, url: str) -> bool:
        """True unless the URL matches a Disallow rule of the '*' group."""
        parts = urlsplit(url)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        return not any(target.startswith(rule) for rule in self.disallow)


def parse_robots(text: str) -> RobotsPolicy:
    policy = RobotsPolicy()
    in_star_group = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            in_star_group = value == "*"
        elif key == "crawl-delay" and in_star_group:
            with contextlib.suppress(ValueError):
                policy.crawl_delay_s = float(value)
        elif key == "sitemap":
            if value:
                policy.sitemaps.append(value)
        elif key == "disallow" and in_star_group and value:
            policy.disallow.append(value)
    return policy
