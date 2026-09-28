"""Regression tests for OpenAI-compatible endpoint/key resolution.

Guards the bug where call sites read only ``OPENAI_BASE_URL`` and defaulted to
``api.openai.com``. With a provider key (e.g. Z.AI / GLM) configured via
``OPENAI_API_BASE_URL``, that sent the key to the wrong host and surfaced as a
401 ``invalid_api_key`` authentication error.
"""
from __future__ import annotations

from econ.core.config import (
    DEFAULT_OPENAI_BASE_URL,
    get_api_base_url,
    get_api_key,
)


def test_falls_back_to_api_base_url_when_base_url_unset(monkeypatch):
    """The exact failure config: only OPENAI_API_BASE_URL is set (the .env case)."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
    # Must resolve to the provider, NOT api.openai.com.
    assert get_api_base_url() == "https://api.z.ai/api/coding/paas/v4"


def test_prefers_base_url_when_both_set(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://primary.example/v1")
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://secondary.example/v1")
    assert get_api_base_url() == "https://primary.example/v1"


def test_defaults_to_openai_when_nothing_set(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE_URL", raising=False)
    assert get_api_base_url() == DEFAULT_OPENAI_BASE_URL


def test_api_key_reads_openai_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    assert get_api_key() == "sk-test-123"


def test_api_key_empty_when_unset(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_api_key() == ""
