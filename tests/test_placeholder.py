"""Placeholder: every src/orphee package must stay importable (offline)."""

import importlib

import pytest

PACKAGES = [
    "orphee",
    "orphee.net",
    "orphee.net.http",
    "orphee.net.robots",
    "orphee.sources",
    "orphee.crawl",
    "orphee.data",
    "orphee.data.models",
    "orphee.data.parse",
    "orphee.data.ingest",
]


@pytest.mark.parametrize("package", PACKAGES)
def test_package_importable(package: str) -> None:
    assert importlib.import_module(package) is not None
