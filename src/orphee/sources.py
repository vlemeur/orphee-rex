"""Registry of the public ASNR sources to scrape (URLs only; parsing lands later).

incident_notices first: the avis d'incident INB published on
reglementation-controle.asnr.fr (server-rendered HTML, sitemap + RSS).
"""

from __future__ import annotations

from dataclasses import dataclass

ASNR_BASE = "https://reglementation-controle.asnr.fr"
INCIDENT_NOTICES_PATH = (
    "/controle/actualites-du-controle/installations-nucleaires"
    "/avis-d-incident-des-installations-nucleaires"
)


@dataclass(frozen=True)
class SourceSpec:
    """URL-level description of one scrapable source."""

    name: str
    base: str
    listing_path: str  # paginated listing page (?page=N) — not a document
    notice_path_prefix: str  # URL prefix of the individual documents
    rss_path: str | None  # incremental feed (recent documents only)
    default_crawl_delay_s: float  # fallback when robots.txt is unreachable


INCIDENT_NOTICES = SourceSpec(
    name="incident_notices",
    base=ASNR_BASE,
    listing_path=INCIDENT_NOTICES_PATH,
    notice_path_prefix=INCIDENT_NOTICES_PATH + "/",
    rss_path="/rss/avis-incidents-INB",
    # robots.txt of reglementation-controle.asnr.fr announces Crawl-delay: 10
    default_crawl_delay_s=10.0,
)

SOURCES: dict[str, SourceSpec] = {s.name: s for s in (INCIDENT_NOTICES,)}
