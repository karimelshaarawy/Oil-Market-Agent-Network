"""Score fetched articles for oil-price impact and write event banners.

Reuses the project's one-off LLM call pattern (raw ``openai.OpenAI`` client +
``adapt_openai_client_call`` + JSON extraction), mirroring
``econ/scenario/builder.py``. Articles are scored in small batches (run
concurrently) rather than one giant request — a single all-articles prompt
balloons to ~15k tokens for ~130 headlines and asks the model for ~130 JSON
objects back, which routinely times out. Small batches stay fast and fail
independently.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime

from openai import AsyncOpenAI

from econ.core.config import get_api_base_url, get_api_key
from econ.core.json_utils import extract_json
from econ.news.feeds import Article

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoredArticle:
    article: Article
    impact_score: float  # 0.0 - 1.0
    affected_good: str
    banner_text: str

    @property
    def published(self) -> datetime:
        return self.article.published


def _build_prompt(articles: list[Article], goods: list[str]) -> str:
    lines = []
    for i, art in enumerate(articles):
        published = art.published.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(
            f"[{i}] ({published}) {art.title}\n"
            f"    {art.summary[:400]}"
        )
    articles_block = "\n".join(lines)
    return f"""
Known simulation goods: {", ".join(goods)}.

Below are recent news headlines. For each, judge whether it is relevant to the
oil market and, if so, how strongly it would move oil/refined-fuel prices.

Articles:
{articles_block}

Return a strict JSON object with this schema:
{{
  "articles": [
    {{
      "index": 0,
      "oil_relevant": true,
      "impact_score": 0.0,
      "affected_good": "crude_oil",
      "banner_text": "short actionable market event text"
    }}
  ]
}}

Rules:
- Include one object per input article, keyed by its integer "index".
- oil_relevant=false for anything not about oil/energy/fuel markets; such
  articles will be discarded.
- impact_score is 0.0 (no price effect) to 1.0 (major shock e.g. OPEC cut,
  war, pipeline outage, SPR release).
- affected_good must be one of the known goods, or "crude_oil" if unsure.
- banner_text: <= 400 characters, written like a live market alert with a
  leading emoji, summarizing the real event and its likely market effect.
  Do not invent facts not present in the headline/summary.
"""


DEFAULT_SCORE_BATCH_SIZE = 10
DEFAULT_SCORE_CONCURRENCY = 4

_SYSTEM_PROMPT = (
    "You are an oil-market news analyst. You score news for price impact "
    "and write concise market alerts. Use only facts present in the input. "
    "Return strict JSON only."
)


def _resolve_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning("Invalid %s=%r; using default %d.", name, raw, default)
    return default


async def _score_batch(
    client: AsyncOpenAI,
    model_name: str,
    batch: list[Article],
    goods: list[str],
) -> list[ScoredArticle]:
    """Score one small batch of articles. Returns [] on any failure.

    Indices in the prompt/response are local to ``batch``. Errors (timeout,
    parse, etc.) are logged and swallowed so one bad batch never aborts the
    whole live-news step — the other batches still contribute. A stop cancels
    the in-flight ``await`` (``CancelledError`` is a ``BaseException`` so the
    ``except Exception`` below does not swallow it).
    """
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(batch, goods)},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(extract_json(content))
    except Exception as exc:
        logger.warning("Scoring batch of %d failed: %s", len(batch), exc)
        return []

    known_goods = {g for g in goods if g}
    scored: list[ScoredArticle] = []
    for item in data.get("articles", []):
        try:
            index = int(item.get("index", -1))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(batch):
            continue
        if not bool(item.get("oil_relevant", False)):
            continue
        banner = str(item.get("banner_text", "")).strip()[:400]
        if not banner:
            continue
        try:
            impact = float(item.get("impact_score", 0.0))
        except (TypeError, ValueError):
            impact = 0.0
        impact = max(0.0, min(1.0, impact))
        good = str(item.get("affected_good", "")).strip()
        if good not in known_goods:
            good = "crude_oil"
        scored.append(
            ScoredArticle(
                article=batch[index],
                impact_score=impact,
                affected_good=good,
                banner_text=banner,
            )
        )
    return scored


async def llm_score_and_summarize(
    articles: list[Article],
    goods: list[str],
) -> list[ScoredArticle]:
    """Score articles in small concurrent batches; return oil-relevant ones.

    Batch size is configurable via ``ECON_NEWS_SCORE_BATCH_SIZE`` (default 10)
    and concurrency via ``ECON_NEWS_SCORE_CONCURRENCY`` (default 4). Batches run
    as concurrent ``AsyncOpenAI`` calls bounded by a semaphore, so a stop
    cancels all in-flight requests cleanly (no background threads to orphan).
    """
    if not articles:
        return []

    client = AsyncOpenAI(
        base_url=get_api_base_url(),
        api_key=get_api_key(),
        timeout=float(os.getenv("ECON_SCENARIO_TIMEOUT_SECONDS", "60")),
    )
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

    batch_size = _resolve_int_env("ECON_NEWS_SCORE_BATCH_SIZE", DEFAULT_SCORE_BATCH_SIZE)
    batches = [articles[i : i + batch_size] for i in range(0, len(articles), batch_size)]

    concurrency = _resolve_int_env("ECON_NEWS_SCORE_CONCURRENCY", DEFAULT_SCORE_CONCURRENCY)
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _bounded(batch: list[Article]) -> list[ScoredArticle]:
        async with sem:
            return await _score_batch(client, model_name, batch, goods)

    results = await asyncio.gather(*[_bounded(b) for b in batches])

    scored: list[ScoredArticle] = [s for batch_scored in results for s in batch_scored]
    logger.info(
        "Scored %d oil-relevant articles out of %d (%d batches of <=%d).",
        len(scored), len(articles), len(batches), batch_size,
    )
    return scored
