# CivicAlign

A legislative accountability and perspective tool for the U.S. Senate. It shows
where each senator's voting record sits among comparable senators, how Senate
seats and committees compare with the country and the chamber, and which
official records each figure comes from. It is not an ideology lookup, it does
not rank politicians, and it does not claim to measure whether a senator
represents their voters.

- Live site: https://safire684-ops.github.io/civicalign/ (`/senator-check.html`,
  methodology report `/methodology.html`)
- The site rebuilds every week from current source data (see "How the weekly
  update works" in `HANDOFF.md`). Figures, rosters and peer groups are expected
  to change; the methods below are not.

## Quick start

```bash
./scripts/fetch_data.sh    # downloads the source data, stamps data/raw/PROVENANCE.tsv
./scripts/report.sh        # prints the figures, each labelled with its scale
./scripts/update.sh        # the whole weekly chain locally: fetch, verify, bind, test, rebuild, supervise
```

The package is stdlib-only (`csv`, `json`, `statistics`, `xml`); `report.sh`
just sets `PYTHONPATH=src`. `pytest` is the only development dependency:

```bash
python3 -m venv .venv && ./.venv/bin/pip install pytest
./.venv/bin/python -m pytest -q
```

## What the site shows

### Pillar 4 — each senator among comparable senators

The primary result is a **caucus-group peer comparison** (`peers.py`). Each
senator is compared with senators in the same caucus group who represent
*other* states whose recent presidential vote was similar:

- Caucus groups: the Republican caucus; the Democratic caucus, meaning Democrats
  plus the Independents whose Senate roster entry records that they caucus with
  them. Any other or missing party or caucus value is not grouped (it fails
  closed and gets no comparison).
- Similar states: the two-party presidential vote share, 2016, 2020 and 2024
  averaged equally (MIT Election Lab), within ±4 percentage points of the
  senator's state.
- At least six peers. The conclusion is published only if it is the same at
  ±2, ±3, ±4 and ±5 points; otherwise the page says the result depends on the
  window. Too few peers gets an honest "not enough comparable senators".
- Outcomes: within the observed range of the peers, outside it on the more
  liberal side, outside it on the more conservative side, window-dependent, or
  insufficient peers.
- Peers are listed by state, never ordered by position. Nothing is ranked.

This says where a voting record sits among comparable senators. It does not
say whether a senator represents, agrees with or matches the state's voters.

**Voter context.** A separate estimate of the state's voters (American Ideology
Project, 2020 wave) appears as supporting context on its own scale. It is never
subtracted from, or tested against, a senator's voting score: the two come
from different measurement systems with no validated bridge between them.

A regression of senator scores on state presidential vote is kept in
`representation.py` for diagnostics and for the methodology report's
explanation of why it is not used: its fitted line mostly measured the party
split and, in competitive states, fell where no senator sits. It produces no
published classification.

### Pillar 5 — Senate seats and the national vote

Same-scale comparisons of election results: the average presidential vote
share across Senate seats against the national vote share, by election. The
chamber's own middle and 60-vote point are shown on the senators' voting scale.

### Pillar 6 — committees against the Senate

Descriptive comparisons of each committee with the Senate overall: where its
members sit, what share of the bills it received it has formally sent forward
(described by sponsor, never as the bill's ideology), and where the Yes/No split
fell on its bills. No causal claims; a bill not yet sent forward is "not yet
sent forward", never dead.

### Recorded votes

Each senator card lists that senator's recorded Yea or Nay on the most recent
Senate passage votes, with links to the official records. No bill description
is shown.

## Pillar 1 — official vote records (no generated explanations)

The deterministic foundation for future plain-English vote receipts is built
through **Stage 2.5**. Nothing in it calls a model, and the live page reads
none of it.

- **Stage 2, binding** (`python -m civicalign.explain.bind`, in the weekly job):
  every Senate roll call is classified from the official question; passage
  votes on bills and joint resolutions are bound to the Senate's own record,
  the bill's GovInfo status record and the exact GovInfo text as voted on,
  cross-checked member by member against Voteview. Each binding also records
  the vote's actual result and the next legislative step, from the measure
  type, the chamber it started in, whether the Senate changed the text, and the
  result; a failed vote is never described as advancing.
- **Stage 2.5, source context** (`python -m civicalign.explain.context`, an
  offline job): the U.S. Code in force at the vote (never a later release,
  never today's law), cited Public Laws, the matching CRS summary, and for
  Congressional Review Act resolutions the bound rule and 5 U.S.C. 801. Each
  citation's relationship to the measure is read from where it sits in the
  voted XML (amended, replaced, used in a definition, applied as a test, or
  only named). Only provisions the measure needs are included, at the exact
  subsection or paragraph cited; the rest are tracked by hash. Unstructured
  citations in places that need content keep a vote pending rather than guessed.
  Every ready vote gets a hashed source packet with size figures; nothing is
  truncated.

**Stage 3 (a Maker/Checker evaluation of plain-English receipts) has not
started. No generated explanation exists or is published.**

## How the numbers are checked

Every weekly run is gated: an all-or-nothing source snapshot, a verification
step, the data tests, the page rebuild, the public-claim tests, and an
independent supervisor that re-reads the raw files and reproduces every
published figure, every peer group, every vote binding and every source packet
with separate code. If any step fails, nothing is committed and the previous
verified site stays live.

## Layout

```
src/civicalign/
  config.py          every definitional choice that changes a published number
  pipeline.py        builds the report
  peers.py           Pillar 4: the caucus-group peer comparison
  representation.py  the retired regression (diagnostics only) and Pillar 5's seats-vs-nation figure
  chamber.py         Senate middle and 60-vote point
  committees.py, output_ideology.py, gatekeeping.py   Pillar 6
  receipts.py        the recent passage votes on each card
  build_demo.py      the page's data blocks and the methodology report
  agents/            snapshot fetch, verify, supervisor
  explain/           Pillar 1: binding.py, bind.py (Stage 2); relevance.py, context.py (Stage 2.5)
  sources/           Voteview, rosters, bill status, Senate votes, U.S. Code, Public Laws, Federal Register, elections
```

`HANDOFF.md` is the current, detailed project state; `METHODOLOGY.md` and the
published methodology report explain the methods and their limits.

## Two data bugs this repo guards against

Both were found in real data; neither raises an error on its own; both have
regression tests.

1. **Seat double-counting.** Filtering Voteview on the current Congress returns
   more Senate rows than seats (members who left sit beside their
   replacements), which shifts the chamber middle. `load_scores()` requires the
   current roster and rejects any state with more than two senators.
2. **Frozen scores.** Voteview's career score (`nominate_dim1`) never changes
   over a career. The per-Congress score (`nokken_poole_dim1`) is used instead;
   the trade-off is documented in `config.py`.
