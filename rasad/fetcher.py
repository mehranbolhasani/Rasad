"""
RSS feed fetching with timeout, retries, and conditional GET (ETag/Last-Modified) caching.
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import feedparser
import requests
from dateutil import parser as date_parser

from rasad.models import Article

logger = logging.getLogger(__name__)

# Strip HTML tags for raw_text
TAG_RE = re.compile(r"<[^>]+>")
LIVE_TITLE_PATTERNS = (
    "آنچه گذشت",
    "لحظه به لحظه",
    "live update",
)


def _strip_html(text: str) -> str:
    return TAG_RE.sub(" ", text).strip() if text else ""


def _normalize_match_text(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", " ")
        .strip()
        .lower()
    )


def _is_live_story(title: str, link: str) -> bool:
    title_norm = _normalize_match_text(title)
    if any(pattern in title_norm for pattern in LIVE_TITLE_PATTERNS):
        return True
    parsed = urlparse(link or "")
    return "/live/" in (parsed.path or "").lower()


def _parse_date(entry: Any, feed: Any) -> Any:
    """Parse published/updated date from feed entry; prefer published."""
    for key in ("published", "updated", "created"):
        val = getattr(entry, key, None) or entry.get(key)
        if val:
            try:
                return date_parser.parse(val)
            except (ValueError, TypeError):
                pass
    # Fallback to feed-level updated
    try:
        return date_parser.parse(getattr(feed, "updated", None) or feed.get("updated", ""))
    except (ValueError, TypeError):
        return None


def _normalize_entry(entry: Any, source_name: str, feed: Any) -> Article | None:
    title = (getattr(entry, "title", None) or entry.get("title") or "").strip()
    link = (getattr(entry, "link", None) or entry.get("link") or "").strip()
    if not title or not link:
        return None
    summary = getattr(entry, "summary", None) or entry.get("summary") or ""
    raw = _strip_html(summary)
    # Some feeds put content in content or description
    if not raw and hasattr(entry, "content"):
        content = entry.content
        if content and len(content) > 0:
            raw = _strip_html(content[0].get("value", ""))
    if not raw:
        raw = title
    published = _parse_date(entry, feed)
    return Article(
        title=title,
        summary=summary,
        link=link,
        source=source_name,
        published=published,
        raw_text=raw,
        is_live=_is_live_story(title=title, link=link),
    )


def _serialize_article(article: Article) -> dict[str, Any]:
    return {
        "title": article.title,
        "summary": article.summary,
        "link": article.link,
        "source": article.source,
        "published": article.published.isoformat() if article.published else None,
        "raw_text": article.raw_text,
        "is_live": article.is_live,
    }


def _deserialize_article(data: dict[str, Any], fallback_source: str) -> Article | None:
    title = str(data.get("title") or "").strip()
    link = str(data.get("link") or "").strip()
    if not title or not link:
        return None

    published_raw = data.get("published")
    published = None
    if isinstance(published_raw, str) and published_raw.strip():
        try:
            published = date_parser.parse(published_raw)
        except (ValueError, TypeError):
            published = None

    summary = str(data.get("summary") or "")
    raw_text = str(data.get("raw_text") or "").strip() or _strip_html(summary) or title
    source = str(data.get("source") or "").strip() or fallback_source
    is_live = bool(data.get("is_live", False))
    return Article(
        title=title,
        summary=summary,
        link=link,
        source=source,
        published=published,
        raw_text=raw_text,
        is_live=is_live,
    )


def _load_cached_articles(
    cache: dict[str, dict[str, Any]],
    cache_key: str | None,
    fallback_source: str,
    max_articles: int,
) -> list[Article]:
    if not cache_key:
        return []
    entry = cache.get(cache_key) or {}
    raw_articles = entry.get("articles")
    if not isinstance(raw_articles, list):
        return []

    articles: list[Article] = []
    for raw in raw_articles[:max_articles]:
        if not isinstance(raw, dict):
            continue
        parsed = _deserialize_article(raw, fallback_source=fallback_source)
        if parsed:
            articles.append(parsed)
    return articles


def _newest_published_datetime(articles: list[Article]) -> datetime | None:
    newest: datetime | None = None
    for article in articles:
        published = article.published
        if published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if newest is None or published > newest:
            newest = published
    return newest


def _is_stale(articles: list[Article], threshold_minutes: int) -> bool:
    if threshold_minutes <= 0:
        return False
    newest = _newest_published_datetime(articles)
    if newest is None:
        # If source has no usable timestamps, treat as stale and allow fallback.
        return True
    age_minutes = (datetime.now(timezone.utc) - newest).total_seconds() / 60.0
    return age_minutes >= threshold_minutes


def _merge_articles(primary: list[Article], fallback: list[Article], max_articles: int) -> list[Article]:
    if not primary:
        return fallback[:max_articles]
    if not fallback:
        return primary[:max_articles]

    merged: list[Article] = []
    seen_links: set[str] = set()
    for article in primary + fallback:
        if article.link in seen_links:
            continue
        seen_links.add(article.link)
        merged.append(article)

    merged.sort(
        key=lambda article: (
            (article.published.replace(tzinfo=timezone.utc) if article.published and article.published.tzinfo is None else article.published)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    return merged[:max_articles]


def _load_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache_path: Path, cache: dict[str, dict[str, Any]]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=0)
    except OSError as e:
        logger.warning("Could not write cache %s: %s", cache_path, e)


def _resolve_local_feed_path(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme in ("http", "https"):
        return None

    # Scheme-less value: treat as a local path when present.
    direct = Path(url).expanduser()
    if direct.exists():
        return direct
    project_relative = Path(__file__).resolve().parents[1] / url
    if project_relative.exists():
        return project_relative
    return None


def fetch_feed(
    url: str,
    source_name: str,
    timeout: int = 10,
    cache: dict[str, dict[str, Any]] | None = None,
    cache_key: str | None = None,
    max_articles: int = 50,
) -> list[Article]:
    """
    Fetch one RSS/Atom feed and return list of Article.
    Uses conditional GET if cache provides etag/last_modified.
    """
    cache = cache or {}
    local_path = _resolve_local_feed_path(url)
    if local_path is not None:
        try:
            content = local_path.read_bytes()
        except OSError as e:
            logger.warning("Local feed read failed %s: %s", local_path, e)
            return []
        parsed = feedparser.parse(content)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
            logger.warning("Local feed parse error (bozo): %s", local_path)
            return []
        articles = []
        for entry in getattr(parsed, "entries", [])[:max_articles]:
            art = _normalize_entry(entry, source_name, parsed.feed)
            if art:
                articles.append(art)
        return articles

    headers = {}
    if cache_key and cache_key in cache:
        if cache[cache_key].get("etag"):
            headers["If-None-Match"] = cache[cache_key]["etag"]
        if cache[cache_key].get("last_modified"):
            headers["If-Modified-Since"] = cache[cache_key]["last_modified"]

    try:
        resp = requests.get(url, timeout=timeout, headers=headers or None)
    except requests.RequestException as e:
        logger.warning("Fetch failed %s: %s", url, e)
        return []

    if resp.status_code == 304:
        logger.debug("Feed unchanged (304): %s", url)
        return _load_cached_articles(
            cache=cache,
            cache_key=cache_key,
            fallback_source=source_name,
            max_articles=max_articles,
        )

    if resp.status_code != 200:
        logger.warning("Feed returned %s: %s", resp.status_code, url)
        return []

    # Update cache for next time
    if cache_key is not None:
        cache_entry = cache.get(cache_key) or {}
        cache[cache_key] = cache_entry
        if resp.headers.get("ETag"):
            cache_entry["etag"] = resp.headers["ETag"].strip()
        if resp.headers.get("Last-Modified"):
            cache_entry["last_modified"] = resp.headers["Last-Modified"].strip()

    parsed = feedparser.parse(resp.content, response_headers=dict(resp.headers))
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
        logger.warning("Feed parse error (bozo): %s", url)
        return []

    articles = []
    for entry in getattr(parsed, "entries", [])[:max_articles]:
        art = _normalize_entry(entry, source_name, parsed.feed)
        if art:
            articles.append(art)
    if cache_key is not None and cache_key in cache:
        cache[cache_key]["articles"] = [_serialize_article(article) for article in articles]
    return articles


def fetch_all(
    feeds: list[dict[str, Any]],
    timeout: int = 10,
    cache_file: str | Path = ".rasad_cache.json",
    max_articles_per_feed: int = 50,
) -> list[Article]:
    """
    Fetch all configured feeds and return combined list of Article.
    """
    cache_path = Path(cache_file)
    cache = _load_cache(cache_path)
    all_articles: list[Article] = []

    for feed_config in feeds:
        name = feed_config.get("name", "Unknown")
        url = feed_config.get("url", "").strip()
        if not url:
            continue
        cache_key = url
        articles = fetch_feed(
            url,
            name,
            timeout=timeout,
            cache=cache,
            cache_key=cache_key,
            max_articles=max_articles_per_feed,
        )
        if not articles:
            fallback_url = (feed_config.get("fallback_url") or "").strip()
            if fallback_url:
                fallback_name = (feed_config.get("fallback_name") or name).strip() or name
                logger.info("Primary feed empty for %s, trying fallback: %s", name, fallback_url)
                fallback_cache_key = f"fallback::{fallback_url}"
                articles = fetch_feed(
                    fallback_url,
                    fallback_name,
                    timeout=timeout,
                    cache=cache,
                    cache_key=fallback_cache_key,
                    max_articles=max_articles_per_feed,
                )
        else:
            fallback_url = (feed_config.get("fallback_url") or "").strip()
            fallback_if_older_than = int(feed_config.get("fallback_if_older_than_minutes", 0) or 0)
            if fallback_url and fallback_if_older_than > 0 and _is_stale(articles, fallback_if_older_than):
                fallback_name = (feed_config.get("fallback_name") or name).strip() or name
                logger.info(
                    "Primary feed stale for %s, trying fallback (%d min threshold): %s",
                    name,
                    fallback_if_older_than,
                    fallback_url,
                )
                fallback_cache_key = f"fallback::{fallback_url}"
                fallback_articles = fetch_feed(
                    fallback_url,
                    fallback_name,
                    timeout=timeout,
                    cache=cache,
                    cache_key=fallback_cache_key,
                    max_articles=max_articles_per_feed,
                )
                articles = _merge_articles(
                    primary=articles,
                    fallback=fallback_articles,
                    max_articles=max_articles_per_feed,
                )
        all_articles.extend(articles)
        logger.info("Fetched %s: %d articles", name, len(articles))

    _save_cache(cache_path, cache)
    return all_articles
