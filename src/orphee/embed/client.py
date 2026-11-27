"""Embedders (pluggable backends, disk-cached) + Mistral chat client.

Two embedding backends behind the same ``Embedder`` interface, both cached
per-text on disk (sha256(model + text)) so re-runs only compute new texts:

- ``FastEmbedLocal`` (default, 0 EUR, offline): local ONNX model via FastEmbed,
  e.g. Qwen/Qwen3-Embedding-0.6B-Q (1024-d, multilingual, 32k tokens) or
  intfloat/multilingual-e5-large. The model downloads once from HF on first
  use (run `just embed` yourself, never in tests).
- ``MistralEmbedder`` (optional, API): mistral-embed (1024-d) via La Plateforme,
  ~$0.10/M input tokens, cached per batch payload under results/cache/mistral/.

``MistralChat`` is the chat completion client (RAG generation later), cached by
payload hash. API key via MISTRAL_API_KEY env / .env — never in code or logs.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import requests
from tqdm import tqdm

from orphee.embed.cache import (
    DEFAULT_API_CACHE_DIR,
    DEFAULT_EMBED_CACHE_DIR,
    JsonDiskCache,
    payload_key,
    text_key,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.mistral.ai/v1"
MISTRAL_EMBED_MODEL = "mistral-embed"  # 1024-d, 8192-token input window
MISTRAL_EMBED_DIM = 1024
DEFAULT_LOCAL_MODEL = "Qwen/Qwen3-Embedding-0.6B-Q"  # 1024-d, multilingual, quantized
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


class CachedEmbedder:
    """Wrap a raw compute function with the per-text disk cache + tqdm progress."""

    def __init__(
        self,
        name: str,
        model: str,
        dim: int,
        compute: Callable[[list[str]], np.ndarray],
        cache_dir: Path | str = DEFAULT_EMBED_CACHE_DIR,
        batch_size: int = 64,
    ) -> None:
        self.name = name
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self._compute = compute
        self.cache = JsonDiskCache(Path(cache_dir) / name)

    def embed(self, texts: list[str]) -> np.ndarray:
        out: list[list[float] | None] = [None] * len(texts)
        missing_idx: list[int] = []
        for i, text in enumerate(texts):
            cached = self.cache.get(text_key(self.model, text))
            if cached is not None and "embedding" in cached:
                out[i] = cached["embedding"]
            else:
                missing_idx.append(i)
        n_cached = len(texts) - len(missing_idx)
        logger.info(
            "%s: %d/%d cached, computing %d (model %s)",
            self.name,
            n_cached,
            len(texts),
            len(missing_idx),
            self.model,
        )
        for start in tqdm(
            range(0, len(missing_idx), self.batch_size),
            desc=f"{self.name} embed",
            unit="batch",
            total=(len(missing_idx) + self.batch_size - 1) // self.batch_size,
        ):
            batch_idx = missing_idx[start : start + self.batch_size]
            computed = np.asarray(
                self._compute([texts[i] for i in batch_idx]), dtype=np.float32
            )
            if computed.shape != (len(batch_idx), self.dim):
                raise RuntimeError(
                    f"{self.name}: expected ({len(batch_idx)}, {self.dim}), "
                    f"got {computed.shape}"
                )
            for j, i in enumerate(batch_idx):
                vec = computed[j].tolist()
                out[i] = vec
                self.cache.put(text_key(self.model, texts[i]), {"embedding": vec})
        matrix = np.asarray(out, dtype=np.float32)
        if matrix.size == 0:
            return np.zeros((0, self.dim), dtype=np.float32)
        return matrix


class FastEmbedLocal:
    """Local ONNX embedding backend (FastEmbed) — default, offline, 0 EUR."""

    def __init__(
        self,
        model: str = DEFAULT_LOCAL_MODEL,
        cache_dir: Path | str = DEFAULT_EMBED_CACHE_DIR,
    ) -> None:
        from fastembed import TextEmbedding  # heavy import, deferred

        self.name = "local"
        self.model = model
        self._backend = TextEmbedding(model_name=model)
        catalog = {m["model"]: m for m in TextEmbedding.list_supported_models()}
        self.dim = int(catalog.get(model, {}).get("dim", 1024))
        self._embedder = CachedEmbedder(
            name=self.name,
            model=model,
            dim=self.dim,
            compute=self._compute,
            cache_dir=cache_dir,
        )

    def _compute(self, texts: list[str]) -> np.ndarray:
        vectors = list(self._backend.embed(texts, batch_size=64))
        return np.asarray(vectors, dtype=np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._embedder.embed(texts)


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
    backend: str = "local",
    model: str | None = None,
    cache_dir: Path | str = DEFAULT_EMBED_CACHE_DIR,
) -> Embedder:
    """Factory: backend 'local' (default, offline) or 'mistral' (API)."""
    if backend == "local":
        return FastEmbedLocal(model=model or DEFAULT_LOCAL_MODEL, cache_dir=cache_dir)
    if backend == "mistral":
        return MistralEmbedder(model=model or MISTRAL_EMBED_MODEL)
    raise ValueError(f"unknown backend: {backend!r} (expected 'local' or 'mistral')")
