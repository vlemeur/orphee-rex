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
