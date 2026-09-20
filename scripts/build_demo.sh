#!/usr/bin/env bash
# Rebuild demo/senator-check.html from the current pipeline output.
# The demo embeds its data, so it must be regenerated whenever the figures move.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src python3 -m civicalign.build_demo
echo "wrote demo/senator-check.html"
