"""
HTML bridge adapter for non-RSS sources.
"""
import logging
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from rasad.bridges.base import BaseAdapter
from rasad.models import Article

logger = logging.getLogger(__name__)


class HTMLAdapter(BaseAdapter):
    """Fetch HTML pages and map elements to Article."""

    def _allowed_by_robots(self, url: str, user_agent: str = "RasadBot") -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except OSError:
            logger.debug("Could not read robots.txt for %s", url)
            return True
        return parser.can_fetch(user_agent, url)

    @staticmethod
    def _select_text(node: BeautifulSoup, selector: str | None) -> str:
        if not selector:
            return ""
        target = node.select_one(selector)
        return target.get_text(" ", strip=True) if target else ""

    @staticmethod
    def _select_href(node: BeautifulSoup, selector: str | None) -> str:
        if not selector:
            return ""
        target = node.select_one(selector)
        if not target:
            return ""
        return (target.get("href") or "").strip()

    def fetch(self, source_config: dict, timeout: int = 10) -> list[Article]:
        url = (source_config.get("url") or "").strip()
        if not url:
            return []

        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        if not self._allowed_by_robots(url, user_agent=user_agent):
            logger.warning("Blocked by robots.txt: %s", url)
            return []

        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Bridge HTML fetch failed %s: %s", url, exc)
            return []

        selectors = source_config.get("selectors") or {}
        item_selector = selectors.get("items")
        if not item_selector:
            logger.warning("Bridge HTML source missing selectors.items: %s", source_config.get("name"))
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        nodes = soup.select(item_selector)
        if not nodes:
            return []

        source_name = source_config.get("name", "Unknown")
        articles: list[Article] = []
        max_items = int(source_config.get("max_items", 50))
        for node in nodes[:max_items]:
            title = self._select_text(node, selectors.get("title"))
            href = self._select_href(node, selectors.get("link"))
            summary = self._select_text(node, selectors.get("summary"))
            date_text = self._select_text(node, selectors.get("date"))

            if not href and selectors.get("title"):
                # Common case: title selector already points to an anchor.
                href = self._select_href(node, selectors.get("title"))
            if not title and selectors.get("link"):
                title = self._select_text(node, selectors.get("link"))

            link = urljoin(url, href) if href else ""
            if not title or not link:
                continue

            published = None
            if date_text:
                try:
                    published = date_parser.parse(date_text)
                except (TypeError, ValueError):
                    published = None

            articles.append(
                Article(
                    title=title,
                    summary=summary,
                    link=link,
                    source=source_name,
                    published=published,
                    raw_text=summary or title,
                )
            )
        return articles

