"""
Keyword-based article filtering. Only articles matching at least one keyword are included.
Results are sorted by relevance score then by date.
"""
from dataclasses import dataclass

from rasad.models import Article


@dataclass
class ScoredArticle:
    """Article with a relevance score for sorting."""
    article: Article
    score: int  # number of keyword matches


@dataclass
class FilterDebugEntry:
    """Debug row for one article filtering decision."""
    title: str
    source: str
    link: str
    passed: bool
    total_score: int
    required_score: int
    matched_keywords: list[str]
    matched_required_keywords: list[str]
    reason: str


def _matched_keywords(text: str, keywords: list[str]) -> list[str]:
    """Return distinct keywords that appear in text (case-insensitive)."""
    if not text or not keywords:
        return []
    lower = text.lower()
    matched: list[str] = []
    for kw in keywords:
        if kw and kw.lower() in lower and kw not in matched:
            matched.append(kw)
    return matched


def score_text(text: str, keywords: list[str]) -> int:
    """Return number of distinct keywords found in text (case-insensitive)."""
    if not text or not keywords:
        return 0
    lower = text.lower()
    count = 0
    for kw in keywords:
        if kw and kw.lower() in lower:
            count += 1
    return count


def filter_articles(
    articles: list[Article],
    keywords: list[str],
    required_keywords: list[str] | None = None,
    min_matches: int = 1,
    return_debug: bool = False,
) -> list[Article] | tuple[list[Article], list[FilterDebugEntry]]:
    """
    Keep only articles that satisfy:
    - at least one required keyword match (if required_keywords is provided)
    - at least min_matches across the main keywords list
    Sort by relevance (match count) descending, then by published date descending.
    """
    if not keywords:
        if return_debug:
            debug_rows = [
                FilterDebugEntry(
                    title=a.title,
                    source=a.source,
                    link=a.link,
                    passed=True,
                    total_score=0,
                    required_score=0,
                    matched_keywords=[],
                    matched_required_keywords=[],
                    reason="keywords_list_empty",
                )
                for a in articles
            ]
            return list(articles), debug_rows
        return list(articles)

    required_keywords = required_keywords or []
    scored: list[ScoredArticle] = []
    debug_rows: list[FilterDebugEntry] = []
    for art in articles:
        combined = f"{art.title} {art.raw_text}"
        matched_required = _matched_keywords(combined, required_keywords)
        required_score = len(matched_required)
        # Option 3: at least one core keyword must exist
        if required_keywords and required_score < 1:
            if return_debug:
                debug_rows.append(
                    FilterDebugEntry(
                        title=art.title,
                        source=art.source,
                        link=art.link,
                        passed=False,
                        total_score=0,
                        required_score=required_score,
                        matched_keywords=[],
                        matched_required_keywords=matched_required,
                        reason="missing_required_keyword",
                    )
                )
            continue
        matched_main = _matched_keywords(combined, keywords)
        s = len(matched_main)
        # Option 1: require a minimum total score
        if s >= min_matches:
            scored.append(ScoredArticle(article=art, score=s))
            if return_debug:
                debug_rows.append(
                    FilterDebugEntry(
                        title=art.title,
                        source=art.source,
                        link=art.link,
                        passed=True,
                        total_score=s,
                        required_score=required_score,
                        matched_keywords=matched_main,
                        matched_required_keywords=matched_required,
                        reason="passed",
                    )
                )
        elif return_debug:
            debug_rows.append(
                FilterDebugEntry(
                    title=art.title,
                    source=art.source,
                    link=art.link,
                    passed=False,
                    total_score=s,
                    required_score=required_score,
                    matched_keywords=matched_main,
                    matched_required_keywords=matched_required,
                    reason="below_min_matches",
                )
            )

    # Sort by score desc, then by published desc (newer first; None last)
    def sort_key(sa: ScoredArticle) -> tuple:
        pub = sa.article.published
        return (-sa.score, -(pub.timestamp() if pub else 0))

    scored.sort(key=sort_key)
    filtered = [sa.article for sa in scored]
    if return_debug:
        return filtered, debug_rows
    return filtered
