# AGENTS.md — Rasad

Compact operating manual for agents. If a fact is obvious from filenames, it is omitted.

## Mission (non-negotiable)

Rasad is an ultra-lightweight crisis-news aggregation pipeline that builds a **static Persian (Farsi, RTL)** website for low-bandwidth users.

- Static output only (`output/` is deployed as-is).
- No heavy JS, no tracking, no cookies.
- Persian-first UX (`lang=fa`, `dir=rtl`).
- Neutral, factual, concise newsroom tone.
- Graceful failure over complexity.

## Architecture

Main pipeline entrypoint: `build.py`

Stages: `fetcher.py` → `filter.py` → `summarizer.py` → `translator.py` → `grouper.py` → `generator.py` + `feed_output.py`

Bridge pipeline entrypoint: `bridge_build.py`

- Generates synthetic RSS from non-RSS sources (`rasad/bridges/*`: HTML/JSON adapters).
- Optionally runs full `build.py` afterwards (`--with-build`).

Core models: `rasad/models.py` (`Article`, `SourceRef`, `GroupedStory`).

## Repository Map

- `build.py` — full build CLI
- `bridge_build.py` — bridge feed generation CLI
- `config.yaml` — central behavior and source config
- `rasad/` — pipeline package
- `rasad/bridges/` — non-RSS adapters (`html_adapter.py`, `json_adapter.py`, `runner.py`, `rss_writer.py`)
- `templates/` — Jinja2 templates (Farsi, RTL; `base.html`, `index.html`, `archive_*.html`)
- `static/style.css` — minimal stylesheet copied to output
- `deploy.sh` — deploy helper (`gh-pages` or `rsync`)
- `deploy_server.sh` — hardened server-side deploy flow (pulls, builds, rsyncs, verifies marker)
- `run_build.sh` — minimal server cron build script
- `crontab.example` — cron template
- `bridges/*.xml` — generated bridge RSS artifacts
- `output/` — generated static site artifact (deploy this)
- `.rasad_cache.json` — conditional GET cache (ETag/Last-Modified); safe to delete

## Runtime and Dependencies

- Python 3.10+ (uses `str | Path` typing).
- Virtualenv expected at `.venv` (server scripts assume it).
- No test runner, no linter, no typechecker, no formatter config exists in the repo.
- Primary deps: `feedparser`, `requests`, `python-dateutil`, `PyYAML`, `Jinja2`, `python-dotenv`, `beautifulsoup4`, `lxml`, `openai`.
- Optional: `deep-translator` (free translation fallback).

## Developer Commands

Local setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Build commands:

```bash
python build.py
python build.py --dry-run
python build.py --filter-debug        # writes output/filter_debug.json
python build.py --config config.yaml --output output
```

Bridge commands:

```bash
python bridge_build.py --config config.yaml
python bridge_build.py --config config.yaml --with-build   # production pattern
```

Deploy commands:

```bash
./deploy.sh gh-pages
RSYNC_DEST=user@host:/var/www/rasad/ ./deploy.sh rsync
./deploy_server.sh
```

## Config Contract (`config.yaml`)

Top-level keys agents touch most:

- `site`: title, description, base_url
- `feeds`: RSS sources (`name`, `url`, `language` — `fa` or `en`)
- `bridge_feeds`: non-RSS sources (`type: html` with CSS selectors, or `type: json` with `json_map`)
- `keywords` / `filtering`: `required_keywords`, `min_matches`
- `summarization`: `mode` (`extractive` | `ai`), `max_sentences`
- `translation`: `mode` (`ai` | `free` | `none`), `post_edit`, `post_edit_limit`
- `fetch`: `timeout_seconds`, `cache_file`, `max_articles_per_feed`
- `grouper`: `similarity_threshold`, `confirmed_min_sources`, `secondary_title_threshold`, `secondary_time_window_hours`
- `output`: `dir`, `latest_count`, `archive_pages`

Rules:

1. Preserve backward-compatible defaults.
2. Add new config keys with safe defaults in code.
3. Never hard-fail if optional config sections are missing.
4. Keep config comments readable for Persian-speaking operators.

## Translation and Summarization Quirks

Translation (`rasad/translator.py`):

- Mode ordering and fallback matter: `ai` falls back to `free`; `free` falls back to `ai`.
- `OPENAI_API_KEY` env var required for AI mode. `OPENAI_MODEL` env var overrides default `gpt-4o-mini`.
- Post-edit is optional and cost-bounded (`post_edit_limit`).
- Farsi-feed articles pass through unchanged.

Summarization (`rasad/summarizer.py`):

- Default mode is `extractive` (first N sentences).
- `ai` mode tries OpenAI first, then Ollama if `OLLAMA_HOST` is set. Falls back to extractive on any failure.
- Avoid speculative phrasing.

## Grouping and Credibility Semantics

`grouper.py` drives the "confirmed / reported" labels:

- `confirmed` = `unique_source_count >= confirmed_min_sources`. This is not external fact-checking.
- Uses Jaccard token overlap on normalized Persian/English text, with a secondary pass for title-only similarity within a time window.
- When changing thresholds, compare cluster counts and source diversity before/after to avoid over-merging or fragmentation.

## Agent Change Workflow (Mandatory)

For any non-trivial change:

1. Read impacted modules and `config.yaml`.
2. Implement smallest coherent change.
3. Run relevant build command(s).
4. Validate generated outputs exist:
   - `output/index.html`
   - `output/feed.xml`
   - `output/api/latest.json`
5. If filtering/grouping changed, run `--filter-debug` and inspect `output/filter_debug.json`.
6. Summarize user-visible impact and operational risks.

Never claim success without running at least one relevant command.

## Safety Rules

1. Do not run destructive git commands (`reset --hard`, force push) unless explicitly requested.
2. Do not remove unrelated local changes made by humans.
3. Keep secrets out of repo (`OPENAI_API_KEY` must remain env-only).
4. Do not weaken nginx/TLS/security defaults without explicit operator approval.
5. Prefer additive, reversible migrations over destructive rewrites.

## Anti-Patterns (Do Not Introduce)

1. Heavy frontend frameworks or client-side hydration.
2. Tracking scripts, fingerprinting, or ad tech.
3. Silent exception swallowing that hides operational failures.
4. Breaking config compatibility without migration notes.
5. Hardcoding environment-specific absolute paths in core Python code.

## Definition of Done

A change is done only when:

1. Code is consistent with mission constraints.
2. Relevant build/verification commands were run successfully.
3. Output artifacts are correct.
4. Any config/behavior changes are documented in README or inline comments.
5. Risky operational changes include rollback guidance.

---

When uncertain, prioritize reliability, minimalism, Persian readability, and operator safety.
