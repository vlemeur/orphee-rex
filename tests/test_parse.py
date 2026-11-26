"""Tests for orphee.data.parse — offline, synthetic HTML fixture."""

from datetime import date

import pytest

from orphee.data.models import IncidentNotice
from orphee.data.parse import ParseError, parse_notice

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
