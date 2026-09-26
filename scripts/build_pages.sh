#!/usr/bin/env bash
# Build demo/senator-check.html and demo/methodology.html from the saved Pillars 4-6
# results, the methodology registry, the reference anchors and the official
# committee names. Nothing is recalculated. Pass --check to compare instead of writing.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x ./.venv/bin/python ] && PY=./.venv/bin/python
PYTHONPATH=src exec $PY -m civicalign.build_pages "$@"
