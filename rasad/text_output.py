"""
Generate lightweight plain-text news digests for offline/low-bandwidth use.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from rasad.models import GroupedStory


def _fmt_updated_tehran() -> str:
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    return now.strftime("%Y-%m-%d %H:%M")


def _status_label(confirmed: bool) -> str:
    return "چند منبع تأیید کرده" if confirmed else "تنها یک منبع"


def _normalize_line(text: str) -> str:
    return " ".join((text or "").split())


def _story_sort_key(story: GroupedStory) -> float:
    if not story.published:
        return 0.0
    published = story.published
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    try:
        return published.timestamp()
    except (AttributeError, OSError):
        return 0.0


def write_text_digests(
    stories: list[GroupedStory],
    output_dir: str | Path,
    site_title: str,
    latest_count: int = 20,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ordered = sorted(stories, key=_story_sort_key, reverse=True)
    batch = ordered[:latest_count]
    updated = _fmt_updated_tehran()

    detailed_lines = [
        site_title,
        f"آخرین آپدیت: {updated}",
        f"تعداد خبرها: {len(batch)}",
        "",
        "=" * 48,
        "",
    ]
    compact_lines = [
        site_title,
        f"آخرین آپدیت: {updated}",
        f"تعداد خبرها: {len(batch)}",
        "",
    ]

    for idx, story in enumerate(batch, start=1):
        summary = _normalize_line(story.summary)
        headline = _normalize_line(story.headline)
        status = _status_label(story.confirmed)

        detailed_lines.extend(
            [
                f"{idx:02d}) [{status}] {headline}",
                f"خلاصه: {summary}",
                "منابع:",
            ]
        )
        for s_idx, source in enumerate(story.sources, start=1):
            detailed_lines.append(f"  {s_idx}. {source.name}: {source.url}")
        detailed_lines.extend(["", "-" * 48, ""])

        first_source = story.sources[0] if story.sources else None
        if first_source:
            compact_lines.append(
                f"{idx:02d}) [{status}] {headline} | {_normalize_line(summary)} | {first_source.name}: {first_source.url}"
            )
        else:
            compact_lines.append(f"{idx:02d}) [{status}] {headline} | {_normalize_line(summary)}")

    # Use UTF-8 BOM to improve compatibility with browsers/clients that do not
    # reliably honor text/plain charset for non-Latin content.
    (output_dir / "latest.txt").write_text(
        "\n".join(detailed_lines).strip() + "\n",
        encoding="utf-8-sig",
    )
    (output_dir / "latest-compact.txt").write_text(
        "\n".join(compact_lines).strip() + "\n",
        encoding="utf-8-sig",
    )

