# orphee-rex

[![CI](https://github.com/vlemeur/orphee-rex/actions/workflows/ci.yml/badge.svg)](https://github.com/vlemeur/orphee-rex/actions/workflows/ci.yml)

Ask the French nuclear operating experience (REX) in natural language —
source-cited answers, evaluated end to end.

Source-cited RAG over public ASNR data — incident notices (avis d'incident
INB, HTML) first, then inspection reports and annual reports — on the Mistral
stack (mistral-embed 1024-d + chat API). Budget: 0 EUR (subscription quota
only; every API call cached on disk by payload hash, never re-embedded by
default).

## Run

```bash
just setup               # uv sync --locked + install prek hooks
just all                 # lint + type-check + tests + prek — the single gate
just scrape --limit 50   # smoke: ASNR incident notices into the raw cache (network)
```

Domain modules under `src/orphee/` and the `scripts/` CLIs land iteratively,
as sources and pipelines are built.
