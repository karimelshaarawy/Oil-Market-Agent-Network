"""Single CAMEL chat-model factory shared by the examples and the runner."""
from __future__ import annotations

import os

from camel.configs import ChatGPTConfig
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from econ.core.config import (
    DEFAULT_MAX_COMPLETION_TOKENS,
    env_int,
    get_api_base_url,
    get_api_key,
)


def build_chat_model(temperature: float = 0.4, max_tokens: int | None = None):
    """Build an OpenAI-compatible CAMEL model from environment settings.

    MODEL_NAME / OPENAI_BASE_URL / OPENAI_API_KEY are read at call time.
    ``max_tokens`` defaults to ECON_MAX_COMPLETION_TOKENS.
    """
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
    from econ.core.thinking_adapter import is_thinking_enabled

    if max_tokens is None:
        max_tokens = env_int("ECON_MAX_COMPLETION_TOKENS", DEFAULT_MAX_COMPLETION_TOKENS)

    thinking_on = is_thinking_enabled()
    # Z.AI reasoning models require temperature=1.0 when thinking is enabled.
    effective_temperature = 1.0 if thinking_on else temperature

    model_config_dict = ChatGPTConfig(
        temperature=effective_temperature,
        max_tokens=max_tokens,
    ).as_dict()

    reasoning_effort = os.getenv("ECON_REASONING_EFFORT", "medium")
    if thinking_on:
        model_config_dict["extra_body"] = {
            "thinking": {"type": "enabled"},
            "reasoning_effort": reasoning_effort,
        }
    else:
        model_config_dict["extra_body"] = {"thinking": {"type": "disabled"}}

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name,
        url=get_api_base_url(),
        api_key=get_api_key(),
        model_config_dict=model_config_dict,
    )
