"""Shared fixtures for the offline test suite (synthetic data, no network)."""

import pytest

# Minimal synthetic ASNR incident-notice page, mirroring the Ibexa structure
# verified on the real pages during recon (ArticleHeader / Tooltip / RichText
# / AsideBlock), including a lexicon tooltip span in the body.
SYNTHETIC_NOTICE_HTML = """<!doctype html>
<html><head>
<title>Événement test - 03/09/2021 - ASNR</title>
<meta property="og:title" content="Événement test"/>
</head><body>
<div class="ArticleHeader ArticleHeader--red">
  <div class="Tooltip-element">
    <span class="Tooltip-title">Centrale nucléaire de Test</span>
    <span class="Tooltip-description">Réacteurs de 900 MWe - EDF</span>
  </div>
  <h1 class="ArticleHeader-title">Événement significatif test</h1>
  <div class="ArticleHeader-chapo">
    <div class="ibexa_richtext-field"><p>Résumé chapo.</p></div>
  </div>
  <div class="ArticleHeader-infobar">
    <p class="ArticleHeader-date">Publié le 15/02/2017</p>
    <div><small>Date de la dernière mise à jour : 03/09/2021</small></div>
  </div>
</div>
<div class="RichText"><div class="ibexa_richtext-field">
<p>Le 26 janvier 2017, l'exploitant déclare un événement classé au
<span data-title="INES" data-content="lexique">niveau 2</span> de l'échelle INES.</p>
</div></div>
<div class="AsideBlock">
  <h4>Classement de l'incident (INES)</h4>
  <p class="AsideBlock-incident-level">Niveau 2</p>
</div>
</body></html>
"""


@pytest.fixture
def synthetic_notice_html() -> str:
    return SYNTHETIC_NOTICE_HTML


# Synthetic reactor-outage page: same Ibexa structure, title carries the
# reactor number and the outage kind.
SYNTHETIC_OUTAGE_HTML = """<!doctype html>
<html><head>
<title>Arrêt pour visite partielle du réacteur 1 - ASNR</title>
<meta property="og:title" content="Arrêt pour visite partielle du réacteur 1"/>
</head><body>
<div class="ArticleHeader">
  <div class="Tooltip-element">
    <span class="Tooltip-title">Centrale nucléaire de Gravelines</span>
    <span class="Tooltip-description">Réacteurs de 900 MWe - EDF</span>
  </div>
  <h1 class="ArticleHeader-title">Arrêt pour visite partielle du réacteur 1</h1>
  <div class="ArticleHeader-infobar">
    <p class="ArticleHeader-date">Publié le 04/05/2026</p>
  </div>
</div>
<div class="RichText"><div class="ibexa_richtext-field">
<p>Le réacteur 1 de la centrale nucléaire de Gravelines a été arrêté pour
maintenance le 12 juillet 2025.</p>
</div></div>
</body></html>
"""


@pytest.fixture
def synthetic_outage_html() -> str:
    return SYNTHETIC_OUTAGE_HTML


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_synthetic_letter_pdf(lines: list[str]) -> bytes:
    """Build a minimal valid one-page PDF whose text is `lines` (pypdf-readable).

    Offline test helper — the content stream is latin-1 (WinAnsi), so French
    accents survive extraction.
    """
    content = (
        "BT /F1 10 Tf 50 780 Td\n"
        + "\n".join(f"({_pdf_escape(line)}) Tj 0 -14 Td" for line in lines)
        + "\nET"
    )
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream"
        % (len(content), content.encode("latin-1")),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return out


# Mirrors the real letter layout ("Lettre de suite de l'inspection du ...
# sur le thème de ..."), kept ASCII: a hand-made PDF stream does not round-trip
# accents through pypdf. Accented date parsing is unit-tested separately.
SYNTHETIC_LETTER_LINES = [
    "Lettre de suite de l'inspection du 27/02/2025 sur le theme de la "
    "surveillance des activites",
    "No dossier : Inspection no INSSN-CAE-2025-0257",
    "Division de Caen",
    "Par lettre citee en reference, vous m'avez adresse vos observations.",
]


@pytest.fixture
def synthetic_letter_pdf() -> bytes:
    return make_synthetic_letter_pdf(SYNTHETIC_LETTER_LINES)
