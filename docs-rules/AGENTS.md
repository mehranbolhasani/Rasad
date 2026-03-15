# AGENTS.md - Rasad Project Operating Manual

This document is the authoritative guide for any coding agent working on this repository.
Follow it strictly to avoid regressions, operational mistakes, or mission drift.

## 1) Project Mission and Constraints

Rasad is an ultra-lightweight crisis-news aggregation pipeline that builds a static Persian (Farsi, RTL) website for low-bandwidth users.

Non-negotiable product constraints:

1. Static output only (deploy `output/` as-is).
2. Fast and minimal pages (no heavy JS, no tracking, no cookies).
3. Persian-first UX (`lang=fa`, `dir=rtl`).
4. Neutral, factual, concise newsroom tone.
5. Reliability over complexity: graceful failure, fallback behavior, clear logs.

If a change improves features but violates these constraints, reject the change.

## 2) High-Level Architecture

Main pipeline entrypoint: `build.py`

Pipeline stages:

1. Fetch feeds (`rasad/fetcher.py`)
2. Filter by keywords (`rasad/filter.py`)
3. Summarize (`rasad/summarizer.py`)
4. Translate EN to FA when enabled (`rasad/translator.py`)
5. Group similar items into stories (`rasad/grouper.py`)
6. Render static HTML (`rasad/generator.py`)
7. Emit RSS + JSON API (`rasad/feed_output.py`)

Bridge pipeline entrypoint: `bridge_build.py`

- Generates synthetic RSS from non-RSS sources (`rasad/bridges/*`)
- Optionally runs full `build.py` afterwards

Core data models are in `rasad/models.py`:

- `Article`
- `SourceRef`
- `GroupedStory`

## 3) Repository Map (Practical)

- `build.py`: full build CLI
- `bridge_build.py`: bridge feed generation CLI
- `config.yaml`: central behavior and source config
- `rasad/`: pipeline package
- `rasad/bridges/`: non-RSS adapters (HTML, JSON)
- `templates/`: Jinja templates for static pages
- `static/style.css`: minimal stylesheet copied to output
- `deploy.sh`: simple deploy helper (gh-pages or rsync)
- `deploy_server.sh`: hardened server-side deploy flow
- `run_build.sh`: minimal server build script
- `bridges/*.xml`: generated or committed bridge RSS artifacts
- `output/`: generated static site artifact (deploy this)

## 4) Runtime and Dependencies

Environment:

- Python 3.10+ preferred (uses modern typing syntax like `str | Path`)
- Virtualenv expected at `.venv` in server scripts

Primary deps (`requirements.txt`):

- `feedparser`, `requests`, `python-dateutil`
- `PyYAML`, `Jinja2`, `python-dotenv`
- `beautifulsoup4`, `lxml`
- `openai` (AI translation/summarization path)

Optional:

- `deep-translator` (free translation fallback)

## 5) Configuration Contract (`config.yaml`)

Top-level keys commonly used by code:

- `site`: title, description, base_url
- `feeds`: RSS sources (`name`, `url`, `language`)
- `bridge_feeds`: non-RSS source conversion settings
- `keywords`: matching list for filtering
- `filtering`: `required_keywords`, `min_matches`
- `summarization`: `mode`, `max_sentences`
- `translation`: `mode`, `post_edit`, `post_edit_limit`
- `fetch`: timeout/cache/max per feed
- `grouper`: thresholds and confirmation controls
- `output`: output directory and archive behavior

Rules:

1. Preserve backward-compatible defaults whenever possible.
2. Add new config keys with safe defaults in code.
3. Never hard-fail if optional config sections are missing.
4. Keep config comments readable for Persian-speaking operators.

