"""Tests for orphee.data.parse — offline, synthetic HTML fixture."""

from datetime import date

import pytest

from orphee.data.models import IncidentNotice, MedicalIncidentNotice, OutageNotice
from orphee.data.parse import (
    ParseError,
    parse_fr_date_text,
    parse_medical_notice,
    parse_notice,
    parse_outage,
)

URL = (
    "https://reglementation-controle.asnr.fr/controle/actualites-du-controle"
    "/installations-nucleaires/avis-d-incident-des-installations-nucleaires"
    "/evenement-test"
)


def test_parse_notice_full(synthetic_notice_html: str) -> None:
    notice = parse_notice(synthetic_notice_html, URL)
    assert notice.id == "evenement-test"
    assert notice.source == "asnr-incident-notice"
    assert notice.url == URL
    assert notice.title == "Événement significatif test"
    assert notice.published == date(2017, 2, 15)
    assert notice.updated == date(2021, 9, 3)
    assert notice.max_freshness == notice.updated
    assert notice.site == "Centrale nucléaire de Test"
    assert notice.site_detail == "Réacteurs de 900 MWe - EDF"
    assert notice.ines_level == 2
    assert notice.chapo == "Résumé chapo."
    # body keeps the lexicon span's visible text, never its data-content attr
    assert "niveau 2" in notice.body
    assert "INES" in notice.body
    assert "lexique" not in notice.body


def test_missing_ines_and_update(synthetic_notice_html: str) -> None:
    html = synthetic_notice_html.replace(
        '<p class="AsideBlock-incident-level">Niveau 2</p>', ""
    )
    html = html.replace(
        "<div><small>Date de la dernière mise à jour : 03/09/2021</small></div>", ""
    )
    notice = parse_notice(html, URL)
    assert notice.ines_level is None
    assert notice.updated is None
    assert notice.max_freshness == notice.published


def test_title_falls_back_to_og(synthetic_notice_html: str) -> None:
    html = synthetic_notice_html.replace(
        '<h1 class="ArticleHeader-title">Événement significatif test</h1>', ""
    )
    notice = parse_notice(html, URL)
    assert notice.title == "Événement test"


def test_missing_body_raises(synthetic_notice_html: str) -> None:
    html = synthetic_notice_html.replace('<div class="RichText">', '<div class="X">')
    with pytest.raises(ParseError, match="no body"):
        parse_notice(html, URL)


def test_missing_date_raises(synthetic_notice_html: str) -> None:
    html = synthetic_notice_html.replace(
        '<p class="ArticleHeader-date">Publié le 15/02/2017</p>', ""
    )
    with pytest.raises(ParseError, match="no publication date"):
        parse_notice(html, URL)


def test_model_json_roundtrip(synthetic_notice_html: str) -> None:
    notice = parse_notice(synthetic_notice_html, URL)
    assert "max_freshness" in notice.model_dump()
    back = IncidentNotice.model_validate_json(notice.model_dump_json())
    assert back == notice


OUTAGE_URL = (
    "https://reglementation-controle.asnr.fr/controle/actualites-du-controle"
    "/installations-nucleaires/arret-de-reacteurs-de-centrales-nucleaires"
    "/arret-pour-visite-partielle-du-reacteur-12"
)


def test_parse_outage_extracts_reactor_and_kind(synthetic_outage_html: str) -> None:
    notice = parse_outage(synthetic_outage_html, OUTAGE_URL)
    assert isinstance(notice, OutageNotice)
    assert notice.source == "asnr-reactor-outage-notice"
    assert notice.id == "arret-pour-visite-partielle-du-reacteur-12"
    assert notice.reactor == "réacteur 1"
    assert notice.outage_kind == "visite partielle"
    assert notice.site == "Centrale nucléaire de Gravelines"
    assert notice.site_detail == "Réacteurs de 900 MWe - EDF"
    assert notice.published == date(2026, 5, 4)
    assert notice.ines_level is None  # outage notices carry no INES block
    assert "arrêté pour" in notice.body


def test_parse_outage_reactor_with_numero_sign(synthetic_outage_html: str) -> None:
    html = synthetic_outage_html.replace(
        "Arrêt pour visite partielle du réacteur 1",
        "Arrêt pour visite décennale du réacteur n° 3",
    )
    notice = parse_outage(html, OUTAGE_URL)
    assert notice.reactor == "réacteur 3"
    assert notice.outage_kind == "visite décennale"


def test_parse_medical_notice_without_ines(synthetic_notice_html: str) -> None:
    html = synthetic_notice_html.replace(
        '<p class="AsideBlock-incident-level">Niveau 2</p>', ""
    )
    notice = parse_medical_notice(html, URL)
    assert isinstance(notice, MedicalIncidentNotice)
    assert notice.source == "asnr-medical-incident-notice"
    assert notice.ines_level is None
    assert notice.max_freshness == notice.updated


def test_parse_fr_date_text_accented_months() -> None:
    assert parse_fr_date_text("27", "août", "2025") == date(2025, 8, 27)
    assert parse_fr_date_text("1er", "février", "2026") == date(2026, 2, 1)
    assert parse_fr_date_text("31", "décembre", "2024") == date(2024, 12, 31)


def test_parse_fr_date_text_unaccented_months_from_pdf() -> None:
    # Real letters crash here before the fix: pypdf extracted "aout" (KeyError).
    assert parse_fr_date_text("27", "aout", "2025") == date(2025, 8, 27)
    assert parse_fr_date_text("3", "fevrier", "2026") == date(2026, 2, 3)
    assert parse_fr_date_text("9", "decembre", "2025") == date(2025, 12, 9)


def test_parse_fr_date_text_mangled_month_from_pdf() -> None:
    # Real letter crash before the fix: pypdf extracted "juillet" as "juilet".
    assert parse_fr_date_text("8", "juilet", "2025") == date(2025, 7, 8)


def test_parse_fr_date_text_unknown_month_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="unknown month"):
        parse_fr_date_text("8", "xxyy", "2025")
