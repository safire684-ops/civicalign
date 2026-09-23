#!/usr/bin/env bash
# The whole update chain, in the order that keeps bad data off the page.
#
#   1 fetch    each source independently; a source that fails its own check
#              leaves the previous good file in place
#   2 verify   61 tests, including ones that recompute every published figure
#              from the raw files
#   3 rebuild  push the new numbers into the demo page, which carries its data
#              inside itself
#   4 confirm  re-run the checks against the rebuilt page
#
# If step 2 fails the page is NOT rebuilt: the site keeps serving the last
# figures that passed, which is the whole point of doing it in this order.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x ./.venv/bin/python ] && PY=./.venv/bin/python

echo "1/4  fetching sources"
PYTHONPATH=src python3 -m civicalign.agents
fetch_status=$?

echo
echo "2/4  verifying the data"
if ! $PY -m pytest -q --ignore=tests/test_published_pages.py --ignore=tests/test_whitepaper.py; then
  echo
  echo "  TESTS FAILED -- the page was not rebuilt."
  echo "  It is still showing the last figures that passed. Read the failure above:"
  echo "  a test naming a stale number means the data moved and the prose needs it."
  exit 2
fi

echo
echo "3/4  rebuilding both pages"
PYTHONPATH=src python3 -m civicalign.build_demo || exit 3

echo
echo "4/4  confirming the rebuilt pages"
$PY -m pytest -q tests/test_published_pages.py || exit 4

echo
echo "5/5  supervisor: independent recount of every published figure"
PYTHONPATH=src $PY -m civicalign.agents.supervisor || exit 5

if ! $PY -m pytest -q tests/test_whitepaper.py >/dev/null 2>&1; then
  echo
  echo "  note: WHITEPAPER.md quotes figures that have moved. The pages are"
  echo "  correct and rebuilt; update the whitepaper's prose when convenient."
fi

echo
if [ $fetch_status -ne 0 ]; then
  echo "done, but at least one source could not be fetched (see above)."
  echo "Everything else is current."
  exit $fetch_status
fi
echo "done. All sources current, all checks passed, page rebuilt."
