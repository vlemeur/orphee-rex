"""mistral-embed client (La Plateforme API, disk-cached) + Mistral chat client.

``MistralEmbedder`` calls mistral-embed (1024-d, 8192-token input window) via
La Plateforme, batch by batch, cached per batch payload under
results/cache/mistral/ — a cache hit never touches the network, so re-runs
are free. Covered by the Vibe Pro subscription's monthly API credit
(25.50 EUR/month); the payload cache keeps us well inside it.

``MistralChat`` is the chat completion client (RAG generation), cached by
payload hash. API key via MISTRAL_API_KEY env / .env — never in code or logs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import requests
from tqdm import tqdm

from orphee.embed.cache import DEFAULT_API_CACHE_DIR, JsonDiskCache, payload_key

logger = logging.getLogger(__name__)

API_BASE = "https://api.mistral.ai/v1"
MISTRAL_EMBED_MODEL = "mistral-embed"  # 1024-d, 8192-token input window
MISTRAL_EMBED_DIM = 1024
DEFAULT_CHAT_MODEL = "mistral-small-latest"
DEFAULT_TIMEOUT_S = 120.0


class Embedder(Protocol):
    """The mockable embedding surface: texts -> (n, dim) float32 matrix."""

    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class SessionLike(Protocol):
    """Minimal POST surface — satisfied by requests.Session and test fakes."""

    headers: dict[str, str]

    def post(self, url: str, json: dict[str, Any], timeout: float) -> Any: ...


class MistralEmbedder:
    """mistral-embed via La Plateforme API — cached per batch payload."""

    def __init__(
        self,
        model: str = MISTRAL_EMBED_MODEL,
        api_key: str | None = None,
        cache_dir: Path | str = DEFAULT_API_CACHE_DIR,
        session: SessionLike | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        batch_size: int = 64,
    ) -> None:
        self.name = "mistral"
        self.model = model
        self.dim = MISTRAL_EMBED_DIM
        self.batch_size = batch_size
        self.timeout_s = timeout_s
        api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY missing (env or .env)")
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.cache = JsonDiskCache(cache_dir)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = payload_key(payload)
        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("cache hit: %s", key[:12])
            return cached
        n_inputs = len(payload["input"])
        logger.info("API call: embeddings %s (%d inputs)", payload["model"], n_inputs)
        resp = self.session.post(
            f"{API_BASE}/embeddings", json=payload, timeout=self.timeout_s
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Mistral API {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        self.cache.put(key, data)
        return data

    def embed(self, texts: list[str]) -> np.ndarray:
        all_vecs: list[list[float]] = []
        n_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        for start in tqdm(
            range(0, len(texts), self.batch_size),
            desc="mistral embed",
            unit="batch",
            total=n_batches,
        ):
            batch = texts[start : start + self.batch_size]
            data = self._post({"model": self.model, "input": batch})
            vecs = [item["embedding"] for item in data["data"]]
            if len(vecs) != len(batch):
                raise RuntimeError("embedding count mismatch in API response")
            all_vecs.extend(vecs)
        matrix = np.asarray(all_vecs, dtype=np.float32)
        if matrix.size == 0:
            return np.zeros((0, self.dim), dtype=np.float32)
        if matrix.shape[1] != self.dim:
            raise RuntimeError(f"unexpected embedding dim: {matrix.shape[1]}")
        return matrix


class MistralChat:
    """Chat completions (RAG generation) — every call cached by payload hash."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | str = DEFAULT_API_CACHE_DIR,
        session: SessionLike | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY missing (env or .env)")
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.cache = JsonDiskCache(cache_dir)
        self.timeout_s = timeout_s

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str = DEFAULT_CHAT_MODEL,
        temperature: float = 0.0,
    ) -> str:
        payload = {"model": model, "messages": messages, "temperature": temperature}
        key = payload_key(payload)
        cached = self.cache.get(key)
        if cached is not None:
            return str(cached["choices"][0]["message"]["content"])
        logger.info("API call: chat/completions %s", model)
        resp = self.session.post(
            f"{API_BASE}/chat/completions", json=payload, timeout=self.timeout_s
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Mistral API {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        self.cache.put(key, data)
        return str(data["choices"][0]["message"]["content"])


def make_embedder(
    model: str | None = None,
    cache_dir: Path | str = DEFAULT_API_CACHE_DIR,
) -> Embedder:
    """Factory: the Mistral API embedder (payload-hash disk-cached)."""
    return MistralEmbedder(model=model or MISTRAL_EMBED_MODEL, cache_dir=cache_dir)
