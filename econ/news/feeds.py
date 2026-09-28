"""Fetch recent oil-market news from RSS feeds.

This is the *fetching* half of the live-news scenario grounding. It pulls
entries from a curated set of oil/energy RSS feeds, normalizes them into
``Article`` objects, and drops anything older than the lookback window or
missing a parseable publish date.

``fetch_articles`` is async: the HTTP GETs go through a shared
``httpx.AsyncClient`` (so a stop cancels them), while the cheap, synchronous
``feedparser`` parse runs inline on the returned bytes.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Per-feed HTTP timeout (seconds). feedparser's own fetch has no timeout, so a
# single slow/dead feed could otherwise stall the whole run indefinitely.
DEFAULT_FETCH_TIMEOUT_SECONDS = 8.0

# A browser-ish UA: some feeds (e.g. investing.com) 403 the default urllib UA.
_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EconSimNewsBot/1.0)"}


# Curated oil/energy RSS feeds. Override via ECON_NEWS_FEEDS (comma-separated).
# Google News search RSS is included as a robust, always-available fallback.
DEFAULT_FEEDS: list[str] = [
    "https://oilprice.com/rss/main",
    "https://www.eia.gov/rss/todayinenergy.xml",
    "https://www.investing.com/rss/news_11.rss",  # commodities
    "https://www.rigzone.com/news/rss/rigzone_latest.aspx",
    (
        "https://news.google.com/rss/search?"
        "q=oil+prices+OR+OPEC+OR+crude+oil&hl=en-US&gl=US&ceid=US:en"
    ),
]

DEFAULT_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class Article:
    title: str
    summary: str
    link: str
    published: datetime  # timezone-aware (UTC)
    source_feed: str = ""


def resolve_feeds(feeds: list[str] | None = None) -> list[str]:
    """Resolve the feed list: explicit arg > ECON_NEWS_FEEDS env > defaults."""
    if feeds:
        return list(feeds)
    env_feeds = os.getenv("ECON_NEWS_FEEDS", "").strip()
    if env_feeds:
        return [f.strip() for f in env_feeds.split(",") if f.strip()]
    return list(DEFAULT_FEEDS)


def resolve_lookback_days(lookback_days: int | None = None) -> int:
    if lookback_days is not None:
        return int(lookback_days)
    raw = os.getenv("ECON_NEWS_LOOKBACK_DAYS", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid ECON_NEWS_LOOKBACK_DAYS=%r; using default.", raw)
    return DEFAULT_LOOKBACK_DAYS


def _resolve_fetch_timeout() -> float:
    """Resolve the per-feed HTTP timeout: ECON_NEWS_FETCH_TIMEOUT_SECONDS > default."""
    raw = os.getenv("ECON_NEWS_FETCH_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "Invalid ECON_NEWS_FETCH_TIMEOUT_SECONDS=%r; using default.", raw
            )
    return DEFAULT_FETCH_TIMEOUT_SECONDS


async def _fetch_feed(client, url: str, cutoff: datetime) -> list[Article]:
    """Fetch and parse one feed (async) with the client's timeout.

    The HTTP GET goes through the shared ``httpx.AsyncClient`` so a stop cancels
    the in-flight request, and the raw bytes are handed to ``feedparser`` (which
    has no timeout of its own). Per-feed failures are logged and swallowed so one
    broken feed never aborts the whole fetch. ``CancelledError`` is a
    ``BaseException``, so a stop is not swallowed by the ``except Exception``.
    """
    import feedparser

    try:
        resp = await client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # network / HTTP / parse errors
        logger.warning("Failed to fetch feed %s: %s", url, exc)
        return []

    out: list[Article] = []
    for entry in getattr(parsed, "entries", []):
        published = _entry_published(entry)
        if published is None or published < cutoff:
            continue
        title = (getattr(entry, "title", "") or "").strip()
        if not title:
            continue
        link = (getattr(entry, "link", "") or "").strip()
        summary = (getattr(entry, "summary", "") or "").strip()
        out.append(
            Article(
                title=title,
                summary=summary[:1000],
                link=link,
                published=published,
                source_feed=url,
            )
        )
    return out


def _entry_published(entry) -> datetime | None:
    """Extract a timezone-aware UTC datetime from a feedparser entry, or None."""
    for key in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, key, None) or (
            entry.get(key) if hasattr(entry, "get") else None
        )
        if struct:
            try:
                # feedparser normalizes to UTC struct_time.
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


async def fetch_articles(
    feeds: list[str] | None = None,
    lookback_days: int | None = None,
) -> list[Article]:
    """Fetch and normalize recent articles from the configured RSS feeds.

    Per-feed failures are logged and skipped so one broken feed never aborts
    the whole fetch. Feeds are fetched concurrently (one shared async client)
    and each is bounded by a timeout, so the total time is ~the slowest single
    feed (capped), not the sum. A stop cancels the in-flight requests cleanly —
    no background threads to orphan. Returns articles sorted oldest-first.
    """
    import httpx

    feed_urls = resolve_feeds(feeds)
    cutoff = datetime.now(timezone.utc) - timedelta(days=resolve_lookback_days(lookback_days))
    timeout = _resolve_fetch_timeout()

    async with httpx.AsyncClient(
        timeout=timeout, headers=_FETCH_HEADERS, follow_redirects=True
    ) as client:
        per_feed = await asyncio.gather(
            *[_fetch_feed(client, url, cutoff) for url in feed_urls]
        )

    articles: list[Article] = []
    seen: set[str] = set()
    for feed_articles in per_feed:
        for art in feed_articles:
            dedupe_key = art.link or art.title
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            articles.append(art)

    articles.sort(key=lambda a: a.published)
    logger.info("Fetched %d recent articles from %d feeds.", len(articles), len(feed_urls))
    return articles
