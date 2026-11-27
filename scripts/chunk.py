"""Chunk the parsed interim JSONL into embeddable chunks (offline).

Reads data/interim/*.jsonl, cleans boilerplate (HTML chrome, PDF letterheads),
writes data/processed/chunks.jsonl with one JSON record per chunk (citation
metadata + max_freshness included).
Chunks are sized in characters (mistral-embed's tokenizer is not public and
its 8192-token input window is far above our chunk sizes): 2000 chars ≈ 500
tokens for French text.
Examples:
    uv run python scripts/chunk.py                          # defaults 2000/400
    uv run python scripts/chunk.py --max-chars 1200 --overlap-chars 240
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from orphee.data.chunk import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS, chunk_corpus
from orphee.env import load_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interim-dir", default="data/interim", help="directory of <source>.jsonl"
    )
    parser.add_argument(
        "--out", default="data/processed/chunks.jsonl", help="output chunks JSONL"
    )
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--overlap-chars", type=int, default=DEFAULT_OVERLAP_CHARS)
    args = parser.parse_args()
    load_env()  # .env at project root, if present
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    paths = sorted(Path(args.interim_dir).glob("*.jsonl"))
    report = chunk_corpus(paths, args.out, args.max_chars, args.overlap_chars)
    print(
        f"\nchunk: {report.documents} documents -> {report.chunks} chunks "
        f"(max {report.max_chars} chars, overlap {report.overlap_chars}), "
        f"{report.cleaned_lines} boilerplate lines removed -> {args.out}"
    )
    if report.skipped:
        print(f"skipped {report.skipped} unreadable line(s)")


if __name__ == "__main__":
    main()
