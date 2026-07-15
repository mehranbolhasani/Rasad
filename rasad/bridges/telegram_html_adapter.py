"""
Telegram public channel preview adapter (t.me/s/...).

Fetches the public web preview for a channel and maps posts to Article objects.
"""
import logging
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from rasad.bridges.base import BaseAdapter
from rasad.bridges.telegram_sanitize import (
    sanitize_telegram_text,
    should_include_telegram_post,
    title_from_telegram_text,
)
from rasad.fetcher import _is_safe_url
from rasad.models import Article

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TITLE_MAX_LEN = 120
_CHANNEL_RE = re.compile(r"^@?([A-Za-z0-9_]{3,})$")


class TelegramHtmlAdapter(BaseAdapter):
    """Fetch Telegram channel previews and map posts to Article."""

    @staticmethod
    def _resolve_channel(source_config: dict) -> str:
        channel = (source_config.get("channel") or "").strip().lstrip("@")
        if channel:
            match = _CHANNEL_RE.match(channel)
            if match:
                return match.group(1)

        url = (source_config.get("url") or "").strip()
        if url:
            path = urlparse(url).path.strip("/")
            if path.startswith("s/"):
                candidate = path.split("/", 1)[1].split("/")[0]
                if _CHANNEL_RE.match(candidate):
                    return candidate.lstrip("@")
            if path and "/" not in path and _CHANNEL_RE.match(path):
                return path.lstrip("@")

        return ""

    @staticmethod
    def _preview_url(channel: str) -> str:
        return f"https://t.me/s/{channel}"

    @staticmethod
    def _strip_channel_footer(text: str, channel: str) -> str:
        channel = channel.lstrip("@")
        cleaned = text.strip()
        for pattern in (
            rf"\s*📡\s*@{re.escape(channel)}\s*$",
            rf"\s*@{re.escape(channel)}\s*$",
            r"\s*Vahid\s*$",
        ):
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @staticmethod
    def _message_text(wrap: BeautifulSoup) -> str:
        node = wrap.select_one(".tgme_widget_message_text")
        if not node:
            return ""
        return node.get_text("\n", strip=True)

    @staticmethod
    def _is_service_message(message: BeautifulSoup) -> bool:
        classes = message.get("class") or []
        return "service" in classes

    @staticmethod
    def _message_link(message: BeautifulSoup, wrap: BeautifulSoup, channel: str) -> str:
        date_link = wrap.select_one("a.tgme_widget_message_date")
        if date_link:
            href = (date_link.get("href") or "").strip()
            if href:
                return href

        data_post = (message.get("data-post") or "").strip()
        if data_post:
            return f"https://t.me/{data_post}"

        return f"https://t.me/{channel}"

    @staticmethod
    def _message_published(wrap: BeautifulSoup):
        time_node = wrap.select_one("time[datetime]")
        if not time_node:
            return None
        raw = (time_node.get("datetime") or "").strip()
        if not raw:
            return None
        try:
            return date_parser.parse(raw)
        except (TypeError, ValueError):
            return None

    def fetch(self, source_config: dict, timeout: int = 10) -> list[Article]:
        channel = self._resolve_channel(source_config)
        if not channel:
            logger.warning(
                "Telegram bridge missing channel for %s",
                source_config.get("name", "Unknown"),
            )
            return []

        url = self._preview_url(channel)
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        }
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Telegram bridge fetch failed %s: %s", url, exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        wraps = soup.select(".tgme_widget_message_wrap")
        if not wraps:
            logger.info("Telegram bridge found no messages for %s", channel)
            return []

        source_name = source_config.get("name", channel)
        max_items = int(source_config.get("max_items", 50))
        telegram_cfg = source_config.get("telegram") or {}
        articles: list[Article] = []
        skipped = 0

        for wrap in wraps:
            message = wrap.select_one(".tgme_widget_message")
            if not message or self._is_service_message(message):
                continue

            raw_text = self._message_text(wrap)
            footer_stripped = self._strip_channel_footer(raw_text, channel)
            if not footer_stripped:
                continue

            preview_title = title_from_telegram_text(
                sanitize_telegram_text(footer_stripped, channel=channel)
            )
            if not should_include_telegram_post(
                footer_stripped,
                preview_title,
                telegram_cfg=telegram_cfg,
                raw_text=footer_stripped,
            ):
                skipped += 1
                continue

            text = sanitize_telegram_text(footer_stripped, channel=channel)
            if not text:
                continue

            title = title_from_telegram_text(text)
            if len(title) < 5:
                continue

            link = self._message_link(message, wrap, channel)
            if not _is_safe_url(link):
                logger.debug("Skipping Telegram item with unsafe link: %s", link)
                continue

            articles.append(
                Article(
                    title=title,
                    summary=text,
                    link=link,
                    source=source_name,
                    published=self._message_published(wrap),
                    raw_text=text,
                )
            )

        if skipped:
            logger.info(
                "Telegram bridge skipped %d posts for %s after channel rules",
                skipped,
                source_name,
            )

        articles.reverse()
        return articles[-max_items:]
