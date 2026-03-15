"""
Group articles that refer to the same event using token overlap (Jaccard similarity).
Each group becomes one GroupedStory with merged headline, combined summary, and source list.
"""
import re
from datetime import datetime, timezone

from rasad.models import Article, GroupedStory, SourceRef

FA_STOPWORDS = {
    "و", "در", "از", "به", "که", "را", "با", "برای", "این", "آن", "یک", "بر",
    "اما", "اگر", "تا", "نیز", "پس", "هم", "می", "شود", "کرد", "کرده", "شده",
    "است", "بود", "خواهد", "دارد", "بین", "روی", "زیر", "پس", "روز",
}

EN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "will", "are", "was",
    "were", "has", "have", "had", "into", "over", "under", "after", "before",
    "amid", "about", "their", "they", "its", "his", "her", "said", "says",
    "news", "live", "update",
}

TOKEN_CANONICAL = {
    # Common normalization to improve cross-outlet matching
    "us": "usa",
    "u.s": "usa",
    "united": "usa",
    "states": "usa",
    "america": "usa",
    "ایالات": "امریکا",
    "متحده": "امریکا",
    "آمریکا": "امریکا",
    "اسرائیلی": "اسرائیل",
    "israeli": "israel",
    "iranian": "iran",
    "ایرانی": "ایران",
    "tehran": "تهران",
    "hormuz": "هرمز",
    "kharg": "خارگ",
}


def _normalize_text(text: str) -> str:
    """Normalize Arabic/Persian variants and strip punctuation noise."""
    if not text:
        return ""
    normalized = (
        text.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
        .replace("\u200c", " ")
    )
    return normalized.lower()


def _tokenize(text: str) -> set[str]:
    """Extract normalized keywords, removing stopwords and noise."""
    if not text:
        return set()
    normalized = _normalize_text(text)
    tokens = re.findall(r"[\w\u0600-\u06FF]{2,}", normalized)
    cleaned: set[str] = set()
    for token in tokens:
        canonical = TOKEN_CANONICAL.get(token, token)
        if canonical in FA_STOPWORDS or canonical in EN_STOPWORDS:
            continue
        if canonical.isdigit():
            continue
        if len(canonical) < 2:
            continue
        cleaned.add(canonical)
    return cleaned


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _text_for_similarity(article: Article) -> str:
    # Use title + summary first because summaries are translated to Farsi
    # for EN sources before grouping. raw_text may remain in original language.
    core = f"{article.title} {article.summary}".strip()
    if core:
        return core
    return f"{article.title} {article.raw_text}"


def _title_for_similarity(article: Article) -> str:
    return _normalize_text(article.title or "")


def _published_ts(article: Article) -> float | None:
    if article.published is None:
        return None
    try:
        published = article.published
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published.timestamp()
    except (AttributeError, OSError):
        return None


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _story_ts(story: GroupedStory) -> float:
    if story.published is None:
        return 0.0
    try:
        return _as_utc(story.published).timestamp()
    except (AttributeError, OSError):
        return 0.0


def _median_published_for_group(group: list[Article]) -> datetime | None:
    source_latest_ts: dict[str, float] = {}
    for article in group:
        ts = _published_ts(article)
        if ts is None:
            continue
        source_key = (article.source or "").strip() or "__unknown__"
        prev = source_latest_ts.get(source_key)
        if prev is None or ts > prev:
            source_latest_ts[source_key] = ts
    if not source_latest_ts:
        return None
    ordered = sorted(source_latest_ts.values())
    size = len(ordered)
    mid = size // 2
    if size % 2 == 1:
        median_ts = ordered[mid]
    else:
        median_ts = (ordered[mid - 1] + ordered[mid]) / 2.0
    return datetime.fromtimestamp(median_ts, tz=timezone.utc)


def _is_mixed_live_pair(article1: Article, article2: Article) -> bool:
    return bool(article1.is_live) ^ bool(article2.is_live)


def _title_similarity(article1: Article, article2: Article) -> float:
    t1 = _tokenize(_title_for_similarity(article1))
    t2 = _tokenize(_title_for_similarity(article2))
    return jaccard(t1, t2)


def similarity(article1: Article, article2: Article) -> float:
    # Weighted similarity:
    # - title overlap is more important than body overlap for event matching
    title_a = _tokenize(_title_for_similarity(article1))
    title_b = _tokenize(_title_for_similarity(article2))
    text_a = _tokenize(_text_for_similarity(article1))
    text_b = _tokenize(_text_for_similarity(article2))

    title_score = jaccard(title_a, title_b)
    text_score = jaccard(text_a, text_b)
    return 0.65 * title_score + 0.35 * text_score


