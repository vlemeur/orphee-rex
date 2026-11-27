"""Scrape public ASNR sources into the local raw cache (network, rate-limited).

Thin CLI over src/orphee/crawl.py + src/orphee/net. Full histories: incident
notices ~3.2k HTML pages, inspection letters ~18k PDFs behind ~1.2k listing
pages; at the robots.txt Crawl-delay (10 s) a full run takes hours — it is
resumable (disk cache + manifest), so run it in the background:
    nohup just scrape --source inspection_letters_inb > /tmp/orphee-scrape.log 2>&1 &
Examples:
    uv run python scripts/scrape.py --limit 50    # smoke
    uv run python scripts/scrape.py               # full history
    uv run python scripts/scrape.py --source inspection_letters_inb \
        --max-pages 3 --limit 20   # smoke on the letters listing
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from orphee import crawl, sources
from orphee.net import robots
from orphee.net.http import HttpClient

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=sorted(sources.SOURCES), default="incident_notices"
    )
    parser.add_argument(
        "--raw-dir", default=None, help="default data/raw/asnr/<source>"
    )
    parser.add_argument("--cache-dir", default=None, help="default <raw-dir>/cache")
    parser.add_argument(
        "--limit", type=int, default=None, help="max documents to fetch"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="seconds between requests (default: robots.txt Crawl-delay)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="max paginated listing pages to crawl (listing-mode sources only)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    spec = sources.SOURCES[args.source]
    raw_dir = Path(args.raw_dir or f"data/raw/asnr/{spec.name}")
    cache_dir = Path(args.cache_dir or raw_dir / "cache")

    # Bootstrap (robots.txt + sitemaps: a handful of requests, 1 s apart),
    # then switch to the robots Crawl-delay for the bulk document fetch.
    bootstrap = HttpClient(cache_dir=cache_dir, min_interval_s=1.0)
    delay = args.delay
    if delay is None:
        try:
            policy = robots.parse_robots(bootstrap.get_text(f"{spec.base}/robots.txt"))
            delay = (
                policy.crawl_delay_s
                if policy.crawl_delay_s is not None
                else spec.default_crawl_delay_s
            )
        except Exception:
            logger.warning(
                "robots.txt unreachable, using default delay %.1fs",
                spec.default_crawl_delay_s,
            )
            delay = spec.default_crawl_delay_s
    logger.info("crawl delay: %.1fs", delay)

    urls = crawl.enumerate_urls(bootstrap, spec, max_listing_pages=args.max_pages)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "urls.txt").write_text("\n".join(urls) + "\n", encoding="utf-8")

    client = HttpClient(cache_dir=cache_dir, min_interval_s=delay)
    summary = crawl.fetch_urls(client, raw_dir, urls, limit=args.limit)
    print(
        f"\n{args.source}: {summary.enumerated} urls enumerated, "
        f"{summary.fetched} fetched, {summary.cache_hits} cache hits, "
        f"{summary.errors} errors in {summary.elapsed_s:.0f}s"
    )
    print(f"raw cache: {cache_dir} · manifest: {raw_dir / 'manifest.jsonl'}")


if __name__ == "__main__":
    main()
