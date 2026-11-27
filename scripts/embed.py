"""Embed the chunks (pluggable backend, disk-cached per text).

Reads data/processed/chunks.jsonl, writes data/processed/embeddings-<backend>.npy
(n_chunks x dim, float32, row order = chunks file order) + a .meta.json sidecar.
Backends: 'local' (default, offline, 0 EUR — FastEmbed/ONNX, model downloads once
from HF on first run) and 'mistral' (La Plateforme API, mistral-embed, cached by
payload hash). Every text is cached by sha256(model+text), so re-runs only compute
the new chunks.
Examples:
    uv run python scripts/embed.py --limit 200                 # smoke, local
    uv run python scripts/embed.py --backend mistral --limit 200
    uv run python scripts/embed.py                              # full corpus
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from orphee.data.chunk import load_chunks
from orphee.embed import make_embedder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["local", "mistral"], default="local")
    parser.add_argument("--model", default=None, help="default per backend")
    parser.add_argument("--chunks", default="data/processed/chunks.jsonl")
    parser.add_argument("--out", default=None, help="default embeddings-<backend>.npy")
    parser.add_argument("--limit", type=int, default=None, help="max chunks to embed")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    chunks = load_chunks(args.chunks)
    if args.limit is not None:
        chunks = chunks[: args.limit]
    texts = [c.text for c in chunks]
    embedder = make_embedder(args.backend, model=args.model)
    model = getattr(embedder, "model", "?")
    print(
        f"embedding {len(texts)} chunks from {args.chunks} "
        f"(backend={embedder.name}, model={model}, dim={embedder.dim})"
    )
    matrix = embedder.embed(texts)
    out = Path(args.out or f"data/processed/embeddings-{embedder.name}.npy")
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, matrix)
    meta = {
        "backend": embedder.name,
        "model": getattr(embedder, "model", None),
        "dim": embedder.dim,
        "n_chunks": int(matrix.shape[0]),
        "chunks_file": args.chunks,
    }
    (out.parent / f"{out.stem}.meta.json").write_text(
        json.dumps(meta, indent=1), encoding="utf-8"
    )
    print(f"saved {matrix.shape} embeddings -> {out} (+ {out.stem}.meta.json)")


if __name__ == "__main__":
    main()
