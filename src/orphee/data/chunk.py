"""Chunk parsed ASNR documents into embeddable units (offline).

Token counts are approximated at ~4 characters per token (French text, no
tokenizer dependency); chunk sizes are approximate by design — the retrieval
eval measures what actually matters (recall@k).

Before chunking, ``clean_for_chunking`` removes verified boilerplate: lone
"."/"INES"/"Lightbox" lines (parsing/tooltip artefacts in HTML bodies) and,
for inspection letters, the recurring PDF letterhead (RÉPUBLIQUE FRANÇAISE,
postal address, phone, page numbers, division line — the division is already
a parsed field). The interim JSONL stays the raw source of truth; cleaning
only applies to chunk text.

Chunking strategy: split on blank lines into paragraphs, greedily pack
paragraphs up to ``max_tokens``, keep an ``overlap_tokens`` tail of the
previous chunk when starting a new one, and hard-split paragraphs longer than
a full chunk into sliding windows with the same overlap. Every chunk keeps
its citation metadata, including ``max_freshness`` (anti-leakage).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from orphee.data.models import AsnrDocument, AsnrDocumentUnion, Chunk

CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 100

_adapter = TypeAdapter(AsnrDocumentUnion)

# Lone lines removed from every body before chunking (verified on real data:
# "." x2733, "INES" x3276 — tooltip artefacts — and "Lightbox" — HTML chrome).
NOISE_LINES = {".", "INES", "Lightbox"}
# Inspection-letter PDF letterhead/pagination lines (all sampled letters start
# with "RÉPUBLIQUE FRANÇAISE" then address/phone/page number).
LETTER_NOISE_RES = (
    re.compile(r"^RÉPUBLIQUE FRANÇAISE$"),
    re.compile(r"^(Adresse postale|Tél\.|Téléphone|Courriel)", re.I),
    # postal address line; the comma after the number is lost by pypdf sometimes
    re.compile(r"^\d+,?\s+place\s.+"),
    re.compile(r"^\d+/\d+$"),
    re.compile(r"^Division de ", re.I),
)


def clean_for_chunking(text: str, source: str) -> str:
    """Drop boilerplate lines from a body; interim JSONL is left untouched."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s in NOISE_LINES:
            continue
        if source == "asnr-inspection-letter" and any(
            rx.match(s) for rx in LETTER_NOISE_RES
        ):
            continue
        out.append(s)
    return "\n".join(out)


def approx_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def chunk_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split text into chunks of ~max_tokens (approx), with overlap."""
    max_chars = max(1, max_tokens) * CHARS_PER_TOKEN
    overlap_chars = min(max(0, overlap_tokens) * CHARS_PER_TOKEN, max_chars // 2)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(para):
                end = min(start + max_chars, len(para))
                chunks.append(para[start:end])
                if end >= len(para):
                    break
                start = max(start + 1, end - overlap_chars)
            continue
        candidate = f"{current}\n{para}" if current else para
        if current and len(candidate) > max_chars:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail} {para}" if tail else para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_document(
    doc: AsnrDocument,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """One document -> its chunks, carrying citation + anti-leakage metadata."""
    body = clean_for_chunking(doc.body, doc.source)
    texts = chunk_text(body, max_tokens, overlap_tokens)
    n = len(texts)
    return [
        Chunk(
            chunk_id=f"{doc.id}#{i}",
            doc_id=doc.id,
            source=doc.source,
            url=doc.url,
            title=doc.title,
            published=doc.published,
            max_freshness=doc.max_freshness,
            chunk_index=i,
            n_chunks=n,
            text=t,
            n_chars=len(t),
        )
        for i, t in enumerate(texts)
    ]


def iter_documents(paths: Iterable[Path]) -> Iterator[AsnrDocument]:
    """Yield every document of the given interim JSONL files."""
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield _adapter.validate_json(line)


@dataclass
class ChunkReport:
    documents: int = 0
    chunks: int = 0
    skipped: int = 0  # unreadable lines
    cleaned_lines: int = 0
    max_tokens: int = DEFAULT_MAX_TOKENS
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS


def chunk_corpus(
    interim_paths: Iterable[Path],
    out_path: Path | str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> ChunkReport:
    """Chunk every document of the interim files into out_path (JSONL)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = ChunkReport(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    with out_path.open("w", encoding="utf-8") as out:
        for path in interim_paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    doc = _adapter.validate_json(line)
                except Exception:
                    report.skipped += 1
                    continue
                report.documents += 1
                report.cleaned_lines += len(doc.body.splitlines()) - len(
                    clean_for_chunking(doc.body, doc.source).splitlines()
                )
                for chunk in chunk_document(doc, max_tokens, overlap_tokens):
                    out.write(chunk.model_dump_json() + "\n")
                    report.chunks += 1
    return report


def load_chunks(path: Path | str) -> list[Chunk]:
    """Load a chunks JSONL file (offline)."""
    return [
        Chunk.model_validate(json.loads(line))
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
