#!/usr/bin/env bash
# Print the full report. No install needed -- the package is stdlib-only.
# Pass --json for the stable machine-readable output the front end should consume;
# every finding carries a "publishable" flag, so a consumer that respects it cannot
# display the rejected committee-drift metric by accident.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src exec python3 -m civicalign "$@"
