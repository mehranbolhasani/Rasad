"""
ترجمه مقالات انگلیسی به فارسی.
مقالاتی که از فیدهای فارسی آمده‌اند نیاز به ترجمه ندارند.
حالت‌ها: ai (OpenAI GPT-4o-mini)، free (deep-translator)، none (بدون ترجمه).
"""
import logging
import os
import re

from rasad.models import Article

logger = logging.getLogger(__name__)


def _translate_openai(text: str) -> str | None:
    """Translate text from English to Farsi using OpenAI GPT-4o-mini."""
    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed; pip install openai")
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set")
        return None

    client = openai.OpenAI()
    try:
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional English-to-Persian (Farsi) news translator. "
                        "Translate the following text to fluent, formal Persian. "
                        "Output ONLY the Persian translation, nothing else."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=400,
        )
        if r.choices and r.choices[0].message.content:
            return r.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("OpenAI translation error: %s", e)
    return None


def _extract_tagged_fields(text: str) -> tuple[str | None, str | None]:
    """
    Parse model output expected in:
      TITLE: ...
      SUMMARY: ...
    """
    if not text:
        return None, None
    title_match = re.search(r"(?im)^title\s*:\s*(.+)$", text)
    summary_match = re.search(r"(?im)^summary\s*:\s*(.+)$", text, re.S)
    title = title_match.group(1).strip() if title_match else None
    summary = summary_match.group(1).strip() if summary_match else None
    return title, summary


def _translate_article_openai(title: str, summary: str) -> tuple[str | None, str | None]:
    """
    Translate title + summary together for more natural, coherent Persian output.
    Returns (fa_title, fa_summary).
    """
    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed; pip install openai")
        return None, None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set")
        return None, None

    client = openai.OpenAI()
    prompt = (
        "You are a senior Persian news editor.\n"
        "Translate English news into NATURAL, fluent Persian (Farsi) used by native journalists.\n"
        "Avoid literal/word-by-word translation.\n"
        "Keep facts exact, no additions, no omissions.\n"
        "Keep neutral tone.\n"
        "Output EXACTLY two lines:\n"
        "TITLE: <translated title>\n"
        "SUMMARY: <translated summary>\n"
        "Rules:\n"
        "- Prefer natural Persian phrasing over direct calque.\n"
        "- Keep names, places, and numbers accurate.\n"
        "- Do not use quotation artifacts or explanation text."
    )
    try:
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"TITLE: {title}\nSUMMARY: {summary}",
                },
            ],
            max_tokens=550,
        )
        if r.choices and r.choices[0].message.content:
            content = r.choices[0].message.content.strip()
            fa_title, fa_summary = _extract_tagged_fields(content)
            if fa_title and fa_summary:
                return fa_title, fa_summary
            # fallback: if parsing fails, return whole text as summary
            return None, content
    except Exception as e:
        logger.warning("OpenAI article translation error: %s", e)
    return None, None


def _post_edit_persian_openai(title_fa: str, summary_fa: str) -> tuple[str | None, str | None]:
    """
    Light stylistic polish for already-translated Persian text.
    Keeps facts unchanged, only improves native fluency/readability.
    """
    try:
        import openai
    except ImportError:
        return None, None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None

    client = openai.OpenAI()
    prompt = (
        "You are a Persian newsroom copy editor.\n"
        "Polish the Persian headline and summary to sound natural and native.\n"
        "STRICT RULES:\n"
        "- Do not change facts, entities, numbers, or claims.\n"
        "- Do not add or remove information.\n"
        "- Keep neutral news tone.\n"
        "- Only improve wording, flow, and idiomatic Persian.\n"
        "Output EXACTLY two lines:\n"
        "TITLE: <edited title>\n"
        "SUMMARY: <edited summary>"
    )
    try:
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.15,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"TITLE: {title_fa}\nSUMMARY: {summary_fa}",
                },
            ],
            max_tokens=550,
        )
        if r.choices and r.choices[0].message.content:
            content = r.choices[0].message.content.strip()
            ed_title, ed_summary = _extract_tagged_fields(content)
            return ed_title, ed_summary
    except Exception as e:
        logger.warning("OpenAI post-edit error: %s", e)
    return None, None


def _translate_free(text: str) -> str | None:
    """Translate text using deep-translator (free Google Translate, no API key)."""
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="en", target="fa").translate(text)
    except Exception as e:
        logger.warning("deep_translator error: %s", e)
    return None


def translate_text(text: str, mode: str = "ai") -> str | None:
    """
    Translate a piece of English text to Farsi.
    Tries the requested mode first, falls back to the other.
    """
    if not text or not text.strip():
        return None

    if mode == "ai":
        result = _translate_openai(text)
        if result:
            return result
        result = _translate_free(text)
        if result:
            return result
    elif mode == "free":
        result = _translate_free(text)
        if result:
            return result
        result = _translate_openai(text)
        if result:
            return result

    return None


def translate_articles(
    articles: list[Article],
    feeds_config: list[dict],
    mode: str = "ai",
    post_edit_enabled: bool = False,
    post_edit_limit: int = 15,
) -> list[Article]:
    """
    Translate English-source articles to Farsi (title + summary).
    Articles from Farsi feeds pass through unchanged.
    feeds_config is used to look up language by source name.
    """
    if mode == "none":
        return list(articles)

    feed_lang = {}
    for fc in feeds_config:
        feed_lang[fc.get("name", "")] = fc.get("language", "en")

    result = []
    translated_count = 0
    post_edited_count = 0
    for art in articles:
        lang = feed_lang.get(art.source, "en")
        if lang == "fa":
            result.append(art)
            continue

        if mode == "ai":
            fa_title, fa_summary = _translate_article_openai(art.title, art.summary)
            if not fa_title:
                # fallback to old per-field translation path
                fa_title = translate_text(art.title, mode)
                fa_summary = (
                    translate_text(art.summary, mode)
                    if art.summary != art.title
                    else fa_title
                )
        else:
            fa_title = translate_text(art.title, mode)
            fa_summary = (
                translate_text(art.summary, mode)
                if art.summary != art.title
                else fa_title
            )

        if fa_title:
            if (
                mode == "ai"
                and post_edit_enabled
                and post_edited_count < max(0, post_edit_limit)
            ):
                ed_title, ed_summary = _post_edit_persian_openai(
                    fa_title,
                    fa_summary or art.summary,
                )
                if ed_title and ed_summary:
                    fa_title, fa_summary = ed_title, ed_summary
                    post_edited_count += 1

            translated_count += 1
            result.append(
                Article(
                    title=fa_title,
                    summary=fa_summary or art.summary,
                    link=art.link,
                    source=art.source,
                    published=art.published,
                    raw_text=art.raw_text,
                )
            )
        else:
            logger.warning("Translation failed for: %s", art.title[:60])
            result.append(art)

    logger.info("Translated %d English articles to Farsi", translated_count)
    if post_edit_enabled and mode == "ai":
        logger.info("Post-edited %d translated articles", post_edited_count)
    return result
