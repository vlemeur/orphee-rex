"""Tests for orphee.embed — offline: fake API session + disk cache, no network."""

import pytest

from orphee.embed.cache import JsonDiskCache, payload_key
from orphee.embed.client import (
    MISTRAL_EMBED_DIM,
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


def test_payload_key_is_stable_and_order_insensitive() -> None:
    assert payload_key({"b": 1, "a": "x"}) == payload_key({"a": "x", "b": 1})
    assert payload_key({"a": "x"}) != payload_key({"a": "y"})


def test_json_disk_cache_roundtrip(tmp_path) -> None:
    cache = JsonDiskCache(tmp_path / "c")
    assert cache.get("k") is None
    cache.put("k", {"embedding": [1.0, 2.0]})
    assert cache.get("k") == {"embedding": [1.0, 2.0]}
    assert cache.count() == 1


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


def test_make_embedder_returns_mistral(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "t")
    emb = make_embedder(cache_dir=tmp_path / "api")
    assert isinstance(emb, MistralEmbedder)
    assert emb.name == "mistral"
