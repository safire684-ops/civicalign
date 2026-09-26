#!/usr/bin/env bash
# The whole update chain, in the order that keeps bad data off the page.
# Mirrors .github/workflows/update.yml. Every step is a gate: a failure stops
# the chain, nothing is built from a partial snapshot, and nothing is committed
# or published (this script never commits; the workflow commits only after
# every gate passes).
#
#    1 fetch      every source into staging; all critical sources succeed or none
#                 is installed
#    2 verify     roster, join keys, record counts
#   Pillar 1 (Engine A), unchanged:
#      bind       Pillar 1 bindings re-derived from this snapshot
#      context    Stage 2.5 records checked against those bindings and this
#                 snapshot's bill status
#   Pillars 4-6 (Engine B):
#    3 ingest     versioned inputs from the verified snapshot
#    4 bridge     record the active bridge (none-v0, NONE)
#    5 anchors    refresh the three reference figures (visual only; no calculation reads them)
#    6 bills      refresh bill_sponsor_classifications from the verified bill-status archive
#    7 outcomes   refresh senate_bill_outcomes (passed the Senate, enacted) from the same archive
#    8 check      both bill tables valid, consistent and current with the snapshot
#    9 compute    versioned Pillars 4-6 results, only where inputs changed
#   10 build      both published pages from the saved results and the newest verified bill tables
#   11 tests      every test, against the pages just built
#   12 supervisor independent recount of every published number
#
# The bill steps read only the verified snapshot: no API call, no model.
#
# No test may compare current source data with a page built from a different
# snapshot, so the build comes before every test.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x ./.venv/bin/python ] && PY=./.venv/bin/python

echo "1/12 fetching every source as one snapshot"
PYTHONPATH=src $PY -m civicalign.agents || { echo; echo "  FETCH FAILED -- no file was replaced; the previous snapshot and pages stand."; exit 1; }

echo
echo "2/12 verifying the snapshot"
PYTHONPATH=src $PY -m civicalign.agents.verify || exit 2

echo
echo "     Pillar 1: binding Senate passage votes to their official records (deterministic)"
PYTHONPATH=src $PY -m civicalign.explain.bind || exit 3

echo
echo "     Pillar 1: checking that the Stage 2.5 records belong to this snapshot"
PYTHONPATH=src $PY -m civicalign.explain.context --check-fresh || exit 4

echo
echo "3/12 ingesting the versioned Pillars 4-6 inputs"
PYTHONPATH=src $PY -m civicalign.ideology.ingest || exit 5

echo
echo "4/12 recording the active bridge"
PYTHONPATH=src $PY -m civicalign.ideology.bridge || exit 6

echo
echo "5/12 refreshing the three reference anchors (visual only)"
PYTHONPATH=src $PY -m civicalign.ideology.anchors || exit 7

echo
echo "6/12 refreshing the bill/sponsor classifications from the verified bill-status archive"
PYTHONPATH=src $PY -m civicalign.ideology.bills || exit 8

echo
echo "7/12 refreshing the passed-Senate and enacted outcomes"
PYTHONPATH=src $PY -m civicalign.ideology.bill_outcomes || exit 9

echo
echo "8/12 verifying both bill tables"
PYTHONPATH=src $PY -m civicalign.ideology.bill_outcomes --verify || exit 10

echo
echo "9/12 computing the versioned Pillars 4-6 results"
PYTHONPATH=src $PY -m civicalign.ideology.compute || exit 11

echo
echo "10/12 building both published pages from the saved results and bill tables (working copy only)"
PYTHONPATH=src $PY -m civicalign.build_pages || exit 12

echo
echo "11/12 running every test against the pages just built"
if ! $PY -m pytest -q; then
  echo
  echo "  TESTS FAILED -- do not commit or publish (git checkout -- demo data/ideology restores the verified files)."
  exit 13
fi

echo
echo "12/12 supervisor: independent recount of every published number"
PYTHONPATH=src $PY -m civicalign.agents.supervisor || exit 14

echo
echo "done. Snapshot accepted, every check passed, pages built."
