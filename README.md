# CivicAlign

Deterministic metrics for legislative accountability and institutional drift.
This repo implements **Sections 2–5** of the math spec (Pillars 4, 5 and 6).

## Quick start

```bash
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
./scripts/fetch_data.sh          # ~8 MB, stamps data/raw/PROVENANCE.tsv
./.venv/bin/python -m civicalign # prints the full report
./.venv/bin/python -m pytest -q  # 11 tests
```

No third-party runtime dependencies — stdlib `csv`, `json`, `statistics` only.
That is deliberate: the whole point of this repo is numbers people can check, and
a zero-install pipeline is one fewer thing standing between a reader and a
reproduction. `pytest` is the only dev dependency.

## Layout

```
src/civicalign/
  config.py            every definitional choice that changes a published number
  space.py             Section 2 — the shared metric space X = [-1, +1]
  alignment.py         Section 3 — Pillar 4, senator vs. state
  chamber.py           Section 4 — Pillar 5, chamber vs. nation
  committees.py        Section 5 — Pillar 6, committee drift
  pipeline.py          wires the sections together
  cli.py               the report
  sources/
    voteview.py        senator coordinates + the seat-dedupe guard
    rosters.py         who actually holds a seat right now
    state_prefs.py     the bridging interface — THE swappable part
```

## What works today, and what does not

**Working, on real 119th Congress data.** Everything senator-to-senator: committee
drift, chamber median, cloture pivot, party medians. These live on one ruler and
need no bridging.

**Blocked.** Pillar 4 entirely, and the national half of Pillar 5. Both need state
and national median-voter coordinates in the same space as senator scores. The
default source refuses to produce a number rather than inventing one, so the CLI
prints `UNAVAILABLE` instead of something plausible and wrong. See
`sources/state_prefs.py` for the three options and the recommendation.

## Two bugs this repo is built to prevent

Both were found in real data. Neither raises an error on its own — each just
produces a confident wrong number. Both have regression tests.

**1. Seat double-counting.** Filtering Voteview on `congress == 119` gives **104
Senate rows for 100 seats**: FL, OH, OK and SC each carry a departed member
alongside their replacement. All four extras are Republicans, so the naive
chamber median is `+0.3645` instead of the correct `+0.3100`. That 0.045 artifact
is a large fraction of an apportionment skew which is itself only 0.1–0.3 wide.
Fixed by requiring a roster in `load_scores()` and rejecting any state with more
than two senators.

**2. Frozen scores.** `nominate_dim1` **never changes over a career** — Murkowski
is `0.204` in all ten of her Congresses. Building Pillar 4 on it freezes every
alignment gap for life and makes every time series a flat line. The per-Congress
column that actually moves is `nokken_poole_dim1`, which is what `config.py`
selects. Trade-off documented there.

## Current numbers (119th Congress)

```
chamber median                 +0.3100
60th-vote pivot (cloture)      +0.4400   (+0.130 vs median)
majority (R) median            +0.5640
minority median                −0.3780
party gap                       0.9420
```

Most-drifted committees, `CCD = committee median − chamber median`:

| committee | n | median | CCD | chair | chair − cmte |
|---|---|---|---|---|---|
| Environment | 18 | +0.003 | −0.307 | +0.412 | +0.409 |
| Appropriations | 28 | +0.004 | −0.306 | +0.170 | +0.166 |
| Foreign Relations | 22 | +0.535 | +0.225 | +0.640 | +0.105 |
| Homeland/Govt Affairs | 15 | +0.521 | +0.211 | +0.812 | +0.291 |
| Budget | 20 | +0.128 | −0.182 | **+0.897** | **+0.769** |
| Commerce | 28 | +0.326 | +0.016 | **+0.865** | **+0.539** |
| Judiciary | 21 | +0.361 | +0.051 | +0.461 | +0.100 |

See `METHODOLOGY.md` for what these do and do not support — including the
whitepaper claim about Judiciary that this data does not back.
