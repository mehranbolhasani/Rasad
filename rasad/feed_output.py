"""
تولید فید RSS 2.0 و API متنی JSON برای سایت رصد.
"""
import json
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from rasad.models import GroupedStory


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


def write_rss(
    stories: list[GroupedStory],
    output_path: str | Path,
    site_title: str = "رصد — اخبار جنگ",
    site_description: str = "اخبار بحران با حداقل حجم. خلاصه‌های معتبر از منابع متعدد.",
    base_url: str = "https://rasad.example.com",
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_url = base_url.rstrip("/")

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = site_title
    SubElement(channel, "description").text = site_description
    SubElement(channel, "link").text = base_url
    SubElement(channel, "language").text = "fa"
    SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    for story in stories[:50]:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = _escape_xml(story.headline)
        SubElement(item, "description").text = _escape_xml(story.summary)
        link = story.sources[0].url if story.sources else base_url
        SubElement(item, "link").text = link
        SubElement(item, "guid", isPermaLink="true").text = link
        if story.published:
            SubElement(item, "pubDate").text = story.published.strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )

    rough = tostring(rss, encoding="unicode", default_namespace=None)
    dom = minidom.parseString(rough)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    output_path.write_text(pretty, encoding="utf-8")


def _story_to_json(story: GroupedStory) -> dict:
    return {
        "headline": story.headline,
        "summary": story.summary,
        "sources": [{"name": s.name, "url": s.url} for s in story.sources],
        "confirmed": story.confirmed,
        "published": story.published.isoformat() if story.published else None,
    }


def write_json_api(
    stories: list[GroupedStory],
    output_path: str | Path,
    latest_count: int = 50,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "stories": [_story_to_json(s) for s in stories[:latest_count]],
    }
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8"
    )
