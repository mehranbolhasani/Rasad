"""
JSON API bridge adapter for non-RSS sources.
"""
import logging
from urllib.parse import urljoin

import requests
from dateutil import parser as date_parser

from rasad.bridges.base import BaseAdapter
from rasad.models import Article

logger = logging.getLogger(__name__)


def _get_path_value(data, path: str, default=None):
    """
    Resolve a dotted path from dict/list values.
    Example: data.articles.0.title
    """
    if not path:
        return default
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            if not part.isdigit():
                return default
            idx = int(part)
            if idx < 0 or idx >= len(current):
                return default
            current = current[idx]
            continue
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue
        return default
    return current


class JSONAdapter(BaseAdapter):
    """Fetch JSON endpoint and map objects to Article."""

    def fetch(self, source_config: dict, timeout: int = 10) -> list[Article]:
        url = (source_config.get("url") or "").strip()
        if not url:
            return []

        headers = {"User-Agent": "RasadBot/1.0 (+https://rasad.example.com)"}
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Bridge JSON fetch failed %s: %s", url, exc)
            return []

        json_map = source_config.get("json_map") or {}
        items_path = json_map.get("items", "")
        items = _get_path_value(payload, items_path, default=[])
        if not isinstance(items, list):
            logger.warning("Bridge JSON items path did not resolve to list: %s", source_config.get("name"))
            return []

        source_name = source_config.get("name", "Unknown")
        max_items = int(source_config.get("max_items", 50))
        articles: list[Article] = []
        for item in items[:max_items]:
            if not isinstance(item, dict):
                continue
            title = _get_path_value(item, json_map.get("title", ""), default="") or ""
            link = _get_path_value(item, json_map.get("link", ""), default="") or ""
            summary = _get_path_value(item, json_map.get("summary", ""), default="") or ""
            date_raw = _get_path_value(item, json_map.get("date", ""), default="") or ""

            if not title or not link:
                continue
            link = urljoin(url, str(link))

            published = None
            if date_raw:
                try:
                    published = date_parser.parse(str(date_raw))
                except (TypeError, ValueError):
                    published = None

            articles.append(
                Article(
                    title=str(title).strip(),
                    summary=str(summary).strip(),
                    link=link.strip(),
                    source=source_name,
                    published=published,
                    raw_text=(str(summary).strip() or str(title).strip()),
                )
            )
        return articles

