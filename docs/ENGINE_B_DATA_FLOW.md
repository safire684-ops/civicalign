# Engine B data flow — Pillars 4–6, file by file

How a number gets from a source file onto the published page, and where each
step can refuse. All commands run from the repository root with
`PYTHONPATH=src`. Engine B (`src/civicalign/ideology/`, `build_pages.py`)
imports nothing from Engine A (Pillar 1); a test enforces this.

```
source files ──1 fetch──▶ data/raw/ + SNAPSHOT.json ──2 verify──▶ 3 Pillar 1 bind and context checks
  ──4 ingest──▶ data/ideology/*.jsonl (versioned inputs)
  ──5 bridge──▶ ideology_bridge.jsonl        ──6 anchors──▶ reference_anchors.jsonl (visual only)
  ──7 bills───▶ bill_sponsor_classifications.jsonl   ──8 outcomes──▶ senate_bill_outcomes.jsonl
  ──9 verify both bill tables
  ──10 compute─▶ data/ideology/metrics/<key>.json + metrics_index.jsonl (versioned results)
  ──11 build───▶ demo/senator-check.html, demo/methodology.html (with input fingerprints)
  ──12 tests, 13 supervisor──▶ 14 commit and deploy (only if everything passed and something changed)
```

The sections below describe each step's code and tables; section 11 lists the
whole daily chain in order.

## 1. The source snapshot — `python -m civicalign.agents`

`agents/sources.py` lists every source with a validator; `agents/base.py`
downloads them into staging and installs them together only if every critical
source succeeded (otherwise nothing is replaced and the run fails). A file
counts as changed only when its content changed (zip archives are keyed by
their members, not their timestamps). The accepted set is recorded in
`data/raw/SNAPSHOT.json` (per file: URL, SHA-256, content key, content-changed
and last-checked times) and every change is appended to
`data/raw/PROVENANCE.tsv`. The raw files themselves are gitignored.

Engine B reads: Voteview `HSall_members.csv`; congress-legislators
`legislators-current.json`, `committee-membership-current.json` and
`committees-current.json`; the American Ideology Project
`aip_states_ideology_v2022a.tab`; Census `NST-EST2024-ALLDATA.csv`; and the
GovInfo bill-status archive for the Congress's Senate bills
(`BILLSTATUS-119-s.zip`).

A new source can be added to the accepted snapshot on its own, without
refreshing the others: `python -m civicalign.agents --add "<source name>"`
(refuses a source the snapshot already has, or a snapshot that was not
accepted). The committee-names source was added this way.

`python -m civicalign.agents.verify` then checks the roster, join keys, record
counts and that no source shrank drastically. The Pillar 1 (Engine A) binding
and context checks run next (`python -m civicalign.explain.bind`,
`python -m civicalign.explain.context --check-fresh`); Engine B does not use
their output.

## 2. Versioned inputs — `python -m civicalign.ideology.ingest [--dry-run]`

`ideology/ingest.py` reads only files the snapshot accepted and whose bytes
still match its SHA-256 (else "INGEST REFUSED"). Every record carries `source`,
`source_url`, `source_version` (the snapshot content key), `source_sha256`,
`retrieved_at` (when CivicAlign first retrieved that content) and `fixture`.
`ideology/records.py` defines the tables and validates every record;
`ideology/store.py` appends only records whose content changed.

| Table (`data/ideology/`) | Key | Content |
|---|---|---|
| `senator_ideology.jsonl` | bioguide_id, congress | Every Senate row of the Congress in Voteview, with `nominate_dim1` (used) and `nokken_poole_dim1` (stored only), vote count, party code and `seated` from the roster. Guards: one row per member; roster and Voteview agree on state; at most two seated per state and 100 in all. **The only source of a senator's current `nominate_dim1`**, including the current sponsor scores shown beside bills. |
| `constituency_ideology.jsonl` | geography_type, geography_id, methodology_version | Every American Ideology Project state row, every wave, estimate and standard error in the survey's own units, with a scale note. |
| `state_population.jsonl` | geography_type, geography_id, measurement_year, vintage | Census July 1 estimates for the 50 states and DC, every year of the vintage (the vintage is in the key because later vintages revise earlier years). |
| `committee_membership_events.jsonl` | congress, committee_id, bioguide_id | Standing committees only, as observed events: joined, left, role changed. Dates are observed (first retrieval showing the change), never official; the first observation of a committee is a baseline. |
| `committee_names.jsonl` | committee_id | Each standing committee's official name and the short name the page shows (the official name without "Senate Committee on (the)"); any other form is refused. |

