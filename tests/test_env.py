"""Tests for orphee.env.load_env — offline, touches only a temp .env."""

import os

from orphee.env import load_env


def test_load_env_sets_missing_vars(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ORPHEE_TEST_A", raising=False)
    monkeypatch.delenv("ORPHEE_TEST_B", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "ORPHEE_TEST_A=hello\n"
        'ORPHEE_TEST_B="quoted value"\n'
        "MALFORMED LINE WITHOUT EQUALS\n",
        encoding="utf-8",
    )
    assert load_env(env) == 2
    assert os.environ["ORPHEE_TEST_A"] == "hello"
    assert os.environ["ORPHEE_TEST_B"] == "quoted value"


def test_load_env_never_overrides_existing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ORPHEE_TEST_KEEP", "from-env")
    env = tmp_path / ".env"
    env.write_text("ORPHEE_TEST_KEEP=from-file\n", encoding="utf-8")
    assert load_env(env) == 0
    assert os.environ["ORPHEE_TEST_KEEP"] == "from-env"


def test_load_env_missing_file_returns_zero(tmp_path) -> None:
    assert load_env(tmp_path / "nope.env") == 0
