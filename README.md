# CivicAlign

A Senate accountability tool made of two separate engines:

- **Engine A — legislative accountability (Pillar 1):** what a senator actually
  voted for, bound to the official record and the exact text voted on.
- **Engine B — institutional and ideological context (Pillars 4–6):** where a
  senator's voting record sits on Voteview's scale beside their state's public
  estimate; where the Senate's average sits, counted by senator and weighted by
  the population each senator represents; and where each standing committee's
  members sit compared with the Senate.

It is not an ideology lookup, it does not rank politicians, and it does not
claim to measure whether a senator represents their voters.

- Live site: https://safire684-ops.github.io/civicalign/ (`/senator-check.html`,
  methodology `/methodology.html`). The rebuilt Engine B pages described here
  are on the `pillars-4-6-rebuild` branch and are not published yet; the live
  site still runs the previous version until they are.
- The site rebuilds daily from a verified source snapshot. Figures, rosters and
  committee memberships are expected to change; the methods below are not.

## Quick start

```bash
./scripts/fetch_data.sh    # the verified source snapshot (all or nothing), stamped in data/raw/
./scripts/update.sh        # the whole daily chain locally (see "The daily update")
./scripts/build_pages.sh   # rebuild the two published pages from the saved results (--check compares)
./scripts/report.sh        # print the saved Pillars 4–6 results (--json for the record)
```

The package is stdlib-only; the scripts just set `PYTHONPATH=src`. `pytest` is
the only development dependency:

```bash
python3 -m venv .venv && ./.venv/bin/pip install pytest
./.venv/bin/python -m pytest -q
```

## What the site shows (Engine B, Pillars 4–6)

Every number on the page opens its methodology: the raw source, what is done to
it, the formula, the recorded versions it depends on, and its limits. A number
without a methodology entry cannot be displayed. Numbers are shown in their own
units (Voteview's −1 to +1 scale, or the survey's own scale); there is no 0–100
display of anything.

### Pillar 4 — senator and state, side by side

Each senator's Voteview `nominate_dim1` score, and separately their state
public's estimated ideology from the American Ideology Project (2020 wave, with
its standard error and survey period). The two come from different measurement
systems and are never compared directly. There is no validated bridge between
them (the active bridge is
`none-v0`, status NONE), so the state estimate is never placed on the senator
scale and **no senator-to-state distance is calculated**; the page says so and
why.

To make the scale readable, three recognisable figures are shown on it as
**visual reference points only**: Bernie Sanders (his Voteview score, which
covers his House and Senate service together), Joe Biden (his Senate voting
record, not his presidency) and JD Vance (his Senate voting record). Their
values come from the same verified Voteview file. They are never an input to
any calculation.

### Pillar 5 — the Senate, counted two ways

The main result compares the Senate's average score with each senator counted
equally against the average with each senator weighted by the population they
represent (their state's population divided by the number of senators the state
has seated). The difference shows how the equal representation of states moves
the Senate's average. It describes voting records and state populations only,
not which laws passed or why. The weighting method is a candidate method, not a
final scientific standard. The Senate median and a population-weighted median
are kept as a secondary comparison, shown only in details.

The national public estimate is **unresolved**: no definition has been chosen,
and no bridge would place it on the senator scale. So no Senate-to-public gap is
calculated.

### Pillar 6 — committees and the Senate

For each standing committee: the median score of its current members, and the
committee median minus the Senate median (sign kept). Descriptive only: where a
committee's members sit says nothing on its own about what the committee did or
decided. Committee names come from the official congress-legislators committee
list (`committees-current.json`). Membership dates are the dates CivicAlign
observed them, not official appointment dates. No committee-to-public drift is
calculated while the national estimate is unresolved.

Retired and not coming back (their code has been removed): the caucus-group
peer comparison, the seats-versus-nation election figure and the state-vote
fit that was used only for diagnostics, the committee bill-flow and Yes/No-split
analysis, landmark bills, the old score that subtracted a voter estimate from a
senator's score, and any 0–100 display.

