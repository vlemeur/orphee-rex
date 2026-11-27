# orphee-rex

[![CI](https://github.com/vlemeur/orphee-rex/actions/workflows/ci.yml/badge.svg)](https://github.com/vlemeur/orphee-rex/actions/workflows/ci.yml)

Ask the French nuclear operating experience (REX) in natural language —
source-cited answers, evaluated end to end.

Source-cited RAG over public ASNR data — avis d'incident (INB incl. transports,
médical, industriel), avis d'arrêts de réacteurs (HTML) and lettres de suite
d'inspection INB (PDF), from reglementation-controle.asnr.fr; annual reports
next — chat on the Mistral API; embeddings pluggable: local FastEmbed/ONNX by
default (0 EUR, offline), mistral-embed API optional. Budget: 0 EUR (every API
call cached on disk by payload hash; every embedding cached per text).

## Run

```bash
just setup               # uv sync --locked + install prek hooks
just all                 # lint + type-check + tests + prek — the single gate
just scrape --limit 50   # smoke: all sources, 50 docs each, into the raw cache (network)
just scrape --source inspection_letters_inb --max-pages 3 --limit 30  # one source only
just ingest              # raw cache -> parsed JSONL (offline), all sources
just chunk && just embed # chunks -> embeddings (local backend, offline, 0 EUR)
```

Scrapable sources (`--source`): `incident_notices` (INB, done — transport
incidents are INB notices too, no separate source), `reactor_outages`,
`medical_incidents`, `patient_radiotherapy_incidents`, `industrial_incidents`,
`inspection_letters_inb` (PDFs, enumerated via the paginated listing).
Full-history runs take hours at the robots.txt Crawl-delay (10 s) — resumable
(cache + manifest per source), run in the background.

Domain modules under `src/orphee/` and the `scripts/` CLIs land iteratively,
as sources and pipelines are built.
