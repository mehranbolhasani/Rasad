# رصد — Rasad

سامانه سبک‌وزن تجمیع اخبار بحران برای افرادی با اینترنت محدود یا ناپایدار. اخبار معتبر درباره بحران ایران-آمریکا/اسرائیل را خلاصه و به صورت صفحات ایستای فارسی با حداقل حجم منتشر می‌کند.

Ultra-lightweight crisis news aggregation for people with limited or unstable internet. Summarizes reliable conflict news into minimal static Farsi pages that load fast on slow connections.

- **Target:** Homepage under 50 KB, no images, no heavy JS, no tracking
- **Stack:** Python, RSS (feedparser), static HTML (Jinja2)
- **Language:** Farsi (Persian) only — RTL layout
- **Deploy:** Static only — GitHub Pages, Cloudflare Pages, Netlify, or any static host

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# For AI translation of English articles (recommended):
export OPENAI_API_KEY="sk-..."
pip install openai

python build.py
```

Open `output/index.html` in a browser or deploy the `output/` folder.

## How translation works

Rasad uses two types of news sources:

1. **Farsi RSS feeds** (BBC Persian, Radio Farda) — content is already in Farsi, no translation needed
2. **English RSS feeds** (Guardian, Al Jazeera, NetBlocks) — translated to Farsi automatically

Translation modes (set in `config.yaml` under `translation.mode`):

- `ai` — Uses OpenAI GPT-4o-mini (~$2–4/month). Set `OPENAI_API_KEY` env var. Best quality.
- `free` — Uses deep-translator (free, no API key, but unreliable). Install: `pip install deep-translator`
- `none` — No translation; English articles appear as-is.
- `translation.post_edit` — Optional newsroom-style Persian polishing pass after translation.
- `translation.post_edit_limit` — Max number of translated items to polish per run (cost control).

## Configuration

Edit `config.yaml` to:

- Add or remove **RSS feeds** (Farsi or English)
- Change **keywords** used to filter articles
- Set **summarization** mode: `extractive` (default) or `ai`
- Set **translation** mode: `ai`, `free`, or `none`
- Tune smarter grouping in `grouper`:
  - `similarity_threshold`
  - `secondary_title_threshold`
  - `secondary_time_window_hours`

## Build pipeline

```
fetch RSS → filter by keywords → summarize → translate EN articles to Farsi → group stories → generate static HTML
```

```bash
python build.py                    # full build
python build.py --dry-run          # print stories, no HTML
python build.py --filter-debug     # write filter decisions to output/filter_debug.json
python build.py --config other.yaml --output ./public
```

## Deployment

- **Artifact:** The `output/` directory is the entire site. Deploy it as-is.
- **GitHub Pages:** Push `output/` to a `gh-pages` branch.
- **Cloudflare Pages / Netlify:** Set build command to `python build.py` and publish directory to `output`.
- **Deploy script:** `./deploy.sh gh-pages` or `RSYNC_DEST=user@host:/path ./deploy.sh rsync`
- **Cron:** Copy `crontab.example` and adjust the path.

## Mirroring

The site is fully static. To mirror:

```bash
wget --mirror --convert-links https://your-rasad-site.example.com
```

## Project structure

```
Rasad/
├── rasad/           # Python package
│   ├── fetcher.py   # RSS fetching
│   ├── filter.py    # Keyword filtering
│   ├── summarizer.py
│   ├── grouper.py
│   ├── translator.py  # EN→FA via OpenAI or deep-translator
│   ├── generator.py
│   └── feed_output.py
├── templates/       # Jinja2 HTML templates (Farsi, RTL)
├── static/          # Minimal CSS (~500 bytes)
├── config.yaml      # Feeds, keywords, options
├── build.py         # Entry point
├── output/          # Generated site (deploy this)
└── requirements.txt
```

## License

MIT. See [LICENSE](LICENSE).