## Pillar 1 — official vote records (no generated explanations)

The deterministic foundation for future plain-English vote receipts is built
through **Stage 2.5**. Nothing in it calls a model, and the live page reads
none of it.

- **Stage 2, binding** (`python -m civicalign.explain.bind`, in the daily automated update):
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

**Stage 3 (a Maker/Checker development evaluation of plain-English receipts)
is set up in `src/civicalign/evaluation/`; one development run was stopped, and
its results are local only. No generated explanation is currently published.**

## How the numbers are stored and checked

- **Versioned, append-only storage** (`data/ideology/`): every input record
  names its source file, snapshot version, SHA-256 and retrieval date; a new
  version is written only when content changes; each key's versions are
  hash-chained; result records are write-once and indexed in order. Nothing
  old is overwritten or deleted.
- **The daily update** runs as one gated chain: fetch the verified snapshot,
  verify it, the Pillar 1 binding and context checks, then for Pillars 4–6
  ingest, bridge, reference anchors, compute, build the pages, run every test,
  and run the supervisor. Only if every step passes, and something changed, is
  anything committed and published; otherwise the previous verified site stays
  live.
- **The supervisor** (`python -m civicalign.agents.supervisor`) re-reads the raw
  files with separate code and reproduces every published Pillars 4–6 number,
  checks the reference anchors and committee names against their sources,
  confirms nothing that needs the bridge or a national estimate is shown,
  checks every displayed number against its methodology entry, and verifies the
  stored records; it also re-derives every Pillar 1 binding and source packet.

`docs/ENGINE_B_DATA_FLOW.md` walks through the Engine B data flow file by file;
`METHODOLOGY.md` explains the methods and their known limits; `HANDOFF.md` is
the detailed current project state.

## Layout

```
src/civicalign/
  config.py          every setting that changes a published number
  ideology/          Engine B: records.py, store.py, ingest.py (versioned inputs); bridge.py, national.py;
                     pillars.py (Pillars 4-6); compute.py (versioned results); anchors.py; methodology.py
  build_pages.py     the two published pages, from the saved results and the methodology registry
  templates/         the page templates (outside demo/, which is what the site publishes)
  cli.py             python -m civicalign: print the saved Pillars 4-6 record
  agents/            snapshot fetch and verify; supervisor.py (independent recount, Engine B and Pillar 1)
  explain/           Pillar 1: binding.py, bind.py (Stage 2); relevance.py, context.py (Stage 2.5)
  evaluation/        Pillar 1 Stage 3 development evaluation (nothing is published from it)
  pipeline.py, receipts.py   Pillar 1 floor-vote evidence
  sources/           readers for Voteview, rosters, bill status, Senate votes, U.S. Code, Public Laws, Federal Register
demo/                the published site (senator-check.html, methodology.html, civicalign.css)
data/ideology/       Engine B versioned inputs and results
data/raw/            the source snapshot (files gitignored; SNAPSHOT.json and PROVENANCE.tsv tracked)
docs/archive/        superseded design documents, kept for history only
```

## Two data bugs this repo guards against

Both were found in real data; neither raises an error on its own; both have
regression tests.

1. **Seat double-counting.** Filtering Voteview on the current Congress returns
   more Senate rows than seats (members who left sit beside their
   replacements), which shifts the chamber middle. The current roster decides
   who is seated, and a state with more than two seated senators, or more than
   100 seated in all, stops the ingest.
2. **Choosing the score column deliberately.** Voteview's `nominate_dim1` is one
   career-long score per member; `nokken_poole_dim1` is re-estimated each
   Congress. Pillars 4–6 use `nominate_dim1` (one stable scale for senators and
   the reference figures; `nokken_poole_dim1` is stored beside it as extra data
   only). The Pillar 1 floor-vote evidence keeps `nokken_poole_dim1`. Both
   settings are in `config.py`.
