"""Embed the chunks with mistral-embed (La Plateforme API, disk-cached).

Reads data/processed/chunks.jsonl, writes data/processed/embeddings-mistral.npy
(n_chunks x dim, float32, row order = chunks file order) + a .meta.json sidecar.
Every API batch is cached by payload hash under results/cache/mistral/, so
re-runs only call the API for the new chunks.
Examples:
    uv run python scripts/embed.py --limit 200   # smoke
    uv run python scripts/embed.py                # full corpus
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from orphee.data.chunk import load_chunks
from orphee.embed import make_embedder
from orphee.env import load_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="default mistral-embed")
    parser.add_argument("--chunks", default="data/processed/chunks.jsonl")
    parser.add_argument("--out", default="data/processed/embeddings-mistral.npy")
    parser.add_argument("--limit", type=int, default=None, help="max chunks to embed")
    args = parser.parse_args()
    load_env()  # .env at project root, if present
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    chunks = load_chunks(args.chunks)
    if args.limit is not None:
        chunks = chunks[: args.limit]
    texts = [c.text for c in chunks]
    embedder = make_embedder(model=args.model)
    print(
        f"embedding {len(texts)} chunks from {args.chunks} "
        f"(backend={embedder.name}, model={embedder.model}, dim={embedder.dim})"
    )
    matrix = embedder.embed(texts)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, matrix)
    meta = {
        "backend": embedder.name,
        "model": embedder.model,
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