## 3. The store — append-only, hash-chained

One JSON Lines file per table. Each line is `{record_id, prev_record_id,
content_sha256, snapshot_run_utc, content}`, with `record_id =
sha256(prev_record_id | content_sha256)`, so each key's versions form a chain
and an edited, deleted or reordered line is detectable (`Table.verify()`).
Files are opened for appending only. Every table in `data/ideology/` (the
inputs above, the bridge, the anchors, both bill tables and the result index) is
versioned this way; nothing old is overwritten or deleted.

## 4. The bridge — `python -m civicalign.ideology.bridge`

`ideology_bridge.jsonl` (key `bridge_version`) records the bridges; the active
one is `config.active_bridge_version` = `none-v0`, status NONE, with no method.
`bridge.to_common()` therefore returns NOT_AVAILABLE with the reason for every
public estimate. Status PROVISIONAL or VALIDATED requires a method, its
parameters and both model versions (and, for VALIDATED, validation results); a
method that is not implemented still yields NOT_AVAILABLE. The national public
estimate (`ideology/national.py`) is UNRESOLVED and always NOT_AVAILABLE.

## 5. The reference anchors — `python -m civicalign.ideology.anchors [--dry-run]`

`ideology/anchors.py` reads exactly three configured figures (Sanders, Biden,
Vance) from the verified Voteview file into `reference_anchors.jsonl` (key
`anchor_id`): the Voteview id of the person's Senate rows, the single
`nominate_dim1` shared by all their House and Senate rows (refused if they
differ), their Congress ranges and vote counts, their label and the source
fields. Voteview's President rows are never read. **Visual only**: `compute`
never reads this table and it is not in the result key.

## 6. Bill/sponsor classifications — `python -m civicalign.ideology.bills [--dry-run] [--tally]`

`ideology/bills.py` reads the verified bill-status archive (refused if its bytes
do not match the snapshot) and writes `bill_sponsor_classifications.jsonl` (key
congress, bill_id): one record per Senate bill with its title, primary sponsor
and Bioguide id, the sponsor class under rule `sponsor_nominate_dim1_sign_v1`
(negative score LIBERAL_SPONSOR, positive CONSERVATIVE_SPONSOR, zero
ZERO_SCORE_SPONSOR, otherwise UNKNOWN with the reason), the fixed wording that
the class describes the sponsor and not the bill, each Senate standing
committee's "Referred To" / "Reported By" / "Reported Original Measure" /
"Discharged From" activities with their dates, the SHA-256 of the bill's XML
(`bill_fingerprint`) and the source fields. It stores the bill-to-sponsor
classification only; no model is used.

