"""Central configuration: environment helpers and shared default constants.

Values here are defaults only — call sites that read environment variables
lazily (at call time) keep doing so via the ``env_*`` helpers.
"""
from __future__ import annotations

import os


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw


# Public OpenAI endpoint, used only when no base URL is configured at all.
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def get_api_base_url() -> str:
    """Resolve the OpenAI-compatible base URL from the environment.

    Accepts either ``OPENAI_BASE_URL`` or ``OPENAI_API_BASE_URL`` — the latter
    is the name used in ``.env`` for non-OpenAI providers (e.g. Z.AI / GLM).
    Every LLM client must go through this so a provider key is never sent to
    ``api.openai.com`` (which surfaces as a 401 ``invalid_api_key`` auth error).
    """
    return (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE_URL")
        or DEFAULT_OPENAI_BASE_URL
    )


def get_api_key() -> str:
    """Resolve the OpenAI-compatible API key from the environment."""
    return os.getenv("OPENAI_API_KEY", "")


# ── LLM defaults ─────────────────────────────────────────────────────────────
# ECON_MAX_COMPLETION_TOKENS — ChatGPTConfig max_tokens (new tokens per reply).
DEFAULT_MAX_COMPLETION_TOKENS = 8192
# ECON_CAMEL_TOKEN_LIMIT — CAMEL per-agent context memory budget.
DEFAULT_TOKEN_LIMIT = 32768
# Maximum concurrent LLM requests per simulation step.
DEFAULT_LLM_SEMAPHORE = 5

# ── API process control ──────────────────────────────────────────────────────
# A stop first asks the simulation child process to exit cleanly, then SIGKILLs
# it if it overruns this grace window.
STOP_GRACE_SECONDS = 2.0

# ── RAG defaults ─────────────────────────────────────────────────────────────
# Retrieval look-back window (steps) for Chroma simulation memory.
DEFAULT_RAG_WINDOW_STEPS = 8

# ── Report / interview defaults ──────────────────────────────────────────────
DEFAULT_INTERVIEW_MAX_REFLECTIONS = 8
DEFAULT_INTERVIEW_MAX_LEDGER_ENTRIES = 30

# ── Endogenous credit defaults ─────────────────────────────────────────────────
# The bank sets a per-loan rate when approving a request; it is clamped to this
# band. The scenario's ``interest_rate`` acts as the reference / fallback rate.
MIN_INTEREST_RATE = 0.01
MAX_INTEREST_RATE = 0.50
# A pending loan request that the bank neither approves nor denies within this
# many steps is auto-expired (the borrower's situation may have changed).
LOAN_REQUEST_EXPIRY_STEPS = 3
