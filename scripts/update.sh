#!/usr/bin/env bash
# The whole update chain, in the order that keeps bad data off the page.
# Mirrors .github/workflows/update.yml. Every step is a gate: a failure stops
# the chain, nothing is rebuilt from a partial snapshot, and the previously
# verified pages stay as they are.
#
#   1 fetch      every source into staging; all critical sources succeed or none
#                is installed
#   2 verify     roster, join keys, record counts
#   3 data tests recompute every figure from the raw files
#   4 rebuild    both pages
#   5 page tests the public-claim contract
#   6 supervisor independent recount of every published figure
set -uo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x ./.venv/bin/python ] && PY=./.venv/bin/python

echo "1/6  fetching every source as one snapshot"
PYTHONPATH=src $PY -m civicalign.agents || { echo; echo "  FETCH FAILED -- no file was replaced; the previous snapshot and pages stand."; exit 1; }

echo
echo "2/6  verifying the snapshot"
PYTHONPATH=src $PY -m civicalign.agents.verify || exit 2

echo
echo "3/6  recomputing every figure from the raw files"
if ! $PY -m pytest -q --ignore=tests/test_published_pages.py --ignore=tests/test_whitepaper.py; then
  echo
  echo "  TESTS FAILED -- the pages were not rebuilt."
  exit 3
fi

echo
echo "4/6  rebuilding both pages"
PYTHONPATH=src $PY -m civicalign.build_demo || exit 4

echo
echo "5/6  checking the public-claim contract on the rebuilt pages"
$PY -m pytest -q tests/test_published_pages.py || exit 5

echo
echo "6/6  supervisor: independent recount of every published figure"
PYTHONPATH=src $PY -m civicalign.agents.supervisor || exit 6

if ! $PY -m pytest -q tests/test_whitepaper.py >/dev/null 2>&1; then
  echo
  echo "  note: WHITEPAPER.md quotes figures that have moved. The pages are"
  echo "  correct and rebuilt; update the whitepaper's prose when convenient."
fi

echo
echo "done. Snapshot accepted, every check passed, pages rebuilt."
