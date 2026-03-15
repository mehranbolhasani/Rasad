# SERVER_HANDOFF_PROD.md - Production Handoff (Pre-Filled)

This is the pre-filled production runbook for Rasad operations.
Source values were derived from current repository configuration and scripts.

## 1) Production Identity (Current)

- Git remote: `https://github.com/mehranbolhasani/Rasad.git`
- Branch: `main`
- Site base URL (current config): `https://rasad.example.com`
- Nginx `server_name` (current sample config): `rasad.example.com`
- Nginx root: `/var/www/rasad/output`
- Repo dir: `/home/rasad/Rasad`
- Virtualenv: `/home/rasad/Rasad/.venv`
- Config path: `/home/rasad/Rasad/config.yaml`

Note: domain/certificate paths currently match sample values in repo config. If your live domain differs, update `config.yaml` and nginx config before go-live.

## 2) One-Time Bootstrap (Exact Commands)

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip rsync curl nginx
sudo mkdir -p /home/rasad
sudo chown -R "$USER":"$USER" /home/rasad
cd /home/rasad
git clone https://github.com/mehranbolhasani/Rasad.git Rasad
cd /home/rasad/Rasad
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Configure secret:

```bash
cat >> /home/rasad/Rasad/.env <<'EOF'
OPENAI_API_KEY=sk-REPLACE_ME
EOF
chmod 600 /home/rasad/Rasad/.env
```

## 3) Primary Deploy Path (Recommended)

Use the hardened deploy script already included in repo:

```bash
cd /home/rasad/Rasad
chmod +x deploy_server.sh
./deploy_server.sh
```

What it does:

1. Fetches + fast-forward pulls `origin/main`
2. Activates `.venv`
3. Runs `python bridge_build.py --config config.yaml --with-build`
4. Verifies `output/index.html`
5. Rsyncs `output/` to `/var/www/rasad/output`
6. Verifies marker `<div class="page">` in built + served HTML

## 4) Production Deploy Variants

Deploy + nginx reload + live URL validation:

```bash
cd /home/rasad/Rasad
RELOAD_NGINX=1 LIVE_URL="https://rasad.example.com" ./deploy_server.sh
```

Deploy to a different serve dir:

```bash
cd /home/rasad/Rasad
SERVE_DIR="/var/www/rasad/output" ./deploy_server.sh
```

## 5) Cron (Production Schedule)

Recommended schedule: every 15 minutes

```bash
*/15 * * * * cd /home/rasad/Rasad && /home/rasad/Rasad/.venv/bin/python bridge_build.py --config config.yaml --with-build >> /var/log/rasad.log 2>&1
```

Install:

```bash
crontab -e
```

Verify logs:

```bash
tail -f /var/log/rasad.log
```

## 6) Nginx Values (Current Repo Defaults)

Current values from `nginx-cloudflare-static.conf`:

- `server_name rasad.example.com;`
- `root /var/www/rasad/output;`
- `ssl_certificate /etc/ssl/certs/cloudflare-origin.pem;`
- `ssl_certificate_key /etc/ssl/private/cloudflare-origin.key;`

Validation/reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 7) Agent Operation Sequence (Strict)

Any agent on server should run this sequence exactly:

```bash
cd /home/rasad/Rasad
git fetch origin main
git pull --ff-only origin main
source .venv/bin/activate
python bridge_build.py --config config.yaml --with-build
test -f output/index.html
test -f output/feed.xml
test -f output/api/latest.json
./deploy_server.sh
```

## 8) Fast Health Check Commands

Local artifacts:

```bash
ls -lah /home/rasad/Rasad/output/index.html /home/rasad/Rasad/output/feed.xml /home/rasad/Rasad/output/api/latest.json
```

Served artifacts:

```bash
ls -lah /var/www/rasad/output/index.html /var/www/rasad/output/feed.xml /var/www/rasad/output/api/latest.json
```

Live site probe:

```bash
curl -fsSL https://rasad.example.com | rg "<div class=\"page\">"
```

## 9) Rollback Procedure (Known-Good Commit)

```bash
cd /home/rasad/Rasad
git checkout <KNOWN_GOOD_COMMIT_SHA>
source .venv/bin/activate
python bridge_build.py --config config.yaml --with-build
./deploy_server.sh
```

Return to tracked branch:

```bash
git checkout main
git pull --ff-only origin main
```

## 10) Final Go-Live Checklist

- [ ] `OPENAI_API_KEY` set in `/home/rasad/Rasad/.env`
- [ ] `config.yaml` `site.base_url` matches live domain
- [ ] nginx `server_name` matches live domain
- [ ] TLS cert/key paths exist on server
- [ ] `/var/www/rasad/output` writable by deploy user
- [ ] `./deploy_server.sh` passes with `LIVE_URL`

