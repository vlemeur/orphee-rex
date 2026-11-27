"""Pluggable, disk-cached embedders + Mistral chat client (budget 0 EUR).

Default backend is local (FastEmbed/ONNX, offline, free); 'mistral' uses the
La Plateforme API (mistral-embed) with a payload-hash disk cache. Every call —
local or API — is cached on disk, so re-runs never recompute cached texts.
"""

from orphee.embed.client import (
    DEFAULT_LOCAL_MODEL,
    MISTRAL_EMBED_DIM,
    MISTRAL_EMBED_MODEL,
    CachedEmbedder,
    Embedder,
    FastEmbedLocal,
    MistralChat,
    MistralEmbedder,
    make_embedder,
)

__all__ = [
    "DEFAULT_LOCAL_MODEL",
    "MISTRAL_EMBED_DIM",
    "MISTRAL_EMBED_MODEL",
    "CachedEmbedder",
    "Embedder",
    "FastEmbedLocal",
    "MistralChat",
    "MistralEmbedder",
    "make_embedder",
]
