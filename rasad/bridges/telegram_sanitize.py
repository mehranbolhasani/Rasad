"""
Sanitization and content selection for Telegram channel previews.
"""
import re

_LEAD_MARKERS = ("🔴", "✋", "📣", "📌", "⚽️", "🏐")
_DECORATIVE_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D"
    r"\u25AA\u25AB\u25B6\u25C0\u25CF\u25A0\u25A1\u25B2\u25BC"
    r"\u2714\u2716\u2795\u2796\u2797"
    r"0-9#*]+"
)
_NUMBERED_BULLET_RE = re.compile(r"^[0-9\u2460-\u2473\u24EA-\u24FF\u2776-\u277F\uFE0F\u20E3]+\s*")
_CHANNEL_MENTION_RE = re.compile(r"@\w[\w_]{2,}\s*$", re.IGNORECASE)
_HASHTAG_LINE_RE = re.compile(r"^#\S+(\s+#\S+)*\s*$")
_SUBSTANTIVE_LINE_RE = re.compile(r"[\w\u0600-\u06FF]", re.UNICODE)
_TITLE_MAX_LEN = 120


def _compile_patterns(patterns: list[str] | None) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns or []:
        raw = (pattern or "").strip()
        if not raw:
            continue
        compiled.append(re.compile(raw, re.IGNORECASE | re.UNICODE))
    return compiled


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _strip_decorative_prefix(line: str) -> str:
    cleaned = line.strip()
    while cleaned:
        next_value = _DECORATIVE_RE.sub("", cleaned, count=1).strip()
        next_value = _NUMBERED_BULLET_RE.sub("", next_value).strip()
        if next_value == cleaned:
            break
        cleaned = next_value
    return cleaned


def _lead_marker(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for marker in _LEAD_MARKERS:
            if stripped.startswith(marker):
                return marker
        break
    return ""


def sanitize_telegram_text(text: str, channel: str = "") -> str:
    """Normalize Telegram post text for Rasad summaries."""
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _strip_decorative_prefix(raw_line.strip())
        if not line:
            continue
        if _HASHTAG_LINE_RE.match(line):
            continue
        if line in {"ترجمه ماشین:", "ترجمه ماشینی:"}:
            continue
        if channel and re.search(rf"@{re.escape(channel.lstrip('@'))}\s*$", line, re.IGNORECASE):
            continue
        line = _CHANNEL_MENTION_RE.sub("", line).strip()
        if line:
            lines.append(line)

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def title_from_telegram_text(text: str) -> str:
    """Pick the first substantive line as a headline."""
    for line in text.splitlines():
        candidate = _strip_decorative_prefix(line.strip())
        if len(candidate) < 5:
            continue
        if not _SUBSTANTIVE_LINE_RE.search(candidate):
            continue
        if len(candidate) <= _TITLE_MAX_LEN:
            return candidate
        truncated = candidate[:_TITLE_MAX_LEN].rsplit(" ", 1)[0]
        return (truncated or candidate[:_TITLE_MAX_LEN]).rstrip() + "…"
    fallback = text.strip()
    if len(fallback) <= _TITLE_MAX_LEN:
        return fallback
    truncated = fallback[:_TITLE_MAX_LEN].rsplit(" ", 1)[0]
    return (truncated or fallback[:_TITLE_MAX_LEN]).rstrip() + "…"


def should_include_telegram_post(
    text: str,
    title: str,
    telegram_cfg: dict | None = None,
    *,
    raw_text: str | None = None,
) -> bool:
    """Apply per-channel inclusion rules before articles enter the pipeline."""
    cfg = telegram_cfg or {}
    lead_source = raw_text or text
    combined = f"{title}\n{text}".strip()
    if not combined:
        return False

    exclude_patterns = _compile_patterns(cfg.get("exclude_patterns"))
    if _matches_any(title, exclude_patterns) or _matches_any(combined, exclude_patterns):
        return False

    include_patterns = _compile_patterns(cfg.get("include_patterns"))
    if include_patterns and not _matches_any(combined, include_patterns):
        return False

    allowed_markers = cfg.get("allowed_lead_markers") or []
    if allowed_markers:
        marker = _lead_marker(lead_source)
        if marker not in allowed_markers:
            return False

    min_chars = int(cfg.get("min_text_chars", 0))
    if min_chars and len(text.strip()) < min_chars:
        return False

    return True
