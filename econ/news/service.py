"""Turn live oil news into a per-step simulation event schedule.

Public entry point: ``build_live_news_events``. It fetches recent oil news,
scores each article for price impact, lays the most significant article across
the simulation steps in real chronological order (time-bucketed), and returns
the resulting ``ScenarioEvent`` list plus a snapshot dict for reproducibility.

Returns ``None`` on any hard failure so the caller can fall back to the
hardcoded event schedule.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from econ.news.feeds import (
    Article,
    fetch_articles,
    resolve_feeds,
    resolve_lookback_days,
)
from econ.news.scoring import ScoredArticle, llm_score_and_summarize
from econ.scenario.scenario_pack import ScenarioEvent

logger = logging.getLogger(__name__)

LIVE_NEWS_SOURCE = "live_news"


def _bucket_index(published: datetime, window_start: datetime, bucket_span: timedelta, n_steps: int) -> int:
    """Map a publish time onto a 0-based step bucket, clamped to [0, n_steps-1]."""
    if bucket_span.total_seconds() <= 0:
        return 0
    offset = (published - window_start).total_seconds() / bucket_span.total_seconds()
    return max(0, min(n_steps - 1, int(offset)))


async def build_live_news_events(
    n_steps: int,
    goods: list[str],
    lookback_days: int | None = None,
    feeds: list[str] | None = None,
) -> tuple[list[ScenarioEvent], dict] | None:
    """Build a live-news event schedule for an N-step simulation.

    Splits the lookback window into N equal time buckets; each step gets the
    highest-impact article published in its bucket (empty bucket -> no event).
    Returns (events, snapshot) or None if news is unavailable / scoring fails.

    Fully async: a stop cancels the in-flight fetch/scoring ``await`` directly
    (``CancelledError`` is a ``BaseException`` so the ``except Exception`` guards
    around fetch/scoring do not swallow it).
    """
    n_steps = int(n_steps)
    if n_steps < 1:
        return None

    resolved_feeds = resolve_feeds(feeds)
    resolved_lookback = resolve_lookback_days(lookback_days)

    try:
        articles: list[Article] = await fetch_articles(
            feeds=resolved_feeds, lookback_days=resolved_lookback
        )
    except Exception as exc:
        logger.warning("Live news fetch failed: %s", exc)
        return None

    if not articles:
        logger.warning("Live news fetch returned no recent articles.")
        return None

    try:
        scored: list[ScoredArticle] = await llm_score_and_summarize(articles, goods)
    except Exception as exc:
        logger.warning("Live news scoring failed: %s", exc)
        return None

    if not scored:
        logger.warning("No oil-relevant articles after scoring.")
        return None

    # Time-bucket the lookback window into n_steps equal buckets.
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=resolved_lookback)
    bucket_span = (now - window_start) / n_steps

    # For each bucket keep the highest-impact scored article.
    best_per_bucket: dict[int, ScoredArticle] = {}
    for sa in scored:
        idx = _bucket_index(sa.published, window_start, bucket_span, n_steps)
        current = best_per_bucket.get(idx)
        if current is None or sa.impact_score > current.impact_score:
            best_per_bucket[idx] = sa

    events: list[ScenarioEvent] = []
    chosen_snapshot: list[dict] = []
    for step in range(1, n_steps + 1):
        sa = best_per_bucket.get(step - 1)
        event_text = sa.banner_text if sa else None
        events.append(
            ScenarioEvent(step=step, event_text=event_text, source=LIVE_NEWS_SOURCE)
        )
        chosen_snapshot.append(
            {
                "step": step,
                "event_text": event_text,
                "impact_score": sa.impact_score if sa else None,
                "affected_good": sa.affected_good if sa else None,
                "title": sa.article.title if sa else None,
                "link": sa.article.link if sa else None,
                "published": sa.published.isoformat() if sa else None,
            }
        )

    snapshot = {
        "source": LIVE_NEWS_SOURCE,
        "feeds": resolved_feeds,
        "lookback_days": resolved_lookback,
        "fetched_count": len(articles),
        "scored_count": len(scored),
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "schedule": chosen_snapshot,
        "scored_articles": [
            {
                "title": sa.article.title,
                "link": sa.article.link,
                "published": sa.published.isoformat(),
                "impact_score": sa.impact_score,
                "affected_good": sa.affected_good,
                "banner_text": sa.banner_text,
            }
            for sa in sorted(scored, key=lambda s: s.impact_score, reverse=True)
        ],
    }

    fired = sum(1 for e in events if e.event_text)
    logger.info("Built live-news schedule: %d/%d steps have events.", fired, n_steps)
    return events, snapshot
