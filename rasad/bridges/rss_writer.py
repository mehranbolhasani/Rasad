"""
Write synthetic RSS feeds from normalized Article objects.
"""
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from rasad.models import Article


def _escape_xml(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def write_articles_rss(
    articles: list[Article],
    output_path: str | Path,
    feed_title: str,
    feed_description: str,
    feed_link: str,
    language: str = "en",
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    channel_link = feed_link.strip() or "https://example.com"

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = feed_title
    SubElement(channel, "description").text = feed_description
    SubElement(channel, "link").text = channel_link
    SubElement(channel, "language").text = language
    SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    for article in articles:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = _escape_xml(article.title)
        SubElement(item, "description").text = _escape_xml(article.summary or article.raw_text)
        SubElement(item, "link").text = article.link
        SubElement(item, "guid", isPermaLink="true").text = article.link
        if article.published:
            SubElement(item, "pubDate").text = article.published.strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )

    rough = tostring(rss, encoding="unicode", default_namespace=None)
    dom = minidom.parseString(rough)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    output_path.write_text(pretty, encoding="utf-8")

