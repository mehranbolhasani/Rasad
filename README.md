# رصد — Rasad

سامانه سبک‌وزن تجمیع اخبار بحران برای افرادی با اینترنت محدود یا ناپایدار. اخبار معتبر درباره بحران ایران-آمریکا/اسرائیل را خلاصه و به صورت صفحات ایستای فارسی با حداقل حجم منتشر می‌کند.

Ultra-lightweight crisis news aggregation for people with limited or unstable internet. Summarizes reliable conflict news into minimal static Farsi pages that load fast on slow connections.

- **Target:** Homepage under 50 KB, no images, no heavy JS, no tracking
- **Stack:** Python, RSS (feedparser), static HTML (Jinja2)
- **Language:** Farsi (Persian) only — RTL layout
- **Deploy:** Static only — Nginx, GitHub Pages, Cloudflare Pages, or any static host

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
fetch RSS → filter by keywords → summarize → translate EN articles to Farsi → group stories → generate static HTML + RSS + text
```

```bash
python build.py                    # full build (bridges + site in one command)
python build.py --dry-run          # print stories, no HTML
python build.py --filter-debug     # write filter decisions to output/filter_debug.json
python build.py --config other.yaml --output ./public
```

## Deployment

### Server (VPS + Nginx) — recommended

The `deploy_server.sh` script handles everything:

```bash
./deploy_server.sh
```

What it does: pull latest code → build → rsync to web root → verify.

For auto-deploy, install the cron:

```bash
crontab -e
# Paste from crontab.example
```

### Static hosts

- **Artifact:** The `output/` directory is the entire site. Deploy it as-is.
- **GitHub Pages:** Push `output/` to a `gh-pages` branch.
- **Cloudflare Pages / Netlify:** Set build command to `python build.py` and publish directory to `output`.

### Nginx (Cloudflare + static origin)

If you deploy on your own Nginx server behind Cloudflare (Full Strict), use the hardened sample config in:

- `nginx-cloudflare-static.conf`

Usage checklist:

1. Replace `server_name` with your domain.
2. Replace `root` with your deployed `output/` path.
3. Set `ssl_certificate` and `ssl_certificate_key` to your Cloudflare Origin Certificate files.
4. Validate and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Notes:

- The config includes strong TLS settings, HSTS, CSP, and common security headers suitable for static sites.
- Keep your origin reachable only through Cloudflare (firewall allowlist Cloudflare IP ranges).
- If your origin is publicly reachable directly, review HSTS/preload before enabling in production.

## Mirroring

The site is fully static. To mirror:

```bash
wget --mirror --convert-links https://your-rasad-site.example.com
```

## Project structure

```
Rasad/
├── rasad/              # Python package
│   ├── fetcher.py      # RSS fetching
│   ├── filter.py       # Keyword filtering
│   ├── summarizer.py
│   ├── grouper.py
│   ├── translator.py   # EN→FA via OpenAI
│   ├── generator.py    # HTML output
│   ├── feed_output.py  # RSS + JSON API
│   ├── text_output.py  # Plain text digests
│   └── bridges/        # Non-RSS adapters
├── templates/          # Jinja2 HTML templates (Farsi, RTL)
├── static/             # Minimal CSS
├── config.yaml         # Feeds, keywords, options
├── build.py            # Single build command
├── deploy_server.sh    # Server deploy script
├── crontab.example     # Cron template
└── requirements.txt
```

## License

MIT. See [LICENSE](LICENSE).
