"""Chunk the parsed interim JSONL into embeddable chunks (offline).

Reads data/interim/*.jsonl, cleans boilerplate (HTML chrome, PDF letterheads),
writes data/processed/chunks.jsonl with one JSON record per chunk (citation
metadata + max_freshness included).
Examples:
    uv run python scripts/chunk.py                          # defaults 500/100
    uv run python scripts/chunk.py --max-tokens 300 --overlap 50
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from orphee.data.chunk import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interim-dir", default="data/interim", help="directory of <source>.jsonl"
    )
    parser.add_argument(
        "--out", default="data/processed/chunks.jsonl", help="output chunks JSONL"
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    paths = sorted(Path(args.interim_dir).glob("*.jsonl"))
    report = chunk_corpus(paths, args.out, args.max_tokens, args.overlap_tokens)
    print(
        f"\nchunk: {report.documents} documents -> {report.chunks} chunks "
        f"(max {report.max_tokens} tok, overlap {report.overlap_tokens}), "
        f"{report.cleaned_lines} boilerplate lines removed -> {args.out}"
    )
    if report.skipped:
        print(f"skipped {report.skipped} unreadable line(s)")


if __name__ == "__main__":
    main()
