#!/usr/bin/env python3
"""
Build bridge feeds from non-RSS sources, optionally run full site build.
"""
import argparse
import logging
import subprocess
import sys
from pathlib import Path

from rasad.bridges.runner import run_bridges_from_config_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build bridge RSS feeds for non-RSS sources")
    parser.add_argument("--config", default="config.yaml", help="Config YAML path")
    parser.add_argument("--timeout", type=int, default=10, help="Fetch timeout in seconds")
    parser.add_argument(
        "--with-build",
        action="store_true",
        help="Run build.py after bridge feeds are generated",
    )
    parser.add_argument(
        "--build-args",
        default="",
        help="Extra args passed to build.py when --with-build is enabled",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    generated = run_bridges_from_config_path(config_path=config_path, timeout=args.timeout)
    logger.info("Generated %d bridge RSS file(s)", len(generated))

    if not args.with_build:
        return 0

    build_cmd = [sys.executable, "build.py", "--config", str(config_path)]
    if args.build_args.strip():
        build_cmd.extend(args.build_args.strip().split())
    logger.info("Running full build: %s", " ".join(build_cmd))
    completed = subprocess.run(build_cmd, check=False)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())

