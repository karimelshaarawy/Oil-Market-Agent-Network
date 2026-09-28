from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from econ.core.config import get_api_base_url, get_api_key
from econ.core.json_utils import extract_json
from econ.scenario.scenario_pack import PriceAnchor, ScenarioEvent, ScenarioPack

# Backward-compatible alias — extraction now lives in econ.core.json_utils.
_extract_json = extract_json

load_dotenv(override=True)


DEFAULT_FALLBACK_SUMMARY = (
    "No external seed documents were used. Agents should rely on live market "
    "listings, price history, inventory costs, and scheduled simulation events."
)


def fallback_scenario_pack(events: dict[int, str | None]) -> ScenarioPack:
    """Wrap the existing hardcoded EVENTS dict as a persisted scenario pack."""
    return ScenarioPack(
        summary=DEFAULT_FALLBACK_SUMMARY,
        events=[
            ScenarioEvent(step=int(step), event_text=text, source="hardcoded")
            for step, text in sorted(events.items())
        ],
        generated=False,
        source="hardcoded_events",
    )


async def build_scenario_pack(
    seed_text: str | None,
    n_steps: int,
    goods: list[str],
    fallback_events: dict[int, str | None],
    max_events: int = 4,
) -> ScenarioPack:
    """Build a grounded scenario pack from seed news/report text.

    The LLM is used once (async) at simulation start. If anything fails, the
    caller gets a fallback pack that preserves current hardcoded event behavior.
    A stop request cancels the in-flight call: ``CancelledError`` is a
    ``BaseException`` so the broad ``except Exception`` below never swallows it.
    """
    seed_text = (seed_text or "").strip()
    if not seed_text:
        return fallback_scenario_pack(fallback_events)

    try:
        data = await _call_llm(seed_text=seed_text, n_steps=n_steps, goods=goods, max_events=max_events)
        return _pack_from_json(
            data=data,
            raw_seed_text=seed_text,
            n_steps=n_steps,
            goods=goods,
            max_events=max_events,
        )
    except Exception:
        pack = fallback_scenario_pack(fallback_events)
        return ScenarioPack(
            summary=(
                "Scenario extraction failed, so this run used the hardcoded "
                "baseline event schedule. Raw seed text was still saved for audit."
            ),
            macro_facts=pack.macro_facts,
            uncertainties=pack.uncertainties,
            price_anchors=pack.price_anchors,
            events=pack.events,
            raw_seed_text=seed_text,
            generated=False,
            source="fallback_after_extraction_error",
        )


async def _call_llm(seed_text: str, n_steps: int, goods: list[str], max_events: int) -> dict[str, Any]:
    client = AsyncOpenAI(
        base_url=get_api_base_url(),
        api_key=get_api_key(),
        timeout=float(os.getenv("ECON_SCENARIO_TIMEOUT_SECONDS", "60")),
    )
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
    system = (
        "You extract bounded oil-market simulation context from seed documents. "
        "Use only facts present in the seed text. Return strict JSON only."
    )
    user = f"""
Simulation length: {n_steps} steps.
Known simulation goods: {", ".join(goods)}.
Maximum shock events: {max_events}.

Seed market context:
{seed_text[:12000]}

Return JSON with this schema:
{{
  "summary": "short paragraph",
  "macro_facts": ["fact 1", "fact 2"],
  "uncertainties": ["uncertainty 1"],
  "price_anchors": [
    {{"good_name": "crude_oil", "low": 10, "high": 20, "rationale": "short reason"}}
  ],
  "events": [
    {{"step": 2, "event_text": "short actionable market event text"}}
  ]
}}

Rules:
- Use only known goods.
- Event steps must be integers from 1 to {n_steps}.
- Event text should be <= 550 characters and should guide likely market effects without forcing actions.
- Price anchors are non-binding ranges in simulation credits per unit.
- Include null event_text only if a step should clear prior active event context.
"""
    # Pure JSON extraction — call AsyncOpenAI directly with no thinking extra_body
    # (a stop cancels this await and tears down the in-flight request).
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(extract_json(content))


def _pack_from_json(
    data: dict[str, Any],
    raw_seed_text: str,
    n_steps: int,
    goods: list[str],
    max_events: int,
) -> ScenarioPack:
    known_goods = {good for good in goods if good}
    anchors: list[PriceAnchor] = []
    for item in data.get("price_anchors", []):
        good = str(item.get("good_name", "")).strip()
        if good not in known_goods:
            continue
        low = float(item.get("low", 0))
        high = float(item.get("high", 0))
        if low <= 0 or high <= 0:
            continue
        if low > high:
            low, high = high, low
        anchors.append(
            PriceAnchor(
                good_name=good,
                low=round(low, 4),
                high=round(high, 4),
                rationale=str(item.get("rationale", ""))[:240],
            )
        )

    events: list[ScenarioEvent] = []
    seen_steps: set[int] = set()
    for item in data.get("events", [])[:max_events]:
        step = int(item.get("step", 0))
        if step < 1 or step > n_steps or step in seen_steps:
            continue
        seen_steps.add(step)
        event_text = item.get("event_text")
        if event_text is not None:
            event_text = str(event_text).strip()[:550]
            if not event_text:
                continue
        events.append(ScenarioEvent(step=step, event_text=event_text, source="generated"))

    return ScenarioPack(
        summary=str(data.get("summary", "")).strip()[:1400],
        macro_facts=[str(x).strip()[:300] for x in data.get("macro_facts", []) if str(x).strip()][:8],
        uncertainties=[
            str(x).strip()[:300]
            for x in data.get("uncertainties", [])
            if str(x).strip()
        ][:5],
        price_anchors=anchors,
        events=sorted(events, key=lambda event: event.step),
        raw_seed_text=raw_seed_text,
        generated=True,
        source="seed_documents",
    )
