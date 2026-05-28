#!/usr/bin/env bash
set -e
cd /home/rasad/Rasad
# Pull latest code before building. Safe if working tree is clean.
git pull --ff-only origin main
source .venv/bin/activate
python bridge_build.py --config config.yaml --with-build
