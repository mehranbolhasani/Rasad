#!/bin/sh
# Deploy Rasad static site (output/) to a remote or gh-pages.
# Usage: ./deploy.sh [target]
# Targets: gh-pages | rsync | (add your own)

set -e
cd "$(dirname "$0")"

# Build first
echo "Building..."
python build.py

OUTPUT_DIR="${OUTPUT_DIR:-output}"

case "${1:-}" in
  gh-pages)
    # Deploy to GitHub Pages: push output/ to gh-pages branch
    if [ -z "$(git status --porcelain "$OUTPUT_DIR")" ] && [ ! -f "$OUTPUT_DIR/index.html" ]; then
      echo "Nothing to deploy or output not built."
      exit 0
    fi
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
      echo "Not a git repo. Clone first."
      exit 1
    fi
    rm -rf .deploy_ghp
    cp -r "$OUTPUT_DIR" .deploy_ghp
    git checkout gh-pages 2>/dev/null || git checkout --orphan gh-pages
    rm -rf *
    mv .deploy_ghp/* .
    rmdir .deploy_ghp
    git add .
    git commit -m "Deploy Rasad $(date -u +%Y-%m-%d)" || true
    git push origin gh-pages
    git checkout -
    echo "Deployed to gh-pages."
    ;;
  rsync)
    # Deploy via rsync. Set RSYNC_DEST e.g. user@host:/var/www/rasad/
    if [ -z "$RSYNC_DEST" ]; then
      echo "Set RSYNC_DEST (e.g. user@host:/var/www/rasad/)"
      exit 1
    fi
    rsync -av --delete "$OUTPUT_DIR/" "$RSYNC_DEST"
    echo "Deployed to $RSYNC_DEST"
    ;;
  *)
    echo "Usage: $0 gh-pages | rsync"
    echo "  gh-pages: push output/ to branch gh-pages"
    echo "  rsync:   rsync output/ to RSYNC_DEST"
    exit 1
    ;;
esac
