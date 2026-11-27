"""Parse ASNR HTML "actualité du contrôle" pages into ControlArticle records.

Selectors target the Ibexa CMS structure verified on the real pages during
recon: div.ArticleHeader (title, publication/update dates, site tooltip),
p.AsideBlock-incident-level (INES level, INB/transports only), div.RichText
(body). Missing optional fields become None (counted in the ingest report);
a page without a title, publication date or body raises ParseError.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, TypeVar

from bs4 import BeautifulSoup

from orphee.data.models import (
    ControlArticle,
    IncidentNotice,
    IndustrialIncidentNotice,
    MedicalIncidentNotice,
    OutageNotice,
    PatientRadiotherapyIncidentNotice,
)

DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")
UPDATED_RE = re.compile(r"dernière mise à jour\s*:?\s*(\d{2}/\d{2}/\d{4})", re.I)
INES_RE = re.compile(r"niveau\s*(\d+)", re.I)
REACTOR_RE = re.compile(r"réacteur\s+(?:n°\s*|n\s*)?(\d+)", re.I)
OUTAGE_KIND_RE = re.compile(r"arrêt pour (.+?) du réacteur", re.I)

T = TypeVar("T", bound=ControlArticle)


class ParseError(Exception):
    """The page cannot be parsed into a document (missing title/date/body)."""


def clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_body(text: str) -> str:
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def parse_fr_date(s: str) -> date:
    """Parse a numeric French date: JJ/MM/AAAA."""
    day, month, year = s.split("/")
    return date(int(year), int(month), int(day))


FR_MONTHS = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}


def parse_fr_date_text(day: str, month: str, year: str) -> date:
    """Parse a French date written out: '27'/'1er', 'février', '2025'."""
    day_num = int(re.sub(r"[^\d]", "", day))
    return date(int(year), FR_MONTHS[month.strip().lower()], day_num)


def _article_fields(html: str, url: str) -> dict[str, Any]:
    """Common ControlArticle fields of one Ibexa article page."""
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one("div.ArticleHeader") or soup

    title_el = header.select_one("h1.ArticleHeader-title")
    title = clean_inline(title_el.get_text()) if title_el else ""
    if not title:
        og = soup.select_one("meta[property='og:title']")
        if og and og.get("content"):
            title = clean_inline(str(og["content"]))
    if not title:
        raise ParseError(f"no title: {url}")

    date_el = header.select_one("p.ArticleHeader-date")
    found = DATE_RE.search(date_el.get_text()) if date_el else None
    if not found:
        raise ParseError(f"no publication date: {url}")
    published = parse_fr_date(found.group(0))

    updated_match = UPDATED_RE.search(header.get_text(" "))
    updated = parse_fr_date(updated_match.group(1)) if updated_match else None

    site_el = header.select_one("span.Tooltip-title") or soup.select_one(
        "span.Tooltip-title"
    )
    site = clean_inline(site_el.get_text()) if site_el else None
    detail_el = header.select_one("span.Tooltip-description") or soup.select_one(
        "span.Tooltip-description"
    )
    site_detail = clean_inline(detail_el.get_text()) if detail_el else None

    ines_el = soup.select_one("p.AsideBlock-incident-level")
    ines_level = None
    if ines_el:
        ines_match = INES_RE.search(ines_el.get_text())
        ines_level = int(ines_match.group(1)) if ines_match else None

    chapo_el = header.select_one("div.ArticleHeader-chapo")
    chapo = clean_body(chapo_el.get_text("\n")) if chapo_el else ""
    chapo = chapo or None

    body_el = soup.select_one("div.RichText")
    if body_el is None:
        raise ParseError(f"no body (div.RichText): {url}")
    body = clean_body(body_el.get_text("\n"))
    if not body:
        raise ParseError(f"empty body: {url}")

    return {
        "title": title,
        "published": published,
        "updated": updated,
        "site": site,
        "site_detail": site_detail,
        "ines_level": ines_level,
        "chapo": chapo,
        "body": body,
    }


def _build[T: ControlArticle](
    model_cls: type[T], html: str, url: str, **extra: Any
) -> T:
    """Build a ControlArticle subclass from an Ibexa article page."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return model_cls(id=slug, url=url, **_article_fields(html, url), **extra)


def parse_notice(html: str, url: str) -> IncidentNotice:
    """Parse one avis d'incident INB page."""
    return _build(IncidentNotice, html, url)


def parse_medical_notice(html: str, url: str) -> MedicalIncidentNotice:
    return _build(MedicalIncidentNotice, html, url)


def parse_patient_radiotherapy_notice(
    html: str, url: str
) -> PatientRadiotherapyIncidentNotice:
    return _build(PatientRadiotherapyIncidentNotice, html, url)


def parse_industrial_notice(html: str, url: str) -> IndustrialIncidentNotice:
    return _build(IndustrialIncidentNotice, html, url)


def parse_outage(html: str, url: str) -> OutageNotice:
    """Parse one arrêt de réacteur page; reactor/kind come from the title."""
    probe = _build(OutageNotice, html, url)
    reactor = None
    reactor_match = REACTOR_RE.search(probe.title)
    if reactor_match:
        reactor = f"réacteur {reactor_match.group(1)}"
    kind_match = OUTAGE_KIND_RE.search(probe.title)
    outage_kind = clean_inline(kind_match.group(1)) if kind_match else None
    return probe.model_copy(update={"reactor": reactor, "outage_kind": outage_kind})
