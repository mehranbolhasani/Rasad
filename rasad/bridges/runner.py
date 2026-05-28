"""
Bridge feed runner for non-RSS sources.
"""
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from rasad.bridges.html_adapter import HTMLAdapter
from rasad.bridges.json_adapter import JSONAdapter
from rasad.bridges.rss_writer import write_articles_rss

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Create a filesystem-safe slug from a name. Preserves Persian/Unicode letters."""
    value = (name or "").strip().lower()
    # Keep letters (including Persian \u0600-\u06FF), digits, and whitespace
    value = re.sub(r"[^\w\s\u0600-\u06FF]+", "-", value, flags=re.UNICODE)
    # Collapse whitespace to hyphens
    value = re.sub(r"\s+", "-", value)
    value = value.strip("-")
    return value or "source"


def _load_config(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _pick_adapter(source_type: str):
    adapters = {
        "html": HTMLAdapter(),
        "json": JSONAdapter(),
    }
    return adapters.get(source_type)


def _is_quality_article(article) -> bool:
    """Reject clearly broken bridge items (empty/short title, title equals link, etc.)."""
    title = (article.title or "").strip()
    if len(title) < 5:
        return False
    link = (article.link or "").strip()
    if title == link:
        return False
    return True


def run_bridges(config: dict[str, Any], project_root: Path, timeout: int = 10) -> list[Path]:
    bridge_cfg = config.get("bridge_feeds") or {}
    output_dir_name = bridge_cfg.get("output_dir", "bridges")
    output_dir = (project_root / output_dir_name).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[Path] = []
    for source in bridge_cfg.get("sources") or []:
        source_name = source.get("name", "Unknown source")
        source_type = (source.get("type") or "").strip().lower()
        adapter = _pick_adapter(source_type)
        if not adapter:
            logger.warning("Unsupported bridge source type '%s' for %s", source_type, source_name)
            continue

        try:
            articles = adapter.fetch(source, timeout=timeout)
        except Exception as exc:  # defensive barrier per-source
            logger.warning("Bridge adapter failed for %s: %s", source_name, exc)
            continue

        before = len(articles)
        articles = [a for a in articles if _is_quality_article(a)]
        after = len(articles)
        if after < before:
            logger.info("Bridge quality filter dropped %d low-quality items for %s", before - after, source_name)

        slug = source.get("slug") or _slugify(source_name)
        output_path = output_dir / f"{slug}.xml"
        write_articles_rss(
            articles,
            output_path=output_path,
            feed_title=source_name,
            feed_description=source.get("description", f"Bridge RSS for {source_name}"),
            feed_link=source.get("url", ""),
            language=source.get("language", "en"),
        )
        generated_files.append(output_path)
        logger.info("Bridge generated %s: %d articles", output_path, len(articles))

    return generated_files


def run_bridges_from_config_path(config_path: str | Path, timeout: int = 10) -> list[Path]:
    config_path = Path(config_path)
    config = _load_config(config_path)
    project_root = config_path.resolve().parent
    return run_bridges(config=config, project_root=project_root, timeout=timeout)

