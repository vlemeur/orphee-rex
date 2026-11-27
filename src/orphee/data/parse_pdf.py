"""Parse ASNR inspection-letter PDFs (lettres de suite d'inspection) into records.

The letters are served as PDF downloads (``/content/download/<id>/download_file/
INSSN-<DIV>-<YYYY>-<NNNN>.pdf``), not as HTML pages. Text is extracted with
pypdf; the metadata (reference, inspection date, theme) is parsed from the
letter's own first page, which follows a stable ASNR layout:
"Lettre de suite de l'inspection du 27 février 2025 sur le thème de ...".
``published`` = the inspection date (the date the listing shows for the item),
falling back to the letter's signature date ("Lyon, le 23 octobre 2026").
A PDF without an INSSN reference or any date raises PdfParseError.
"""

from __future__ import annotations

import io
import re
from datetime import date

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from orphee.data.models import InspectionLetter
from orphee.data.parse import (
    ParseError,
    clean_body,
    clean_inline,
    parse_fr_date,
    parse_fr_date_text,
)

REF_RE = re.compile(r"\bINSSN-([A-Z]{3})-(\d{4})-(\d+)\b")
# Real letter openings seen in the wild: "inspection du 27/02/2025",
# "inspection inopinée du 17/09/2026"
INSPECTION_DATE_NUM_RE = re.compile(
    r"inspections?\s+(?:inopin[ée]e\s+)?du\s+(\d{1,2}/\d{1,2}/\d{4})", re.I
)
# "inspection du 27 février 2025", "inspection des 21 et 22 octobre 2026",
# "inspection du 1er mars 2026"
INSPECTION_DATE_TEXT_RE = re.compile(
    r"inspections?\s+(?:inopin[ée]e\s+)?(?:du|des|de la)\s+(\d{1,2}(?:er)?)"
    r"(?:\s+et\s+\d{1,2}(?:er)?)?\s+([a-zàâäéèêëîïôöùûüç]+)\s+(\d{4})",
    re.I,
)
# Letter (signature) date, fallback for published: "Lyon, le 23 octobre 2026"
LETTER_DATE_RE = re.compile(
    r"[A-ZÀ-Þ][a-zà-ÿ]+,\s*le\s+(\d{1,2}(?:er)?)"
    r"\s+([a-zàâäéèêëîïôöùûüç]+)\s+(\d{4})",
    re.I,
)
# Theme on flattened text: "sur le thème de la surveillance des activités · N° dossier"
# or "sur le thème « Maîtrise des réactions nucléaires en chaine » N° dossier".
# "th[eè]me" tolerates accent-less extraction (some PDFs lose diacritics).
THEME_RE = re.compile(
    r"sur le th[eè]me\s+(?:de\s+)?[«“\"]?\s*(.+?)\s*[»”\"]?\s*"
    r"(?:·|[Nn][o°]\s*dossier|$)",
    re.I,
)


class PdfParseError(ParseError):
    """The PDF cannot be parsed into an inspection letter."""


def parse_inspection_date(flat_text: str) -> date | None:
    """Inspection date from flattened text ('27/02/2025' or '27 février 2025')."""

    num = INSPECTION_DATE_NUM_RE.search(flat_text)
    if num:
        return parse_fr_date(num.group(1))
    text = INSPECTION_DATE_TEXT_RE.search(flat_text)
    if text:
        return parse_fr_date_text(text.group(1), text.group(2), text.group(3))
    return None


def parse_letter_date(flat_text: str) -> date | None:
    """Signature date ('Lyon, le 23 octobre 2026') — published fallback."""
    match = LETTER_DATE_RE.search(flat_text)
    if match:
        return parse_fr_date_text(match.group(1), match.group(2), match.group(3))
    return None


def parse_inspection_letter(pdf_bytes: bytes, url: str) -> InspectionLetter:
    """Parse one lettre de suite d'inspection PDF. Raises PdfParseError if unusable."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, OSError) as exc:
        raise PdfParseError(f"unreadable PDF: {url} ({exc})") from exc
    text = "\n".join(pages)
    if not text.strip():
        raise PdfParseError(f"no extractable text: {url}")
    flat = re.sub(r"\s+", " ", text)

    ref_match = REF_RE.search(flat)
    if not ref_match:
        raise PdfParseError(f"no INSSN reference: {url}")
    reference = ref_match.group(0)
    division = ref_match.group(1)

    inspection_date = parse_inspection_date(flat)
    letter_date = parse_letter_date(flat)
    published = inspection_date or letter_date
    if published is None:
        raise PdfParseError(f"no inspection or letter date: {url}")

    theme_match = THEME_RE.search(flat)
    theme = clean_inline(theme_match.group(1)) if theme_match else None

    filename = url.rstrip("/").rsplit("/", 1)[-1]
    doc_id = filename.removesuffix(".pdf")
    title = f"Lettre de suite d'inspection {reference}"
    if theme:
        title = f"{title} — {theme}"
    return InspectionLetter(
        id=doc_id,
        url=url,
        title=title,
        published=published,
        reference=reference,
        division=division,
        inspection_date=inspection_date,
        theme=theme,
        site=None,  # the recipient address is not reliably parseable; see listing
        site_detail=None,
        pdf_pages=len(pages),
        body=clean_body(text),
    )