## 6) Build, Debug, and Operations Commands

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
python build.py --filter-debug
python build.py --config config.yaml --output output
```

Bridge commands:

```bash
python bridge_build.py --config config.yaml
python bridge_build.py --config config.yaml --with-build
```

Deploy commands:

```bash
./deploy.sh gh-pages
RSYNC_DEST=user@host:/var/www/rasad/ ./deploy.sh rsync
./deploy_server.sh
```

Cron pattern:

- See `crontab.example` and use `bridge_build.py --with-build` for non-RSS-inclusive production runs.

## 7) Coding Standards for This Repository

General:

1. Prefer clear, boring code over clever code.
2. Keep functions focused and composable.
3. Maintain graceful degradation on network/API failure.
4. Log warnings for recoverable failures; avoid crashes in per-feed/per-source loops.
5. Keep all user-facing output neutral and factual.

Python style:

- Use type hints consistently (current codebase style).
- Use dataclasses for shared payload structures.
- Avoid introducing heavy frameworks or asynchronous complexity unless required.
- Keep imports minimal and localize optional imports when dependency may be absent (current pattern in translator/summarizer).

I/O and networking:

- Always set timeouts for HTTP.
- Use defensive parsing with fallback values.
- Continue processing other items/sources when one source fails.

Templates/UI:

- Maintain RTL correctness and Persian-first layout.
- Keep markup and CSS minimal.
- Do not add analytics scripts or third-party trackers.

## 8) Translation and Summarization Guardrails

Translation (`rasad/translator.py`):

- Respect mode ordering and fallback behavior (`ai`, `free`, `none`).
- Do not silently force AI-only behavior when API key is absent.
- Preserve factual accuracy and named entities.
- Keep post-edit optional and cost-bounded (`post_edit_limit`).

Summarization (`rasad/summarizer.py`):

- Preserve concise, factual summaries.
- If AI summarization fails, fallback to extractive behavior.
- Avoid speculative phrasing and editorial tone.

## 9) Grouping and Credibility Semantics

Grouping (`rasad/grouper.py`) drives "confirmed/reporting" UX:

- `confirmed` is derived from number of unique sources (`confirmed_min_sources`), not an external fact-check.
- Similarity thresholds control clustering behavior and can change site perception.

When changing grouping logic:

1. Explain expected precision/recall trade-off.
2. Run before/after comparison on sample outputs.
3. Confirm no major collapse into over-merged or fragmented stories.

## 10) Agent Change Workflow (Mandatory)

For any non-trivial change, do this sequence:

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

## 11) Safety Rules (Server + Git)

1. Do not run destructive git commands (`reset --hard`, force push) unless explicitly requested.
2. Do not remove unrelated local changes made by humans.
3. Keep secrets out of repo (`OPENAI_API_KEY` must remain env-only).
4. Do not weaken nginx/TLS/security defaults without explicit operator approval.
5. Prefer additive, reversible migrations over destructive rewrites.

## 12) Testing and Verification Checklist

Minimum checks after pipeline edits:

1. `python build.py` exits cleanly.
2. `output/index.html` renders and contains stories or empty-state behavior.
3. `output/feed.xml` is generated and syntactically valid.
4. `output/api/latest.json` is generated and valid JSON.

Additional checks after bridge edits:

1. `python bridge_build.py --config config.yaml` succeeds.
2. Expected `bridges/*.xml` files are produced.
3. Bridge-generated feeds are consumable by `build.py`.

Additional checks after template/style edits:

1. Verify RTL layout and readability.
2. Confirm no added heavy assets/scripts.

## 13) Common Task Playbooks

Add a new RSS source:

1. Add source in `config.yaml` under `feeds` with correct `language`.
2. Run `python build.py`.
3. Check filtered inclusion and story grouping.

Add a new non-RSS source:

1. Add source in `config.yaml` under `bridge_feeds.sources`.
2. Use `type: html` with selectors or `type: json` with `json_map`.
3. Run `python bridge_build.py --config config.yaml --with-build`.
4. Validate generated bridge XML and resulting site stories.

Tune filtering:

1. Adjust `keywords`, `required_keywords`, `min_matches`.
2. Run `python build.py --filter-debug`.
3. Inspect false positives/negatives before finalizing.

Tune grouping:

1. Adjust `grouper` thresholds conservatively.
2. Compare cluster counts and source diversity before/after.
3. Confirm top headlines remain coherent.

## 14) Anti-Patterns (Do Not Introduce)

1. Heavy frontend frameworks or client-side hydration.
2. Tracking scripts, fingerprinting, or ad tech.
3. Silent exception swallowing that hides operational failures.
4. Breaking config compatibility without migration notes.
5. Hardcoding environment-specific absolute paths in core Python code.

## 15) Definition of Done

A change is done only when:

1. Code is consistent with mission constraints.
2. Relevant build/verification commands were run successfully.
3. Output artifacts are correct.
4. Any config/behavior changes are documented in README or inline comments.
5. Risky operational changes include rollback guidance.

---

When uncertain, prioritize reliability, minimalism, Persian readability, and operator safety.
