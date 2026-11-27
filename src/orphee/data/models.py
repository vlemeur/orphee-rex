"""Pydantic models for scraped ASNR documents.

Every document carries ``max_freshness`` (anti-leakage metadata): the newest
information date it carries (its update date if any, else its publication
date). Eval pipelines must never use a document whose max_freshness is after
the eval cutoff.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, computed_field


class AsnrDocument(BaseModel):
    """Common fields of every scraped ASNR document (HTML article or PDF)."""

    id: str  # URL slug, or PDF file stem (e.g. INSSN-CAE-2025-0257)
    url: str
    title: str
    published: date
    updated: date | None = None

    @computed_field
    @property
    def max_freshness(self) -> date:
        return self.updated or self.published


class ControlArticle(AsnrDocument):
    """One "actualité du contrôle" HTML article (incident notice, outage notice).

    Parsed from the Ibexa CMS structure (ArticleHeader / Tooltip / RichText /
    AsideBlock-incident-level); ``ines_level`` is only set for events graded
    on the INES scale (INB and transports — not patients).
    """

    source: str
    site: str | None = None
    site_detail: str | None = None
    chapo: str | None = None
    ines_level: int | None = None
    body: str


class IncidentNotice(ControlArticle):
    """One avis d'incident INB, parsed from its ASNR HTML page."""

    source: Literal["asnr-incident-notice"] = "asnr-incident-notice"


class TransportIncidentNotice(ControlArticle):
    """Avis d'incident pour un transport lié aux installations nucléaires."""

    source: Literal["asnr-transport-incident-notice"] = "asnr-transport-incident-notice"


class MedicalIncidentNotice(ControlArticle):
    """Avis d'incident du domaine médical (ESR de radioprotection)."""

    source: Literal["asnr-medical-incident-notice"] = "asnr-medical-incident-notice"


class PatientRadiotherapyIncidentNotice(ControlArticle):
    """Avis d'incident affectant un patient en radiothérapie."""

    source: Literal["asnr-patient-radiotherapy-incident-notice"] = (
        "asnr-patient-radiotherapy-incident-notice"
    )


class IndustrialIncidentNotice(ControlArticle):
    """Avis d'incident hors installations nucléaires (domaine industriel)."""

    source: Literal["asnr-industrial-incident-notice"] = (
        "asnr-industrial-incident-notice"
    )


class OutageNotice(ControlArticle):
    """Avis d'information sur un arrêt de réacteur de centrale nucléaire."""

    source: Literal["asnr-reactor-outage-notice"] = "asnr-reactor-outage-notice"
    reactor: str | None = None  # e.g. "réacteur 1", from the title
    outage_kind: str | None = None  # e.g. "visite partielle", from the title


class InspectionLetter(AsnrDocument):
    """One lettre de suite d'inspection INB, parsed from its ASNR PDF.

    ``published`` is the inspection date carried by the letter (the listing
    shows the same date); the letter's own signature date is not parsed.
    """

    source: Literal["asnr-inspection-letter"] = "asnr-inspection-letter"
    reference: str  # e.g. INSSN-CAE-2025-0257
    division: str | None = None  # ASNR division code, e.g. CAE
    inspection_date: date | None = None
    theme: str | None = None  # inspection theme, e.g. "surveillance des activités"
    site: str | None = None
    site_detail: str | None = None
    pdf_pages: int
    body: str  # full text extracted from the PDF
