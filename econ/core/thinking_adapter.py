from __future__ import annotations

import os
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def is_thinking_enabled() -> bool:
    """Helper to check if reasoning/thinking configurations should be enabled from environment config."""
    return os.getenv("ECON_ENABLE_THINKING", "false").lower() == "true"


def adapt_openai_client_call(
    client: Any,
    model_name: str,
    messages: List[Dict[str, Any]],
    *,
    enable_thinking: bool | None = None,
    **kwargs: Any,
) -> Any:
    """Wraps OpenAI client direct chat completion calls. Injects 'extra_body' thinking
    parameters if thinking is enabled.

    ``enable_thinking`` overrides the global ``ECON_ENABLE_THINKING`` flag for a
    single call: pass ``False`` for pure-extraction tasks (JSON scoring, scenario
    parsing) that don't need a reasoning trace, so they don't pay the latency of
    a hidden chain-of-thought and time out. ``None`` (default) keeps the global
    behavior.
    """
    request_kwargs = dict(kwargs)
    thinking = is_thinking_enabled() if enable_thinking is None else enable_thinking
    if thinking:
        request_kwargs["extra_body"] = {
            "enable_thinking": True,
            "chat_template_kwargs": {"enable_thinking": True}
        }
    return client.chat.completions.create(
        model=model_name,
        messages=messages,
        **request_kwargs
    )
