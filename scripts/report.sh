#!/usr/bin/env bash
# Print the full report. No install needed -- the package is stdlib-only.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src exec python3 -m civicalign "$@"
