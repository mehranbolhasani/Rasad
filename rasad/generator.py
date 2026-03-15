"""
تولید سایت ایستا: قالب‌های Jinja2 به output/.
تمام صفحات به زبان فارسی و با چیدمان راست‌به‌چپ تولید می‌شوند.
"""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from rasad.models import GroupedStory

LABELS = {
    "site_title": "رصد — اخبار جنگ",
    "nav_text_full": "دانلود نسخه متنی",
    "nav_text_compact": "نسخه متنی کم‌حجم",
    "label_confirmed": "چند منبع تأیید کرده",
    "label_reported": "تنها یک منبع",
    "label_sources": "منبع",
    "footer_no_tracking": "بدون ردیابی. بدون کوکی.",
    "footer_mirror": "آینه‌سازی: wget --mirror --convert-links [آدرس سایت]",
}


PERSIAN_MONTHS = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]


def _to_persian_digits(text: str) -> str:
    return text.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """
    Convert Gregorian date to Jalali (Solar Hijri).
    """
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def _format_last_updated_tehran() -> str:
    tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
    jy, jm, jd = _gregorian_to_jalali(
        tehran_now.year,
        tehran_now.month,
        tehran_now.day,
    )
    day_text = _to_persian_digits(str(jd))
    year_text = _to_persian_digits(str(jy))
    time_text = _to_persian_digits(tehran_now.strftime("%H:%M"))
    return f"آخرین آپدیت: {day_text} {PERSIAN_MONTHS[jm - 1]} {year_text} | {time_text}"


def _base_context(
    base_url: str,
    last_updated: str,
    stylesheet_href: str,
    site_title: str | None = None,
) -> dict[str, Any]:
    labels = dict(LABELS)
    if site_title:
        labels["site_title"] = site_title
    return {
        "lang": "fa",
        "dir": "rtl",
        "title": labels["site_title"],
        "site_title": labels["site_title"],
        "base_url": base_url.rstrip("/"),
        "last_updated": last_updated,
        "stylesheet_href": stylesheet_href,
        "nav_text_full": labels["nav_text_full"],
        "nav_text_compact": labels["nav_text_compact"],
        "label_confirmed": labels["label_confirmed"],
        "label_reported": labels["label_reported"],
        "label_sources": labels["label_sources"],
        "footer_no_tracking": labels["footer_no_tracking"],
        "footer_mirror": labels["footer_mirror"],
    }


def _safe_ts(dt: datetime | None) -> float:
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.timestamp()
    except (AttributeError, OSError):
        return 0.0


def generate(
    stories: list[GroupedStory],
    output_dir: str | Path,
    templates_dir: str | Path,
    static_dir: str | Path,
    site_config: dict[str, Any],
    latest_count: int = 20,
) -> None:
    output_dir = Path(output_dir)
    templates_dir = Path(templates_dir)
    static_dir = Path(static_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_url = site_config.get("base_url", "").strip() or "/"
    site_title = site_config.get("title") or LABELS["site_title"]
    last_updated = _format_last_updated_tehran()

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(("html", "htm")),
    )
    style_src = static_dir / "style.css"
    style_dst = output_dir / "style.css"
    if style_src.exists():
        shutil.copy2(style_src, style_dst)
    project_root = Path(__file__).resolve().parents[1]
    favicon_src = project_root / "favicon.ico"
    if favicon_src.exists():
        shutil.copy2(favicon_src, output_dir / "favicon.ico")
    # Archive pages are retired. Remove stale archive directory if present.
    shutil.rmtree(output_dir / "archive", ignore_errors=True)
    # Defensive ordering: always render newest stories first on HTML pages.
    stories = sorted(
        stories,
        key=lambda s: _safe_ts(s.published),
        reverse=True,
    )
    latest = stories[:latest_count]

    # صفحه اصلی
    ctx = _base_context(base_url, last_updated, "style.css", site_title)
    ctx["stories"] = latest
    html = env.get_template("index.html").render(**ctx)
    output_dir.joinpath("index.html").write_text(html, encoding="utf-8")
