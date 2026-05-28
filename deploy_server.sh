#!/usr/bin/env bash
set -Eeuo pipefail

# One-command deploy for Rasad.
# Pull latest code, build, sync to web root, verify.
#
# Usage: ./deploy_server.sh

REPO_DIR="${REPO_DIR:-/home/rasad/Rasad}"
SERVE_DIR="${SERVE_DIR:-/home/rasad/Rasad/output}"
CONFIG_PATH="${CONFIG_PATH:-config.yaml}"
VERIFY_MARKER="${VERIFY_MARKER:-<div class=\"page\">}"
LIVE_URL="${LIVE_URL:-}"
RELOAD_NGINX="${RELOAD_NGINX:-0}"

cd "$REPO_DIR"

# Pull latest code (fails safely if working tree is dirty)
if git pull --ff-only origin main | grep -q "Already up to date"; then
  echo "Already up to date"
else
  echo "Pulled latest changes"
fi

# Build
source .venv/bin/activate
python build.py --config "$CONFIG_PATH"

# Ensure web root exists
mkdir -p "$SERVE_DIR"

# Sync (skip if same dir)
if [ "$(cd output && pwd -P)" != "$(cd "$SERVE_DIR" && pwd -P)" ]; then
  rsync -av --delete "output/" "$SERVE_DIR/"
fi

# Verify
if ! grep -qF "$VERIFY_MARKER" "$SERVE_DIR/index.html"; then
  echo "ERROR: Build verification failed" >&2
  exit 1
fi

# Optional nginx reload
if [ "$RELOAD_NGINX" = "1" ]; then
  sudo systemctl reload nginx
fi

# Optional live URL check
if [ -n "$LIVE_URL" ]; then
  if curl -fsSL "$LIVE_URL" | grep -qF "$VERIFY_MARKER"; then
    echo "Live OK"
  else
    echo "ERROR: Live verification failed" >&2
    exit 1
  fi
fi

echo "Deploy complete: $(git rev-parse --short HEAD)"
