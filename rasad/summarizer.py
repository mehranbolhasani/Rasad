"""
Summarization: extractive (default) or optional AI.
Produces 2–3 short factual sentences, neutral tone.
"""
import logging
import os
import re
from dataclasses import dataclass

from rasad.models import Article

logger = logging.getLogger(__name__)

# Sentence boundary: . ! ? followed by space or end
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
SPECULATION_MARKERS = ("reportedly", "allegedly", "according to reports", "unconfirmed")


def _sentences(text: str) -> list[str]:
    """Split text into sentences (simple)."""
    if not text or not text.strip():
        return []
    parts = SENTENCE_RE.split(text.strip())
    return [s.strip() for s in parts if s.strip()]


def extractive_summary(article: Article, max_sentences: int = 3) -> str:
    """
    Take first max_sentences from raw_text. Prefer raw_text (already stripped of HTML).
    """
    text = article.raw_text or article.summary or article.title
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    sentences = _sentences(text)
    if not sentences:
        return article.title
    chosen = sentences[:max_sentences]
    return " ".join(chosen)


def summarize_with_ai(article: Article, max_sentences: int = 3) -> str | None:
    """
    Optional: call OpenAI or Ollama for a 2–3 sentence factual summary.
    Returns None on failure (caller should fall back to extractive).
    """
    try:
        if os.environ.get("OPENAI_API_KEY"):
            return _summarize_openai(article, max_sentences)
        if os.environ.get("OLLAMA_HOST"):
            return _summarize_ollama(article, max_sentences)
    except Exception as e:
        logger.warning("AI summarization failed: %s", e)
    return None


def _summarize_openai(article: Article, max_sentences: int) -> str | None:
    try:
        import openai
    except ImportError:
        return None
    client = openai.OpenAI()
    text = (article.raw_text or article.summary or article.title)[:4000]
    prompt = (
        "Summarize the following news in 2–3 short factual sentences. "
        "Neutral tone only. No opinions or speculation. Confirmed information only."
    )
    try:
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Headline: {article.title}\n\nText: {text}"},
            ],
            max_tokens=150,
        )
        if r.choices and r.choices[0].message.content:
            return r.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("OpenAI summarization error: %s", e)
    return None


def _summarize_ollama(article: Article, max_sentences: int) -> str | None:
    try:
        import requests
    except ImportError:
        return None
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    text = (article.raw_text or article.summary or article.title)[:4000]
    prompt = (
        "Summarize the following news in 2–3 short factual sentences. "
        "Neutral tone only. No opinions or speculation. Confirmed information only.\n\n"
        f"Headline: {article.title}\n\nText: {text}"
    )
    try:
        r = requests.post(
            f"{host.rstrip('/')}/api/generate",
            json={"model": os.environ.get("OLLAMA_MODEL", "llama2"), "prompt": prompt, "stream": False},
            timeout=60,
        )
        if r.status_code == 200 and r.json().get("response"):
            return r.json()["response"].strip()
    except Exception as e:
        logger.warning("Ollama summarization error: %s", e)
    return None


def summarize_article(
    article: Article,
    mode: str = "extractive",
    max_sentences: int = 3,
) -> str:
    """
    Return 2–3 sentence summary. Uses AI if mode is 'ai' and API available; else extractive.
    """
    if mode == "ai":
        ai_summary = summarize_with_ai(article, max_sentences)
        if ai_summary:
            return ai_summary
    return extractive_summary(article, max_sentences)


def summarize_articles(
    articles: list[Article],
    mode: str = "extractive",
    max_sentences: int = 3,
) -> list[Article]:
    """
    Return new articles with summary replaced by the summarized text (and raw_text unchanged for grouping).
    We store the short summary in the article's summary field for downstream use.
    """
    result = []
    for art in articles:
        new_summary = summarize_article(art, mode=mode, max_sentences=max_sentences)
        result.append(
            Article(
                title=art.title,
                summary=new_summary,
                link=art.link,
                source=art.source,
                published=art.published,
                raw_text=art.raw_text,
            )
        )
    return result
