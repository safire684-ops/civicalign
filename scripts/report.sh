#!/usr/bin/env bash
# Print the saved Pillars 4-6 results (nothing is recalculated). No install needed --
# the package is stdlib-only. Pass --json for the saved result record itself.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src exec python3 -m civicalign "$@"
