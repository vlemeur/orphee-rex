"""Pydantic models for scraped ASNR documents."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, computed_field


class IncidentNotice(BaseModel):
    """One avis d'incident INB, parsed from its ASNR HTML page.

    max_freshness is the anti-leakage metadata: the newest information date
    the document carries (its update date if any, else its publication date).
    Eval pipelines must never use a document whose max_freshness is after
    the eval cutoff.
    """

    id: str  # URL slug
    source: Literal["asnr-incident-notice"] = "asnr-incident-notice"
    url: str
    title: str
    published: date
    updated: date | None = None
    site: str | None = None
    site_detail: str | None = None
    ines_level: int | None = None
    chapo: str | None = None
    body: str

    @computed_field
    @property
    def max_freshness(self) -> date:
        return self.updated or self.published
