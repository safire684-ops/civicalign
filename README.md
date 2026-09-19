# CivicAlign

Deterministic metrics for legislative accountability and institutional drift.
This repo implements **Sections 2–5** of the math spec (Pillars 4, 5 and 6).

## Quick start

```bash
./scripts/fetch_data.sh    # ~9 MB of source data, stamps data/raw/PROVENANCE.tsv
./scripts/report.sh        # prints the full report
```

No install and no venv needed for the report -- the package is stdlib-only, and
`report.sh` just sets `PYTHONPATH=src`. For the tests:

```bash
python3 -m venv .venv && ./.venv/bin/pip install pytest
./.venv/bin/python -m pytest -q          # 19 tests
```

`conftest.py` puts `src/` on the path, so tests need no install either. (An
editable install via `pip install -e .` also works but proved flaky on Python
3.14 here -- if `import civicalign` ever fails, rerun the install or just use
`PYTHONPATH=src`.)

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

**Working, on real 119th Congress data.**

- Everything senator-to-senator: committee drift, chamber median, cloture pivot,
  party medians. One ruler, no bridging needed.
- **Pillar 4**, via regression on real election results. Fit senator ideology
  against their state's presidential vote share (averaged over 2016/2020/2024)
  and read the residual. This never subtracts the two scales, so their units
  never have to match. State results explain **69%** of senator ideology, so the
  residual is deviation from a strong pattern.
- **Pillar 5's apportionment skew**, in vote-share units: the average state vote
  share per Senate seat vs. the national vote share. Election results on both
  sides, so again no bridging. **+3.37 points.**
- **Committees vs. the public**, same way, reported both against the nation and
  against the Senate's own average (which strips out the structural skew and
  majority control, leaving the committee-specific part).

**Still unavailable: absolute distance to the median voter.** The regression
answers "is this senator more extreme than their state's own result predicts?"
It cannot answer "how far is this senator from their state's median voter?" --
that is an absolute distance and does need bridged survey data. See
`sources/state_prefs.py` and METHODOLOGY.md.

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
apportionment skew             +3.37 points  (Senate seats vs. national vote)
state results explain           69%  of senator ideology (r-squared 0.687)

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

Most out of step with their own state (residual from the fitted line):

| senator | state | state vote | ideology | predicted | residual |
|---|---|---|---|---|---|
| Ron Johnson | WI | 50.4% | +0.897 | −0.003 | **+0.900** |
| Rick Scott | FL | 56.6% | +0.926 | +0.254 | +0.672 |
| Ted Budd | NC | 51.6% | +0.693 | +0.046 | +0.647 |
| Jon Ossoff | GA | 51.1% | −0.547 | +0.025 | −0.572 |
| Shelley Moore Capito | WV | 71.3% | +0.412 | +0.869 | −0.457 |

See `METHODOLOGY.md` for what these do and do not support — including the
whitepaper claim about Judiciary that this data does not back.
