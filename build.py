#!/usr/bin/env python3
"""
خط لوله ساخت رصد:
  دریافت RSS → فیلتر کلیدواژه → خلاصه‌سازی → ترجمه مقالات انگلیسی → گروه‌بندی → تولید HTML ایستا
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from rasad.fetcher import fetch_all
from rasad.filter import filter_articles
from rasad.grouper import group_articles
from rasad.summarizer import summarize_articles
from rasad.translator import translate_articles
from rasad.generator import generate
from rasad.feed_output import write_rss, write_json_api
from rasad.text_output import write_text_digests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _slugify(name: str) -> str:
    value = (name or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "source"


def _bridge_feed_entries(config: dict, project_root: Path) -> list[dict]:
    bridge_cfg = config.get("bridge_feeds") or {}
    output_dir_name = bridge_cfg.get("output_dir", "bridges")
    bridge_dir = project_root / output_dir_name
    entries: list[dict] = []

    for source in bridge_cfg.get("sources") or []:
        if source.get("enabled", True) is False:
            continue
        if source.get("include_in_main", True) is False:
            continue
        source_name = source.get("name", "Unknown")
        slug = source.get("slug") or _slugify(source_name)
        path = bridge_dir / f"{slug}.xml"
        if not path.exists() or path.stat().st_size < 200:
            # Skip missing/empty bridge files. Builder will continue with other sources.
            continue
        entries.append(
            {
                "name": source_name,
                "url": str(path),
                "language": source.get("language", "en"),
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Rasad static site")
    parser.add_argument("--config", default="config.yaml", help="Config YAML path")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print stories, no HTML")
    parser.add_argument(
        "--filter-debug",
        action="store_true",
        help="Write filter decision report to output/filter_debug.json",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    output_dir = Path(args.output or config.get("output", {}).get("dir", "output"))
    project_root = Path(__file__).resolve().parent
    templates_dir = project_root / "templates"
    static_dir = project_root / "static"

    feeds = list(config.get("feeds", []))
    feeds.extend(_bridge_feed_entries(config=config, project_root=project_root))
    keywords = config.get("keywords", [])
    filtering_cfg = config.get("filtering", {})
    required_keywords = filtering_cfg.get("required_keywords", [])
    min_matches = filtering_cfg.get("min_matches", 1)
    fetch_cfg = config.get("fetch", {})
    summarization_cfg = config.get("summarization", {})
    translation_cfg = config.get("translation", {})
    grouper_cfg = config.get("grouper", {})
    output_cfg = config.get("output", {})
    site_cfg = config.get("site", {})

    # ۱. دریافت فیدها
    logger.info("Fetching RSS feeds...")
    articles = fetch_all(
        feeds,
        timeout=fetch_cfg.get("timeout_seconds", 10),
        cache_file=project_root / fetch_cfg.get("cache_file", ".rasad_cache.json"),
        max_articles_per_feed=fetch_cfg.get("max_articles_per_feed", 50),
    )
    logger.info("Fetched %d articles total", len(articles))

    # ۲. فیلتر کلیدواژه
    debug_report = None
    if args.filter_debug:
        articles, debug_rows = filter_articles(
            articles,
            keywords,
            required_keywords=required_keywords,
            min_matches=min_matches,
            return_debug=True,
        )
        debug_report = {
            "fetched_count": len(debug_rows),
            "passed_count": len(articles),
            "rejected_count": len(debug_rows) - len(articles),
            "min_matches": min_matches,
            "required_keywords": required_keywords,
            "entries": [row.__dict__ for row in debug_rows],
        }
    else:
        articles = filter_articles(
            articles,
            keywords,
            required_keywords=required_keywords,
            min_matches=min_matches,
        )
    logger.info("After keyword filter: %d articles", len(articles))
    if debug_report is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        debug_path = output_dir / "filter_debug.json"
        debug_path.write_text(
            json.dumps(debug_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Filter debug report written to %s", debug_path)

    if not articles:
        logger.warning("No articles after filtering.")
        if args.dry_run:
            return 0
        stories = []
    else:
        # ۳. خلاصه‌سازی
        articles = summarize_articles(
            articles,
            mode=summarization_cfg.get("mode", "extractive"),
            max_sentences=summarization_cfg.get("max_sentences", 3),
        )

        # ۴. ترجمه مقالات انگلیسی به فارسی
        translation_mode = translation_cfg.get("mode", "ai")
        if translation_mode != "none":
            articles = translate_articles(
                articles,
                feeds_config=feeds,
                mode=translation_mode,
                post_edit_enabled=translation_cfg.get("post_edit", False),
                post_edit_limit=translation_cfg.get("post_edit_limit", 15),
            )

        # ۵. گروه‌بندی
        stories = group_articles(
            articles,
            similarity_threshold=grouper_cfg.get("similarity_threshold", 0.3),
            confirmed_min_sources=grouper_cfg.get("confirmed_min_sources", 3),
            secondary_title_threshold=grouper_cfg.get("secondary_title_threshold", 0.14),
            secondary_time_window_hours=grouper_cfg.get("secondary_time_window_hours", 6),
            max_age_hours=grouper_cfg.get("max_age_hours", 72),
            live_mixed_similarity_threshold=grouper_cfg.get("live_mixed_similarity_threshold", 0.6),
            live_penalty=grouper_cfg.get("live_penalty", 0.3),
            source_diversity_bonus_cap=grouper_cfg.get("source_diversity_bonus_cap", 0.15),
        )
        logger.info("Grouped into %d stories", len(stories))

    if args.dry_run:
        for i, s in enumerate(stories[:10], 1):
            print(f"  {i}. {s.headline[:80]} ({len(s.sources)} sources)")
        if len(stories) > 10:
            print(f"  ... and {len(stories) - 10} more.")
        return 0

    # ۶. تولید سایت ایستا
    generate(
        stories,
        output_dir=output_dir,
        templates_dir=templates_dir,
        static_dir=static_dir,
        site_config=site_cfg,
        latest_count=output_cfg.get("latest_count", 20),
    )
    logger.info("Generated HTML in %s", output_dir)

    # ۷. فید RSS و API
    write_rss(
        stories,
        output_dir / "feed.xml",
        site_title=site_cfg.get("title", "رصد — اخبار جنگ"),
        site_description=site_cfg.get("description", "اخبار بحران با حداقل حجم."),
        base_url=site_cfg.get("base_url", "").strip() or "/",
    )
    (output_dir / "api").mkdir(parents=True, exist_ok=True)
    write_json_api(stories, output_dir / "api" / "latest.json", latest_count=50)
    write_text_digests(
        stories,
        output_dir=output_dir,
        site_title=site_cfg.get("title", "رصد — اخبار جنگ"),
        latest_count=output_cfg.get("latest_count", 20),
    )
    logger.info("Generated feed.xml and api/latest.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
