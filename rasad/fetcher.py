"""
RSS feed fetching with timeout, retries, and conditional GET (ETag/Last-Modified) caching.
"""
import json
import logging
import re
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


def _strip_html(text: str) -> str:
    return TAG_RE.sub(" ", text).strip() if text else ""


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
    )


def _load_cache(cache_path: Path) -> dict[str, dict[str, str]]:
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache_path: Path, cache: dict[str, dict[str, str]]) -> None:
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
    cache: dict[str, dict[str, str]] | None = None,
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
        return []

    if resp.status_code != 200:
        logger.warning("Feed returned %s: %s", resp.status_code, url)
        return []

    # Update cache for next time
    if cache_key is not None:
        cache[cache_key] = {}
        if resp.headers.get("ETag"):
            cache[cache_key]["etag"] = resp.headers["ETag"].strip()
        if resp.headers.get("Last-Modified"):
            cache[cache_key]["last_modified"] = resp.headers["Last-Modified"].strip()

    parsed = feedparser.parse(resp.content, response_headers=dict(resp.headers))
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
        logger.warning("Feed parse error (bozo): %s", url)
        return []

    articles = []
    for entry in getattr(parsed, "entries", [])[:max_articles]:
        art = _normalize_entry(entry, source_name, parsed.feed)
        if art:
            articles.append(art)
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
        all_articles.extend(articles)
        logger.info("Fetched %s: %d articles", name, len(articles))

    _save_cache(cache_path, cache)
    return all_articles
