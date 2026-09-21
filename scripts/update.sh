#!/usr/bin/env bash
# Refresh every source, then verify nothing broke.
#
# Safe to run on a schedule: each source is fetched independently and only
# replaces the live file if it passes its own validation, so a bad download or a
# server outage leaves the previous good data in place.
set -uo pipefail
cd "$(dirname "$0")/.."

PYTHONPATH=src python3 -m civicalign.agents
fetch_status=$?

echo
echo "verifying the figures still hold..."
if [ -x ./.venv/bin/python ]; then
  ./.venv/bin/python -m pytest -q || exit 2
else
  python3 -m pytest -q || exit 2
fi

exit $fetch_status
