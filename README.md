# orphee-rex

[![CI](https://github.com/vlemeur/orphee-rex/actions/workflows/ci.yml/badge.svg)](https://github.com/vlemeur/orphee-rex/actions/workflows/ci.yml)

Ask the French nuclear operating experience (REX) in natural language —
source-cited answers, evaluated end to end.

Source-cited RAG over public ASNR data — avis d'incident (INB incl. transports,
médical, industriel), avis d'arrêts de réacteurs (HTML) and lettres de suite
d'inspection INB (PDF), from reglementation-controle.asnr.fr; annual reports
next — on the Mistral stack (mistral-embed 1024-d + chat API). Budget: 0 EUR
(subscription quota only; every API call cached on disk by payload hash, never
re-embedded by default).

## Run

```bash
just setup               # uv sync --locked + install prek hooks
just all                 # lint + type-check + tests + prek — the single gate
just scrape --limit 50   # smoke: ASNR incident notices into the raw cache (network)
just scrape --source inspection_letters_inb --max-pages 3 --limit 30  # letters smoke
just ingest              # raw cache -> parsed JSONL (offline), per --source
```

Scrapable sources (`--source`): `incident_notices` (INB, done — transport
incidents are INB notices too, no separate source), `reactor_outages`,
`medical_incidents`, `patient_radiotherapy_incidents`, `industrial_incidents`,
`inspection_letters_inb` (PDFs, enumerated via the paginated listing).
Full-history runs take hours at the robots.txt Crawl-delay (10 s) — resumable,
run them one at a time in the background.

Domain modules under `src/orphee/` and the `scripts/` CLIs land iteratively,
as sources and pipelines are built.
