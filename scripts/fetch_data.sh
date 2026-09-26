#!/usr/bin/env bash
# Refresh the raw source data as ONE verified snapshot, and record provenance.
#
# Voteview REVISES past scores when it re-estimates, so a number cached last
# month may no longer be the published number. Every refresh is stamped in
# data/raw/SNAPSHOT.json and data/raw/PROVENANCE.tsv.
#
# This runs the same all-or-nothing snapshot as the update chain
# (python -m civicalign.agents): every source is downloaded and validated into
# staging, and installed together only if every critical source succeeded.
# Downloading files one by one outside the snapshot is not supported: the
# Pillars 4-6 ingest refuses any raw file whose bytes the snapshot did not accept.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x ./.venv/bin/python ] && PY=./.venv/bin/python
PYTHONPATH=src exec $PY -m civicalign.agents
