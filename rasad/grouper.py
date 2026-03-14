"""
Group articles that refer to the same event using token overlap (Jaccard similarity).
Each group becomes one GroupedStory with merged headline, combined summary, and source list.
"""
import re
from datetime import datetime

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
        return article.published.timestamp()
    except (AttributeError, OSError):
        return None


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
) -> list[GroupedStory]:
    """
    Cluster articles by similarity. Each cluster becomes one GroupedStory.
    Headline from first (or highest-ranked) article; summary combined from first;
    sources list all; confirmed = True if group has at least confirmed_min_sources.
    """
    if not articles:
        return []

    # Build adjacency: for each article, which others are similar enough
    n = len(articles)
    similar: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        similar[i].add(i)
        for j in range(i + 1, n):
            sim = similarity(articles[i], articles[j])
            if sim >= similarity_threshold:
                similar[i].add(j)
                similar[j].add(i)
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
                return a.published.timestamp()
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
        published = first.published
        for a in group[1:]:
            if a.published and (published is None or a.published < published):
                published = a.published
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

    # Sort stories by published date descending
    def _story_sort_key(s: GroupedStory) -> float:
        if s.published is None:
            return 0.0
        try:
            return s.published.timestamp()
        except (AttributeError, OSError):
            return 0.0
    stories.sort(key=_story_sort_key, reverse=True)
    return stories
