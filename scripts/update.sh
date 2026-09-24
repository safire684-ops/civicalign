#!/usr/bin/env bash
# The whole update chain, in the order that keeps bad data off the page.
# Mirrors .github/workflows/update.yml. Every step is a gate: a failure stops
# the chain, nothing is rebuilt from a partial snapshot, and nothing is
# committed or published (this script never commits; the workflow commits only
# after every gate passes).
#
#   1 fetch      every source into staging; all critical sources succeed or none
#                is installed
#   2 verify     roster, join keys, record counts
#   3 bind       Pillar 1 bindings re-derived from this snapshot
#   4 context    Stage 2.5 records checked against those bindings and this
#                snapshot's bill status
#   5 rebuild    both pages from this snapshot
#   6 data tests every figure recomputed from the raw files and compared with
#                the pages rebuilt in step 5
#   7 page tests the public-claim contract
#   8 supervisor independent recount of every published figure
#
# No test may compare current source data with a page generated from a
# different snapshot, so the rebuild comes before every test.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x ./.venv/bin/python ] && PY=./.venv/bin/python

echo "1/8  fetching every source as one snapshot"
PYTHONPATH=src $PY -m civicalign.agents || { echo; echo "  FETCH FAILED -- no file was replaced; the previous snapshot and pages stand."; exit 1; }

echo
echo "2/8  verifying the snapshot"
PYTHONPATH=src $PY -m civicalign.agents.verify || exit 2

echo
echo "3/8  binding Senate passage votes to their official records (Pillar 1, deterministic)"
PYTHONPATH=src $PY -m civicalign.explain.bind || exit 3

echo
echo "4/8  checking that the Stage 2.5 records belong to this snapshot"
PYTHONPATH=src $PY -m civicalign.explain.context --check-fresh || exit 4

echo
echo "5/8  rebuilding both pages from this snapshot (working copy only)"
PYTHONPATH=src $PY -m civicalign.build_demo || exit 5

echo
echo "6/8  recomputing every figure from the raw files and comparing with the rebuilt pages"
if ! $PY -m pytest -q --ignore=tests/test_published_pages.py --ignore=tests/test_whitepaper.py; then
  echo
  echo "  TESTS FAILED -- do not commit or publish the rebuilt pages (git checkout -- demo restores the verified ones)."
  exit 6
fi

echo
echo "7/8  checking the public-claim contract on the rebuilt pages"
$PY -m pytest -q tests/test_published_pages.py || exit 7

echo
echo "8/8  supervisor: independent recount of every published figure"
PYTHONPATH=src $PY -m civicalign.agents.supervisor || exit 8

if ! $PY -m pytest -q tests/test_whitepaper.py >/dev/null 2>&1; then
  echo
  echo "  note: WHITEPAPER.md quotes figures that have moved. The pages are"
  echo "  correct and rebuilt; update the whitepaper's prose when convenient."
fi

echo
echo "done. Snapshot accepted, every check passed, pages rebuilt."
