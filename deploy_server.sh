#!/usr/bin/env bash
set -Eeuo pipefail

# One-command deploy for Rasad on server.
# It pulls latest code, builds static output, syncs to web root, and verifies HTML marker.
#
# Usage:
#   chmod +x deploy_server.sh
#   ./deploy_server.sh
#
# Optional env vars:
#   REPO_DIR=/home/rasad/Rasad
#   SERVE_DIR=/var/www/rasad/output
#   BRANCH=main
#   REMOTE=origin
#   CONFIG_PATH=config.yaml
#   VERIFY_MARKER='<div class="page">'
#   LIVE_URL=https://your-domain.example
#   RELOAD_NGINX=0   # set to 1 to run: sudo systemctl reload nginx

REPO_DIR="${REPO_DIR:-/home/rasad/Rasad}"
SERVE_DIR="${SERVE_DIR:-/var/www/rasad/output}"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"
CONFIG_PATH="${CONFIG_PATH:-config.yaml}"
VERIFY_MARKER="${VERIFY_MARKER:-<div class=\"page\">}"
LIVE_URL="${LIVE_URL:-}"
RELOAD_NGINX="${RELOAD_NGINX:-0}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_cmd git
require_cmd python
require_cmd rsync

[ -d "$REPO_DIR" ] || fail "Repo directory not found: $REPO_DIR"
cd "$REPO_DIR"

[ -d ".git" ] || fail "Not a git repository: $REPO_DIR"
[ -d ".venv" ] || fail "Virtualenv not found: $REPO_DIR/.venv"
[ -f "bridge_build.py" ] || fail "bridge_build.py not found in $REPO_DIR"
[ -f "$CONFIG_PATH" ] || fail "Config file not found: $REPO_DIR/$CONFIG_PATH"

log "Fetching latest commits"
git fetch "$REMOTE" "$BRANCH"

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "$REMOTE/$BRANCH")"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  log "Already up to date on $REMOTE/$BRANCH"
else
  log "Pulling latest changes from $REMOTE/$BRANCH"
  git pull --ff-only "$REMOTE" "$BRANCH"
fi

log "Activating virtualenv"
# shellcheck disable=SC1091
source .venv/bin/activate

log "Running bridge + site build"
python bridge_build.py --config "$CONFIG_PATH" --with-build

[ -f "output/index.html" ] || fail "Build did not generate output/index.html"

log "Ensuring serve directory exists: $SERVE_DIR"
mkdir -p "$SERVE_DIR"

if [ "$(cd output && pwd -P)" = "$(cd "$SERVE_DIR" && pwd -P)" ]; then
  log "Serve directory is same as build output; skipping rsync"
else
  log "Syncing output/ -> $SERVE_DIR"
  rsync -av --delete "output/" "$SERVE_DIR/"
fi

if [ "$RELOAD_NGINX" = "1" ]; then
  log "Reloading nginx"
  sudo systemctl reload nginx
fi

log "Verifying marker exists in local built HTML"
if grep -qF "$VERIFY_MARKER" "output/index.html"; then
  echo "OK: marker found in output/index.html"
else
  fail "Marker not found in output/index.html: $VERIFY_MARKER"
fi

log "Verifying marker exists in served HTML file"
if grep -qF "$VERIFY_MARKER" "$SERVE_DIR/index.html"; then
  echo "OK: marker found in $SERVE_DIR/index.html"
else
  fail "Marker not found in $SERVE_DIR/index.html: $VERIFY_MARKER"
fi

if [ -n "$LIVE_URL" ]; then
  require_cmd curl
  log "Verifying marker exists in LIVE response: $LIVE_URL"
  if curl -fsSL "$LIVE_URL" | grep -qF "$VERIFY_MARKER"; then
    echo "OK: marker found in live response"
  else
    fail "Marker not found in live response from $LIVE_URL"
  fi
fi

log "Deploy complete"
echo "Commit now deployed: $(git rev-parse --short HEAD)"
