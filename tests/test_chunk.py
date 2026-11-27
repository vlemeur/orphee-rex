"""Tests for orphee.data.chunk — offline, synthetic documents."""

from datetime import date
from pathlib import Path

from orphee.data.chunk import (
    chunk_corpus,
    chunk_document,
    chunk_text,
    clean_for_chunking,
    load_chunks,
)
from orphee.data.models import Chunk, IncidentNotice


def _notice(body: str) -> IncidentNotice:
    return IncidentNotice(
        id="doc-1",
        url="https://asnr.test/avis/doc-1",
        title="Événement test",
        published=date(2020, 1, 1),
        updated=date(2021, 6, 1),
        body=body,
    )


def test_clean_removes_html_and_parsing_artefacts() -> None:
    body = "Lightbox\n.\nINES\nLe 1er janvier, un événement.\n"
    assert clean_for_chunking(body, "asnr-incident-notice") == (
        "Le 1er janvier, un événement."
    )


def test_clean_removes_letter_pdf_letterhead() -> None:
    body = (
        "RÉPUBLIQUE FRANÇAISE\n"
        "5, place Jules Ferry – 69006 Lyon\n"
        "5 place Jules Ferry - 69006 Lyon\n"  # no comma after pypdf extraction
        "Tél. : +33 (0)4 26 28 60 00 / Courriel : lyon.asnr@asnr.fr 1/7\n"
        "Division de Lyon\n"
        "Référence courrier : CODEP-LYO-2026-062826\n"
        "Lyon, le 23 octobre 2026\n"
        "Objet : Contrôle des INB\n"
        "Madame le Directeur,\n"
    )
    cleaned = clean_for_chunking(body, "asnr-inspection-letter")
    assert "RÉPUBLIQUE FRANÇAISE" not in cleaned
    assert "Jules Ferry" not in cleaned
    assert "Tél." not in cleaned
    assert "Division de Lyon" not in cleaned
    assert "1/7" not in cleaned
    # real content is kept
    assert "Référence courrier : CODEP-LYO-2026-062826" in cleaned
    assert "Lyon, le 23 octobre 2026" in cleaned
    assert "Madame le Directeur," in cleaned


def test_clean_keeps_letterhead_noise_in_non_letter_sources() -> None:
    body = "RÉPUBLIQUE FRANÇAISE\nDivision de Lyon\n"
    # only letters get the PDF letterhead treatment
    assert clean_for_chunking(body, "asnr-incident-notice") == body.strip()


def test_chunk_text_short_body_single_chunk() -> None:
    assert chunk_text("Un petit paragraphe.", 2000, 400) == ["Un petit paragraphe."]


def test_chunk_text_hard_splits_long_paragraph_with_overlap() -> None:
    chunks = chunk_text("a" * 1000, max_chars=200, overlap_chars=40)
    assert len(chunks) == 6
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0] == "a" * 200
    assert chunks[1][:40] == "a" * 40  # overlap tail carried over


def test_chunk_text_packs_paragraphs_until_limit() -> None:
    paras = "\n\n".join(f"paragraphe {i} " + "x" * 100 for i in range(10))
    chunks = chunk_text(paras, max_chars=200, overlap_chars=0)
    assert len(chunks) > 1
    assert sum(c.count("paragraphe") for c in chunks) >= 10


def test_chunk_document_carries_metadata_and_max_freshness() -> None:
    doc = _notice("corps\n\n" + "mot " * 600)
    chunks = chunk_document(doc, max_chars=400, overlap_chars=40)
    assert len(chunks) > 1
    for i, c in enumerate(chunks):
        assert isinstance(c, Chunk)
        assert c.chunk_id == f"doc-1#{i}"
        assert c.doc_id == "doc-1"
        assert c.source == "asnr-incident-notice"
        assert c.url == "https://asnr.test/avis/doc-1"
        assert c.chunk_index == i
        assert c.n_chunks == len(chunks)
        assert c.max_freshness == date(2021, 6, 1)  # updated wins over published
        assert c.published == date(2020, 1, 1)
        assert c.n_chars == len(c.text)


def test_chunk_document_cleans_before_chunking() -> None:
    doc = _notice("Lightbox\n.\ncorps utile.")
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].text == "corps utile."


def test_chunk_corpus_roundtrip(tmp_path: Path, synthetic_notice_html: str) -> None:
    from orphee.data.parse import parse_notice

    doc = parse_notice(synthetic_notice_html, "https://asnr.test/avis/evenement-test")
    doc = doc.model_copy(update={"body": "Lightbox\n.\n" + doc.body})
    interim = tmp_path / "interim"
    interim.mkdir()
    (interim / "incident_notices.jsonl").write_text(
        doc.model_dump_json() + "\n" + "not json\n", encoding="utf-8"
    )
    out = tmp_path / "processed" / "chunks.jsonl"
    report = chunk_corpus(sorted(interim.glob("*.jsonl")), out)
    assert report.documents == 1
    assert report.skipped == 1
    assert report.chunks >= 1
    assert report.cleaned_lines >= 1  # "Lightbox"/"INES"/"." artefacts removed
    chunks = load_chunks(out)
    assert chunks[0].doc_id == "evenement-test"
    assert chunks[0].max_freshness == date(2021, 9, 3)
    assert all("Lightbox" not in c.text for c in chunks)
