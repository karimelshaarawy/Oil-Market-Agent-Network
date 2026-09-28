"""Shared helper for extracting JSON objects from LLM responses."""
from __future__ import annotations

import re


def extract_json(text: str) -> str:
    """Return the JSON object embedded in ``text`` (strips ``` fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in scenario response.")
    return match.group(0)
