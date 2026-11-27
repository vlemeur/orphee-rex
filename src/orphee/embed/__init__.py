"""mistral-embed API client (disk-cached) + Mistral chat client.

Every API call — embeddings or chat — is cached on disk by payload hash, so
re-runs never hit the network again. Covered by the Vibe Pro subscription's
monthly API credit; the cache keeps us well inside it.
"""

from orphee.embed.client import (
    MISTRAL_EMBED_DIM,
    MISTRAL_EMBED_MODEL,
    Embedder,
    MistralChat,
    MistralEmbedder,
    make_embedder,
)

__all__ = [
    "MISTRAL_EMBED_DIM",
    "MISTRAL_EMBED_MODEL",
    "Embedder",
    "MistralChat",
    "MistralEmbedder",
    "make_embedder",
]
