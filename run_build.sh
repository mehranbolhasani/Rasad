#!/usr/bin/env bash
set -e
cd /home/rasad/Rasad
source .venv/bin/activate
python bridge_build.py --config config.yaml --with-build