- **When a bill is re-versioned**: only when the bill's official record, its
  sponsor or Bioguide id, the classification rule, the class (the sign of the
  sponsor's current score) or the unknown reason changes.
- **Exact score changes that stay on the same side of zero do not re-version
  any bill** (for example −0.400 to −0.385). **A classification change does**:
  a score that crosses zero (for example −0.010 to +0.005, or +0.010 to 0)
  re-versions exactly that sponsor's bills.
- The score stored in a record (`sponsor_nominate_dim1`, with the
  `senator_ideology` record and version it came from) is historical: the score
  that version was classified from. The current score is always read from
  `senator_ideology` (`bills.current_sponsor_scores()`).
- `bill_tallies.py` turns the records into counts that each carry their exact
  bill ids: `passed_senate_tally()` for Pillar 5 and `committee_tallies()` for
  Pillar 6 (referred, reported, reported-of-referred and
  reported-without-referral per committee, each by sponsor class).

## 7. Senate bill outcomes and the bill-table check — `python -m civicalign.ideology.bill_outcomes [--dry-run] [--audit] [--verify]`

`ideology/bill_outcomes.py` reads the same verified archive and writes
`senate_bill_outcomes.jsonl` (key congress, bill_id): each bill's Senate passage
and enactment evidence. Passed the Senate (rule `senate_passage_loc17000_v1`):
a Library of Congress action code 17000 and no later Senate action vitiating
the passage; the record keeps every code-17000 action, the Senate floor action
and whether an engrossed Senate text exists. Enacted (rule
`enactment_signature_or_public_law_v1`): a presidential signature or a recorded
public law; the record keeps the basis, the public-law number or that it is
pending, and the dates. Nothing here reads Voteview, so a Voteview update never
changes an outcome record. An unchanged archive writes nothing.

`--verify` then checks both bill tables before anything is computed: each is
valid and hash-chained; they cover the same bills from the same archive content;
every passage count traces to its bills and agrees with the independent
evidence; every stored class matches the sign of the sponsor's latest score in
`senator_ideology`; and a dry refresh of either table would write nothing
(current with the verified snapshot). Any problem stops the chain.

## 8. Versioned results — `python -m civicalign.ideology.compute [--verify] [--full]`

`ideology/pillars.py` holds the pure calculations (Pillar 4 per senator; Pillar 5
plain and population-weighted means and medians; Pillar 6 committee median and
drift); `ideology/compute.py` runs them on the current input versions and
settings (`config.py`: score column, survey wave, weighting method, population
year and vintage, bridge version, committee prefix, Congress).

- The result key is the hash of every input `record_id` used plus every
  number-changing setting. Same inputs, same key.
- `data/ideology/metrics/<key>.json` is written once (exclusive create; an
  existing file is never overwritten). It holds the settings, the versions of
  every source it used, the fingerprints, which record computed each result,
  and the results. Every quantity is `{value, status (AVAILABLE | PROVISIONAL
  | NOT_AVAILABLE), units, reason}`.
- `data/ideology/metrics_index.jsonl` is append-only; each line chains to the
  previous key and carries the file's content hash.
- Modes: **unchanged** (the key exists: nothing written); **committees_only**
  (only membership changed: only those committees recomputed, the rest carried
  and credited to the record that computed them); **full** (anything else).
  A carried result always equals a full recompute (tested).
- `--verify`: every indexed file exists and matches its hash and key, the index
  chains, there are no unindexed files, the latest result is current, and it
  equals a full recompute.

## 9. The published pages — `python -m civicalign.build_pages [--check]`

`build_pages.py` reads only the latest saved result (checked against its index
hash), the methodology registry (`ideology/methodology.py`), the three stored
anchors, the stored committee names, and the two bill tables (through
`bill_tallies.py`, with current sponsor scores from `senator_ideology`), and
fills the templates in
`src/civicalign/templates/` to write `demo/senator-check.html` (data embedded)
and `demo/methodology.html`. It never recalculates. It refuses to build if the
registry does not cover every number in the record, if any number has no entry,
if the anchors are not exactly the configured three, or if a committee has no
official name. Each embedded number carries its value, display text (the
registry's decimals, rounded half-up), status, reason, units, registry id and
path; in the page every number is rendered by one function that refuses a
number without an entry and opens its methodology when selected. `--check`
compares instead of writing.

**Presentation** (`ideology/display.py`, never imported by any calculation):
each value on Voteview's scale also carries its display position, (score + 1) ×
50, as a whole number and with one decimal; each difference carries its size in
display points; each senator carries a side label; and the Senate and committee
sentences are generated by fixed rules (`display_position_v1`, `side_label_v1`,
`senate_position_wording_v1`, `population_shift_wording_v1`,
`committee_comparison_wording_v1`, all published on the methodology page). Survey
estimates never get a display position. Each senator's party (R, D, I) is read
at build time from the congress-legislators roster, only if its bytes match the
verified snapshot, and the roster version is recorded in the page's provenance
(`meta.identity_source`); party is never stored in `senator_ideology`.

The bill counts (Pillar 5 "What the Senate passed" and each Pillar 6
committee's bills sent here and sent back) are embedded with the exact bill
ids behind each count, so every number traces to its bills; the build refuses a
count that does not trace to its ids, or a committee named by the bills that has
no Pillar 6 result. **Each build records its input fingerprints**
(`bill_outcomes.input_versions()`): the fingerprints of both bill tables and of
`senator_ideology`, the Voteview source versions, the bill-status archive
version, and the classification, outcome and enactment rule versions. Because
every table is append-only, the fingerprints of any earlier page can be
recomputed from the prefix of each table that existed when it was built.

## 10. Tests and the supervisor

`python -m pytest -q` runs every test against the pages just built.
`python -m civicalign.agents.supervisor` then re-reads the raw files with its
own code (it does not import `ideology.pillars` or `ideology.inputs`) and
reproduces every published number; the full list is in `METHODOLOGY.md`
("Verification"). For the bill counts it re-reads each bill's own XML and the
raw Voteview file, recounts every Pillar 5 outcome count and every Pillar 6
committee count, checks each listed bill's sponsor, committee action dates and
current score, confirms every stored class matches the sign of the latest
score, and **verifies that the page names the current, verified source and table
versions**. For the presentation it re-derives every display position from the
raw score, confirms no survey estimate carries one, re-applies every wording
rule to the raw values, and checks every party label against the verified
roster. It also runs the unchanged Pillar 1 checks.

## 11. The daily update

`.github/workflows/update.yml` (daily, 11:00 UTC) and `scripts/update.sh` run the
same chain (a test keeps them identical):

1. fetch the verified sources (`python -m civicalign.agents`)
2. verify the snapshot (`python -m civicalign.agents.verify`)
3. Pillar 1 steps: bind Senate passage votes, and check the Stage 2.5 records
   belong to this snapshot
4. ingest the Engine B inputs (`python -m civicalign.ideology.ingest`)
5. record the bridge (`python -m civicalign.ideology.bridge`)
6. refresh the reference figures (`python -m civicalign.ideology.anchors`)
7. refresh the bill/sponsor classifications (`python -m civicalign.ideology.bills`)
8. refresh the Senate bill outcomes (`python -m civicalign.ideology.bill_outcomes`)
9. verify both bill tables (`python -m civicalign.ideology.bill_outcomes --verify`)
10. compute Pillars 4–6 (`python -m civicalign.ideology.compute`)
11. build the pages (`python -m civicalign.build_pages`)
12. run every test (`python -m pytest -q`)
13. run the checker (`python -m civicalign.agents.supervisor`)
14. commit and deploy, only if every step passed

Each step is a gate: a failure stops the chain. Only if every step passes, and
something changed, does the workflow commit `demo/senator-check.html`,
`demo/methodology.html`, `data/ideology/` (including
`bill_sponsor_classifications.jsonl` and `senate_bill_outcomes.jsonl`),
`data/raw/PROVENANCE.tsv` and `data/explanations/` (and the snapshot, only when
something else changed), and then deploy `demo/`. Otherwise nothing is committed
and the previous verified site stays live. The bill steps read only the verified
snapshot: no API call and no model.

## Adding or changing a displayed number

1. Add the quantity to `ideology/pillars.py` (or `compute.py`) in the
   `{value, status, units, reason}` shape.
2. Add its registry entry to `ideology/methodology.py` (source, transformation,
   formula, versions, limitations, and why it can be NOT_AVAILABLE). The build
   and the tests refuse a number without one.
3. Render it in `src/civicalign/templates/senator-check.template.html` through
   `num()`.
4. Add an independent recount to `agents/supervisor.py`.

A bill count follows the same path with kind `outcome` (Pillar 5) or `billflow`
(Pillar 6) in the registry: it comes from `bill_tallies.py`, carries its exact
bill ids, and is recounted by the supervisor from the raw archive.
