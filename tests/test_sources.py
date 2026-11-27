"""Tests for orphee.sources.resolve_sources — offline, no network."""

import pytest

from orphee import sources


def test_resolve_all_returns_every_registered_source() -> None:
    specs = sources.resolve_sources(sources.ALL_SOURCES)
    assert [s.name for s in specs] == list(sources.SOURCES)
    assert len(specs) > 1


def test_resolve_single_source() -> None:
    (spec,) = sources.resolve_sources("incident_notices")
    assert spec is sources.SOURCES["incident_notices"]


def test_resolve_unknown_source_raises() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        sources.resolve_sources("transport_incidents")
