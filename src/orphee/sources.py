"""Registry of the public ASNR sources to scrape.

All sources live on reglementation-controle.asnr.fr (Ibexa CMS, robots.txt
Crawl-delay: 10 s; /content/download/ is allowed). Two enumeration modes:

- sitemap: document URLs are read from /sitemap.xml and filtered on
  notice_path_prefix (HTML articles: incident notices, outage notices...);
- paginated listing: when doc_url_regex is set, documents are NOT in the
  sitemap — the listing pages (?page=0..N) are crawled and every link whose
  URL matches the regex is kept (inspection letters served as PDF under
  /content/download/.../INSSN-*.pdf).
"""

from __future__ import annotations

from dataclasses import dataclass

ASNR_BASE = "https://reglementation-controle.asnr.fr"
_CONTROLE = "/controle/actualites-du-controle"
_INB = _CONTROLE + "/installations-nucleaires"

INCIDENT_NOTICES_PATH = _INB + "/avis-d-incident-des-installations-nucleaires"


@dataclass(frozen=True)
class SourceSpec:
    """URL-level description of one scrapable source."""

    name: str
    base: str
    listing_path: str  # paginated listing page (?page=N) — not a document
    notice_path_prefix: str  # URL prefix of the individual documents
    rss_path: str | None  # incremental feed (recent documents only)
    default_crawl_delay_s: float  # fallback when robots.txt is unreachable
    # When set, documents are enumerated by crawling the paginated listing
    # and matching link URLs against this regex (sitemap does not list them).
    doc_url_regex: str | None = None
    listing_max_pages: int = 5000  # safety bound for the paginated listing


INCIDENT_NOTICES = SourceSpec(
    name="incident_notices",
    base=ASNR_BASE,
    listing_path=INCIDENT_NOTICES_PATH,
    notice_path_prefix=INCIDENT_NOTICES_PATH + "/",
    rss_path="/rss/avis-incidents-INB",
    # robots.txt of reglementation-controle.asnr.fr announces Crawl-delay: 10
    default_crawl_delay_s=10.0,
)

REACTOR_OUTAGES = SourceSpec(
    name="reactor_outages",
    base=ASNR_BASE,
    listing_path=_INB + "/arret-de-reacteurs-de-centrales-nucleaires",
    notice_path_prefix=_INB + "/arret-de-reacteurs-de-centrales-nucleaires/",
    rss_path="/rss/arrets_reacteur",
    default_crawl_delay_s=10.0,
)

INSPECTION_LETTERS_INB = SourceSpec(
    name="inspection_letters_inb",
    base=ASNR_BASE,
    listing_path=_INB + "/lettres-de-suite-d-inspection-des-installations-nucleaires",
    notice_path_prefix="/content/download/",  # documents are PDF downloads
    rss_path="/rss/lettre-de-suite-inspection-INB",
    default_crawl_delay_s=10.0,
    # ~18k letters (2002->now) on ~1.2k listing pages; the PDFs are not in
    # the sitemap, so enumerate by crawling listing?page=N and matching links.
    doc_url_regex=r"/content/download/\d+/download_file/INSSN-[A-Z]+-\d{4}-\d+\.pdf$",
    listing_max_pages=5000,
)

# NOTE: there is no separate "transport incidents" source: the transport
# listing (transport-de-substances-radioactives/...) is only a filtered VIEW
# whose items are hosted under avis-d-incident-des-installations-nucleaires/
# (verified on the real listing HTML) — i.e. already covered by
# INCIDENT_NOTICES. The RSS avis-incidents-transports likewise republishes them.

MEDICAL_INCIDENTS = SourceSpec(
    name="medical_incidents",
    base=ASNR_BASE,
    listing_path=_CONTROLE + "/activites-medicales/avis-d-incident-domaine-medical",
    notice_path_prefix=_CONTROLE
    + "/activites-medicales/avis-d-incident-domaine-medical/",
    rss_path="/rss/avis-incident-domaine-medical",
    default_crawl_delay_s=10.0,
)

PATIENT_RADIOTHERAPY_INCIDENTS = SourceSpec(
    name="patient_radiotherapy_incidents",
    base=ASNR_BASE,
    listing_path=(
        _CONTROLE
        + "/activites-medicales/avis-d-incident-affectant-un-patient-en-radiotherapie"
    ),
    notice_path_prefix=(
        _CONTROLE
        + "/activites-medicales/avis-d-incident-affectant-un-patient-en-radiotherapie/"
    ),
    rss_path="/rss/avis-incidents-patients-radiotherapie",
    default_crawl_delay_s=10.0,
)

INDUSTRIAL_INCIDENTS = SourceSpec(
    name="industrial_incidents",
    base=ASNR_BASE,
    listing_path=(
        _CONTROLE
        + "/activites-industrielles/avis-d-incident-hors-installations-nucleaires"
    ),
    notice_path_prefix=_CONTROLE
    + "/activites-industrielles/avis-d-incident-hors-installations-nucleaires/",
    rss_path="/rss/avis-incidents-domaine-industriel",
    default_crawl_delay_s=10.0,
)

SOURCES: dict[str, SourceSpec] = {
    s.name: s
    for s in (
        INCIDENT_NOTICES,
        REACTOR_OUTAGES,
        INSPECTION_LETTERS_INB,
        MEDICAL_INCIDENTS,
        PATIENT_RADIOTHERAPY_INCIDENTS,
        INDUSTRIAL_INCIDENTS,
    )
}