def group_articles(
    articles: list[Article],
    similarity_threshold: float = 0.3,
    confirmed_min_sources: int = 3,
    secondary_title_threshold: float = 0.14,
    secondary_time_window_hours: int = 6,
    max_age_hours: int = 72,
    live_mixed_similarity_threshold: float = 0.6,
    live_penalty: float = 0.3,
    source_diversity_bonus_cap: float = 0.15,
) -> list[GroupedStory]:
    """
    Cluster articles by similarity. Each cluster becomes one GroupedStory.
    Headline from first (or highest-ranked) article; summary combined from first;
    sources list all; confirmed = True if group has at least confirmed_min_sources.
    """
    if not articles:
        return []
    now_ts = datetime.now(timezone.utc).timestamp()
    if max_age_hours > 0:
        min_ts = now_ts - (max_age_hours * 3600)
        filtered_articles = []
        for article in articles:
            ts = _published_ts(article)
            if ts is None or ts >= min_ts:
                filtered_articles.append(article)
        articles = filtered_articles
        if not articles:
            return []

    # Build adjacency: for each article, which others are similar enough
    n = len(articles)
    similar: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        similar[i].add(i)
        for j in range(i + 1, n):
            is_mixed_live_pair = _is_mixed_live_pair(articles[i], articles[j])
            required_threshold = similarity_threshold
            if is_mixed_live_pair:
                required_threshold = max(similarity_threshold, live_mixed_similarity_threshold)
            sim = similarity(articles[i], articles[j])
            if sim >= required_threshold:
                similar[i].add(j)
                similar[j].add(i)
                continue

            if is_mixed_live_pair:
                continue

            # Second-pass merge rule:
            # If two headlines are very similar and published near each other,
            # treat them as same event even when full-text similarity is lower.
            ts_i = _published_ts(articles[i])
            ts_j = _published_ts(articles[j])
            if ts_i is None or ts_j is None:
                continue
            within_window = abs(ts_i - ts_j) <= secondary_time_window_hours * 3600
            if not within_window:
                continue
            title_sim = _title_similarity(articles[i], articles[j])
            if title_sim >= secondary_title_threshold:
                similar[i].add(j)
                similar[j].add(i)

    # Union-find to get connected components
    parent = list(range(n))

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in similar[i]:
            union(i, j)

    # Collect components
    components: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        components.setdefault(root, []).append(i)

    stories = []
    for indices in components.values():
        group = [articles[i] for i in indices]
        # Sort by date descending (newest first) for headline/summary
        def _sort_key(a: Article) -> float:
            if a.published is None:
                return 0.0
            try:
                published = a.published
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                return published.timestamp()
            except (AttributeError, OSError):
                return 0.0
        group.sort(key=_sort_key, reverse=True)
        first = group[0]
        headline = first.title
        summary = first.summary
        sources = [SourceRef(name=a.source, url=a.link) for a in group]
        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_sources: list[SourceRef] = []
        for s in sources:
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                unique_sources.append(s)
        # Use median timestamp across unique sources to avoid one live feed pinning top forever.
        published = _median_published_for_group(group) or first.published
        confirmed = len(unique_sources) >= confirmed_min_sources
        stories.append(
            GroupedStory(
                headline=headline,
                summary=summary,
                sources=unique_sources,
                confirmed=confirmed,
                published=published,
            )
        )

    story_meta_by_headline = {
        story.headline: {
            "sources_count": len(story.sources),
            "is_live": bool(story.headline and _normalize_text(story.headline).startswith("آنچه گذشت")),
        }
        for story in stories
    }
    for indices in components.values():
        group = [articles[i] for i in indices]
        if not group:
            continue
        first = max(group, key=lambda a: _published_ts(a) or 0.0)
        if first.title in story_meta_by_headline:
            story_meta_by_headline[first.title]["is_live"] = bool(first.is_live)

    max_display_hours = float(max(max_age_hours, 1))

    def _story_score(story: GroupedStory) -> tuple[float, float]:
        published_ts = _story_ts(story)
        if published_ts <= 0:
            recency_score = 0.0
        else:
            age_hours = max((now_ts - published_ts) / 3600.0, 0.0)
            recency_score = max(0.0, 1.0 - (age_hours / max_display_hours))
        meta = story_meta_by_headline.get(story.headline, {})
        source_count = int(meta.get("sources_count", len(story.sources) or 1))
        diversity = min(source_count / max(float(confirmed_min_sources), 1.0), 1.0)
        source_bonus = diversity * source_diversity_bonus_cap
        story_live_penalty = live_penalty if bool(meta.get("is_live", False)) else 0.0
        score = recency_score + source_bonus - story_live_penalty
        return score, published_ts

    stories.sort(key=_story_score, reverse=True)
    return stories
