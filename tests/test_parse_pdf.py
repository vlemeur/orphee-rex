"""Tests for orphee.data.parse_pdf — offline, synthetic PDF fixture."""

from datetime import date

import pytest

from orphee.data.models import InspectionLetter
from orphee.data.parse_pdf import (
    PdfParseError,
    parse_inspection_date,
    parse_inspection_letter,
)

LETTER_URL = (
    "https://reglementation-controle.asnr.fr/content/download/203064"
    "/download_file/INSSN-CAE-2025-0257.pdf"
)


def test_parse_inspection_letter(synthetic_letter_pdf: bytes) -> None:
    letter = parse_inspection_letter(synthetic_letter_pdf, LETTER_URL)
    assert isinstance(letter, InspectionLetter)
    assert letter.id == "INSSN-CAE-2025-0257"
    assert letter.source == "asnr-inspection-letter"
    assert letter.url == LETTER_URL
    assert letter.reference == "INSSN-CAE-2025-0257"
    assert letter.division == "CAE"
    assert letter.inspection_date == date(2025, 2, 27)
    assert letter.published == date(2025, 2, 27)
    assert letter.max_freshness == date(2025, 2, 27)
    assert letter.theme == "la surveillance des activites"
    assert "INSSN-CAE-2025-0257" in letter.title
    assert letter.pdf_pages == 1
    assert "INSSN-CAE-2025-0257" in letter.body
    assert "Division de Caen" in letter.body


def test_parse_inspection_letter_missing_reference(synthetic_letter_pdf: bytes) -> None:
    from conftest import make_synthetic_letter_pdf

    pdf = make_synthetic_letter_pdf(["Lettre sans reference, inspection du 27/02/2025"])
    with pytest.raises(PdfParseError, match="no INSSN reference"):
        parse_inspection_letter(pdf, LETTER_URL)


def test_parse_inspection_letter_not_a_pdf() -> None:
    with pytest.raises(PdfParseError, match="unreadable PDF"):
        parse_inspection_letter(b"<html>not a pdf</html>", LETTER_URL)


def test_parse_inspection_date_formats() -> None:
    assert parse_inspection_date("inspection du 27/02/2025 sur le theme") == date(
        2025, 2, 27
    )
    assert parse_inspection_date(
        "Lettre de suite de l'inspection du 27 février 2025 sur le thème de X"
    ) == date(2025, 2, 27)
    assert parse_inspection_date(
        "inspection du 3 décembre 2024 au 5 décembre 2024"
    ) == date(2024, 12, 3)
    assert parse_inspection_date("pas de date ici") is None


def test_letter_json_roundtrip(synthetic_letter_pdf: bytes) -> None:
    letter = parse_inspection_letter(synthetic_letter_pdf, LETTER_URL)
    assert "max_freshness" in letter.model_dump()
    back = InspectionLetter.model_validate_json(letter.model_dump_json())
    assert back == letter
