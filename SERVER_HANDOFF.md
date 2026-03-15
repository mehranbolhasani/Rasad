# SERVER_HANDOFF.md - Main Server Runbook (Rasad)

This document is the production handoff for agents operating Rasad on the main server.
Use it together with `AGENTS.md` (project-wide rules). This file is server-operations focused.

## 1) Server Baseline

Assumed production paths (from deploy scripts):

- Repository: `/home/rasad/Rasad`
- Virtualenv: `/home/rasad/Rasad/.venv`
- Config: `/home/rasad/Rasad/config.yaml`
- Build output: `/home/rasad/Rasad/output`
- Served output: `/var/www/rasad/output`
- Git branch: `main`
- Git remote: `origin`

Primary deploy script:

- `/home/rasad/Rasad/deploy_server.sh`

## 2) One-Time Server Preparation

Install required packages/tools:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip rsync curl nginx
```

Initial repo + env setup:

```bash
cd /home/rasad
git clone <YOUR_RASAD_REPO_URL> Rasad
cd /home/rasad/Rasad
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

OpenAI key for AI translation/summarization (if `translation.mode: ai`):

```bash
echo 'OPENAI_API_KEY=sk-...' >> /home/rasad/Rasad/.env
chmod 600 /home/rasad/Rasad/.env
```

## 3) Daily Operations Commands

Manual full build (bridges + site):

```bash
cd /home/rasad/Rasad
source .venv/bin/activate
python bridge_build.py --config config.yaml --with-build
```

Manual deploy using hardened flow:

```bash
cd /home/rasad/Rasad
chmod +x deploy_server.sh
./deploy_server.sh
```

Quick health check after deploy:

```bash
test -f /var/www/rasad/output/index.html && echo "index OK"
test -f /var/www/rasad/output/feed.xml && echo "rss OK"
test -f /var/www/rasad/output/api/latest.json && echo "api OK"
```

## 4) `deploy_server.sh` Runtime Controls

These env vars can override defaults per deploy:

- `REPO_DIR` (default `/home/rasad/Rasad`)
- `SERVE_DIR` (default `/var/www/rasad/output`)
- `BRANCH` (default `main`)
- `REMOTE` (default `origin`)
- `CONFIG_PATH` (default `config.yaml`)
- `VERIFY_MARKER` (default `<div class="page">`)
- `LIVE_URL` (optional production URL for live HTML verification)
- `RELOAD_NGINX` (`1` to run `sudo systemctl reload nginx`)

Examples:

```bash
RELOAD_NGINX=1 LIVE_URL="https://your-domain.example" ./deploy_server.sh
```

```bash
CONFIG_PATH="config.yaml" SERVE_DIR="/var/www/rasad/output" ./deploy_server.sh
```

## 5) Cron / Automation

Recommended cron (every 15 minutes):

```bash
*/15 * * * * cd /home/rasad/Rasad && /home/rasad/Rasad/.venv/bin/python bridge_build.py --config config.yaml --with-build >> /var/log/rasad.log 2>&1
```

Install cron entry:

```bash
crontab -e
```

Log follow:

```bash
tail -f /var/log/rasad.log
```

## 6) Nginx + Domain Setup

Use the hardened sample:

- `nginx-cloudflare-static.conf`

Before enabling:

1. Set `server_name` to your domain.
2. Set `root` to `/var/www/rasad/output`.
3. Configure Cloudflare Origin cert/key paths.
4. Validate and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 7) Agent-Safe Operating Procedure

Any agent working on server must follow this exact sequence:

1. `cd /home/rasad/Rasad`
2. `git fetch origin main`
3. `git pull --ff-only origin main`
4. `source .venv/bin/activate`
5. `python bridge_build.py --config config.yaml --with-build`
6. Verify `output/index.html`, `output/feed.xml`, `output/api/latest.json`
7. Sync or run `./deploy_server.sh`
8. Optional live check with `LIVE_URL`

Do not skip verification even if build exit code is 0.

## 8) Incident Runbook

If deploy fails:

1. Re-run manually with visible output:
   - `./deploy_server.sh`
2. Check dependency issues:
   - `source .venv/bin/activate && pip install -r requirements.txt`
3. Check API key presence if translation is AI mode:
   - `grep OPENAI_API_KEY /home/rasad/Rasad/.env`
4. Check generated output:
   - `ls -la /home/rasad/Rasad/output`
5. Check web root sync:
   - `ls -la /var/www/rasad/output`
6. Check nginx:
   - `sudo nginx -t`
   - `sudo systemctl status nginx --no-pager`

If a release causes bad content quality, rollback by deploying a known-good git commit:

```bash
cd /home/rasad/Rasad
git checkout <KNOWN_GOOD_COMMIT>
source .venv/bin/activate
python bridge_build.py --config config.yaml --with-build
./deploy_server.sh
```

Then restore tracking branch after incident resolution:

```bash
git checkout main
git pull --ff-only origin main
```

## 9) Security and Reliability Rules

1. Never commit `.env` or secrets.
2. Keep origin behind Cloudflare restrictions where possible.
3. Prefer `git pull --ff-only` on server.
4. Do not run destructive git commands unless explicitly approved.
5. Keep deploy operations idempotent (safe to run repeatedly).

## 10) Final Pre-Handoff Checklist

- [ ] Repo exists at `/home/rasad/Rasad`
- [ ] `.venv` exists and dependencies installed
- [ ] `.env` exists with required secrets
- [ ] `deploy_server.sh` executable
- [ ] `/var/www/rasad/output` writable by deploy user
- [ ] Nginx config validated
- [ ] Cron installed (if desired)
- [ ] Dry run of full deploy completed successfully

