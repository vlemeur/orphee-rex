"""Tests for orphee.embed — offline: fake API session, fake FastEmbed, disk cache."""

import numpy as np
import pytest

from orphee.embed.cache import JsonDiskCache, payload_key, text_key
from orphee.embed.client import (
    MISTRAL_EMBED_DIM,
    CachedEmbedder,
    FastEmbedLocal,
    MistralChat,
    MistralEmbedder,
    make_embedder,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Counts POSTs; answers embeddings/chat from canned payloads."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict, timeout: float) -> FakeResponse:
        self.calls.append((url, json))
        if url.endswith("/embeddings"):
            return FakeResponse(
                {
                    "data": [
                        {"embedding": [float(len(t) % 7)] * MISTRAL_EMBED_DIM}
                        for t in json["input"]
                    ]
                }
            )
        if url.endswith("/chat/completions"):
            return FakeResponse({"choices": [{"message": {"content": "réponse"}}]})
        raise AssertionError(f"unexpected url {url}")


def test_keys_are_stable() -> None:
    assert text_key("m", "abc") == text_key("m", "abc")
    assert text_key("m", "abc") != text_key("m", "abd")
    assert text_key("m1", "abc") != text_key("m2", "abc")
    assert payload_key({"b": 1, "a": "x"}) == payload_key({"a": "x", "b": 1})


def test_json_disk_cache_roundtrip(tmp_path) -> None:
    cache = JsonDiskCache(tmp_path / "c")
    assert cache.get("k") is None
    cache.put("k", {"embedding": [1.0, 2.0]})
    assert cache.get("k") == {"embedding": [1.0, 2.0]}
    assert cache.count() == 1


def test_cached_embedder_computes_only_missing(tmp_path) -> None:
    n_calls = {"n": 0}
    batch_sizes: list[int] = []

    def compute(texts: list[str]) -> np.ndarray:
        n_calls["n"] += 1
        batch_sizes.append(len(texts))
        return np.asarray([[float(len(t) % 5)] * 8 for t in texts], dtype=np.float32)

    emb = CachedEmbedder(
        "fake", "fake-model", 8, compute, cache_dir=tmp_path, batch_size=2
    )
    m1 = emb.embed(["aa", "bbb"])
    assert m1.shape == (2, 8)
    assert n_calls["n"] == 1  # one batch of 2
    m2 = emb.embed(["aa", "bbb"])  # all cached
    assert n_calls["n"] == 1
    assert np.allclose(m1, m2)
    m3 = emb.embed(["aa", "ccc"])  # only "ccc" computed
    assert n_calls["n"] == 2
    assert np.allclose(m3[0], m1[0])
    # 5 texts with batch_size=2 -> batches of 2, 2, 1
    emb2 = CachedEmbedder(
        "fake", "fake-model", 8, compute, cache_dir=tmp_path / "2", batch_size=2
    )
    emb2.embed(["a", "bb", "ccc", "dddd", "eeeee"])
    assert batch_sizes[-3:] == [2, 2, 1]


def test_cached_embedder_rejects_wrong_shape(tmp_path) -> None:
    emb = CachedEmbedder("fake", "m", 8, lambda ts: np.zeros((len(ts), 3)), tmp_path)
    with pytest.raises(RuntimeError, match="expected"):
        emb.embed(["x"])


def test_mistral_embedder_batches_and_caches(tmp_path) -> None:
    session = FakeSession()
    emb = MistralEmbedder(
        api_key="t", cache_dir=tmp_path / "api", session=session, batch_size=64
    )
    texts = [f"texte {i}" for i in range(150)]
    m = emb.embed(texts)
    assert m.shape == (150, MISTRAL_EMBED_DIM)
    assert len(session.calls) == 3  # 64 + 64 + 22
    emb.embed(texts)
    assert len(session.calls) == 3  # all cached, no new API call


def test_mistral_embedder_requires_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        MistralEmbedder(cache_dir=tmp_path, session=FakeSession())


def test_mistral_embedder_api_error(tmp_path) -> None:
    class ErrSession(FakeSession):
        def post(self, url: str, json: dict, timeout: float) -> FakeResponse:
            return FakeResponse({"error": "boom"}, status_code=500)

    emb = MistralEmbedder(api_key="t", cache_dir=tmp_path / "api", session=ErrSession())
    with pytest.raises(RuntimeError, match="500"):
        emb.embed(["x"])


def test_mistral_chat_cached(tmp_path) -> None:
    session = FakeSession()
    chat = MistralChat(api_key="t", cache_dir=tmp_path / "api", session=session)
    msgs = [{"role": "user", "content": "question ?"}]
    assert chat.complete(msgs) == "réponse"
    assert chat.complete(msgs) == "réponse"
    assert len(session.calls) == 1


def test_fastembed_local_with_stubbed_backend(tmp_path, monkeypatch) -> None:
    import fastembed

    class FakeTextEmbedding:
        def __init__(self, model_name: str) -> None:
            pass

        @staticmethod
        def list_supported_models() -> list[dict]:
            return [{"model": "fake-model", "dim": 8}]

        def embed(self, texts, batch_size: int = 64):
            for t in texts:
                yield [float(len(t) % 3)] * 8

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)
    emb = FastEmbedLocal(model="fake-model", cache_dir=tmp_path / "emb")
    assert emb.name == "local"
    assert emb.dim == 8
    m1 = emb.embed(["aa", "bbbb"])
    assert m1.shape == (2, 8)
    m2 = emb.embed(["aa", "bbbb", "cccccc"])
    assert m2.shape == (3, 8)
    assert np.allclose(m2[:2], m1)  # first two served from cache


def test_make_embedder_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        make_embedder("nope")
