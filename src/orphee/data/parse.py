"""Parse ASNR incident-notice HTML pages into IncidentNotice records.

Selectors target the Ibexa CMS structure verified on the real pages during
recon: div.ArticleHeader (title, publication/update dates, site tooltip),
p.AsideBlock-incident-level (INES level), div.RichText (body). Missing
optional fields become None (counted in the ingest report); a page without
a title, publication date or body raises ParseError.
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from orphee.data.models import IncidentNotice

DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")
UPDATED_RE = re.compile(r"dernière mise à jour\s*:?\s*(\d{2}/\d{2}/\d{4})", re.I)
INES_RE = re.compile(r"niveau\s*(\d+)", re.I)


class ParseError(Exception):
    """The page cannot be parsed into a notice (missing title/date/body)."""


def _clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_body(text: str) -> str:
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _parse_fr_date(s: str) -> date:
    day, month, year = s.split("/")
    return date(int(year), int(month), int(day))


def parse_notice(html: str, url: str) -> IncidentNotice:
    """Parse one notice page. Raises ParseError if title/date/body are absent."""
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one("div.ArticleHeader") or soup

    title_el = header.select_one("h1.ArticleHeader-title")
    title = _clean_inline(title_el.get_text()) if title_el else ""
    if not title:
        og = soup.select_one("meta[property='og:title']")
        if og and og.get("content"):
            title = _clean_inline(str(og["content"]))
    if not title:
        raise ParseError(f"no title: {url}")

    date_el = header.select_one("p.ArticleHeader-date")
    found = DATE_RE.search(date_el.get_text()) if date_el else None
    if not found:
        raise ParseError(f"no publication date: {url}")
    published = _parse_fr_date(found.group(0))

    updated_match = UPDATED_RE.search(header.get_text(" "))
    updated = _parse_fr_date(updated_match.group(1)) if updated_match else None

    site_el = header.select_one("span.Tooltip-title") or soup.select_one(
        "span.Tooltip-title"
    )
    site = _clean_inline(site_el.get_text()) if site_el else None
    detail_el = header.select_one("span.Tooltip-description") or soup.select_one(
        "span.Tooltip-description"
    )
    site_detail = _clean_inline(detail_el.get_text()) if detail_el else None

    ines_el = soup.select_one("p.AsideBlock-incident-level")
    ines_level = None
    if ines_el:
        ines_match = INES_RE.search(ines_el.get_text())
        ines_level = int(ines_match.group(1)) if ines_match else None

    chapo_el = header.select_one("div.ArticleHeader-chapo")
    chapo = _clean_body(chapo_el.get_text("\n")) if chapo_el else ""
    chapo = chapo or None

    body_el = soup.select_one("div.RichText")
    if body_el is None:
        raise ParseError(f"no body (div.RichText): {url}")
    body = _clean_body(body_el.get_text("\n"))
    if not body:
        raise ParseError(f"empty body: {url}")

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return IncidentNotice(
        id=slug,
        url=url,
        title=title,
        published=published,
        updated=updated,
        site=site,
        site_detail=site_detail,
        ines_level=ines_level,
        chapo=chapo,
        body=body,
    )
