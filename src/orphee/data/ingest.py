"""Ingest the raw ASNR cache (HTML pages and PDFs) into parsed JSONL — offline.

Source of truth = the HttpClient disk cache under raw_dir/cache/: each
<sha256>.json sidecar carries the url (+ content_type), each <sha256>.gz the
body (both written and closed per page, so a mid-scrape ingest sees every
fetched page). The scrape manifest stays an append-only audit log. Pages are
filtered on url_prefix, parsed with the parser of the given source (HTML
article parsers, or the PDF parser for inspection letters), and written one
JSON record per line. Unparseable pages / unreadable sidecars are counted in
the report, never fatal.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from orphee.data import parse as html_parse
from orphee.data.models import AsnrDocument, ControlArticle
from orphee.data.parse import ParseError
from orphee.data.parse_pdf import parse_inspection_letter

# Optional fields tracked in the report; only those present on the parsed
# model are counted (e.g. ines_level only for ControlArticle subclasses).
OPTIONAL_FIELDS = (
    "updated",
    "site",
    "site_detail",
    "ines_level",
    "chapo",
    "theme",
    "inspection_date",
    "reactor",
    "outage_kind",
    "division",
)

HTML_PARSERS: dict[str, Callable[[str, str], ControlArticle]] = {
    "incident_notices": html_parse.parse_notice,
    "reactor_outages": html_parse.parse_outage,
    "medical_incidents": html_parse.parse_medical_notice,
    "patient_radiotherapy_incidents": html_parse.parse_patient_radiotherapy_notice,
    "industrial_incidents": html_parse.parse_industrial_notice,
}

# Sources whose documents are PDFs (parsed with the PDF parser).
PDF_SOURCES = {"inspection_letters_inb"}


@dataclass
class IngestReport:
    total: int = 0  # cache entries considered (after prefix filter)
    parsed: int = 0
    skipped: int = 0  # malformed sidecars (torn trailing line mid-scrape)
    errors: list[str] = field(default_factory=list)
    missing: Counter[str] = field(default_factory=Counter)
    ines_counts: Counter[int] = field(default_factory=Counter)
    published_min: date | None = None
    published_max: date | None = None
    body_chars: int = 0


def ingest_cache(
    raw_dir: Path | str,
    out_path: Path | str,
    limit: int | None = None,
    url_prefix: str | None = None,
    source: str | None = None,
) -> IngestReport:
    """Parse the cached documents of raw_dir into out_path (JSONL).

    Cache sidecars (<sha256>.json, each with its url) drive the enumeration,
    so a mid-scrape run sees every page already fetched. url_prefix filters
    documents; limit caps how many are read. ``source`` selects the parser:
    HTML article parsers per source name, PDF parser for PDF_SOURCES; default
    is the incident-notice HTML parser.
    """
    raw_dir = Path(raw_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = IngestReport()
    cache_dir = raw_dir / "cache"
    html_parser = HTML_PARSERS.get(source or "", html_parse.parse_notice)
    is_pdf = source in PDF_SOURCES
    entries: list[tuple[str, str]] = []  # (url, key)
    if cache_dir.exists():
        for meta_path in sorted(cache_dir.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError, OSError:
                report.skipped += 1  # torn sidecar mid-write
                continue
            url = str(meta.get("url", ""))
            if url_prefix is not None and not url.startswith(url_prefix):
                continue
            entries.append((url, meta_path.stem))
    if limit is not None:
        entries = entries[:limit]
    with out_path.open("w", encoding="utf-8") as out:
        for url, key in entries:
            report.total += 1
            gz = cache_dir / f"{key}.gz"
            try:
                raw = gzip.decompress(gz.read_bytes())
                doc: AsnrDocument = (
                    parse_inspection_letter(raw, url)
                    if is_pdf
                    else html_parser(raw.decode("utf-8", "replace"), url)
                )
            except (ParseError, OSError, ValueError) as exc:
                report.errors.append(f"{url}: {exc}")
                continue
            out.write(doc.model_dump_json() + "\n")
            report.parsed += 1
            model_fields = type(doc).model_fields
            for name in OPTIONAL_FIELDS:
                if name in model_fields and getattr(doc, name) is None:
                    report.missing[name] += 1
            ines_level = getattr(doc, "ines_level", None)
            if isinstance(ines_level, int):
                report.ines_counts[ines_level] += 1
            body = getattr(doc, "body", "")
            report.body_chars += len(body)
            if report.published_min is None or doc.published < report.published_min:
                report.published_min = doc.published
            if report.published_max is None or doc.published > report.published_max:
                report.published_max = doc.published
    return report
