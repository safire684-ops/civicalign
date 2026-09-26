# Engine B data flow — Pillars 4–6, file by file

How a number gets from a source file onto the published page, and where each
step can refuse. All commands run from the repository root with
`PYTHONPATH=src`. Engine B (`src/civicalign/ideology/`, `build_pages.py`)
imports nothing from Engine A (Pillar 1); a test enforces this.

```
source files ──1 fetch──▶ data/raw/ + SNAPSHOT.json ──2 verify──▶
  ──3 ingest──▶ data/ideology/*.jsonl (versioned inputs)
  ──4 bridge──▶ ideology_bridge.jsonl        ──5 anchors──▶ reference_anchors.jsonl (visual only)
  ──6 compute─▶ data/ideology/metrics/<key>.json + metrics_index.jsonl (versioned results)
  ──7 build───▶ demo/senator-check.html, demo/methodology.html
  ──8 tests, 9 supervisor──▶ 10 commit and publish (only if everything passed and something changed)
```

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
`aip_states_ideology_v2022a.tab`; Census `NST-EST2024-ALLDATA.csv`.

A new source can be added to the accepted snapshot on its own, without
refreshing the others: `python -m civicalign.agents --add "<source name>"`
(refuses a source the snapshot already has, or a snapshot that was not
accepted). The committee-names source was added this way.

`python -m civicalign.agents.verify` then checks the roster, join keys, record
counts and that no source shrank drastically.

## 2. Versioned inputs — `python -m civicalign.ideology.ingest [--dry-run]`

`ideology/ingest.py` reads only files the snapshot accepted and whose bytes
still match its SHA-256 (else "INGEST REFUSED"). Every record carries `source`,
`source_url`, `source_version` (the snapshot content key), `source_sha256`,
`retrieved_at` (when CivicAlign first retrieved that content) and `fixture`.
`ideology/records.py` defines the tables and validates every record;
`ideology/store.py` appends only records whose content changed.

| Table (`data/ideology/`) | Key | Content |
|---|---|---|
| `senator_ideology.jsonl` | bioguide_id, congress | Every Senate row of the Congress in Voteview, with `nominate_dim1` (used) and `nokken_poole_dim1` (stored only), vote count, party code and `seated` from the roster. Guards: one row per member; roster and Voteview agree on state; at most two seated per state and 100 in all. |
| `constituency_ideology.jsonl` | geography_type, geography_id, methodology_version | Every American Ideology Project state row, every wave, estimate and standard error in the survey's own units, with a scale note. |
| `state_population.jsonl` | geography_type, geography_id, measurement_year, vintage | Census July 1 estimates for the 50 states and DC, every year of the vintage (the vintage is in the key because later vintages revise earlier years). |
| `committee_membership_events.jsonl` | congress, committee_id, bioguide_id | Standing committees only, as observed events: joined, left, role changed. Dates are observed (first retrieval showing the change), never official; the first observation of a committee is a baseline. |
| `committee_names.jsonl` | committee_id | Each standing committee's official name and the short name the page shows (the official name without "Senate Committee on (the)"); any other form is refused. |

## 3. The store — append-only, hash-chained

One JSON Lines file per table. Each line is `{record_id, prev_record_id,
content_sha256, snapshot_run_utc, content}`, with `record_id =
sha256(prev_record_id | content_sha256)`, so each key's versions form a chain
and an edited, deleted or reordered line is detectable (`Table.verify()`).
Files are opened for appending only.

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

## 6. Versioned results — `python -m civicalign.ideology.compute [--verify] [--full]`

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

## 7. The published pages — `python -m civicalign.build_pages [--check]`

`build_pages.py` reads only the latest saved result (checked against its index
hash), the methodology registry (`ideology/methodology.py`), the three stored
anchors and the stored committee names, and fills the templates in
`src/civicalign/templates/` to write `demo/senator-check.html` (data embedded)
and `demo/methodology.html`. It never recalculates. It refuses to build if the
registry does not cover every number in the record, if any number has no entry,
if the anchors are not exactly the configured three, or if a committee has no
official name. Each embedded number carries its value, display text (the
registry's decimals, rounded half-up), status, reason, units, registry id and
path; in the page every number is rendered by one function that refuses a
number without an entry and opens its methodology when selected. `--check`
compares instead of writing.

## 8–9. Tests and the supervisor

`python -m pytest -q` runs every test against the pages just built.
`python -m civicalign.agents.supervisor` then re-reads the raw files with its
own code (it does not import `ideology.pillars` or `ideology.inputs`) and
reproduces every published number; the full list is in `METHODOLOGY.md`
("Verification"). It also runs the unchanged Pillar 1 checks.

## 10. The daily update

`.github/workflows/update.yml` (daily, 11:00 UTC) and `scripts/update.sh` run the
same chain: fetch → verify → Pillar 1 bind and context checks → ingest → bridge →
anchors → compute → build pages → tests → supervisor. Only if every step passes
does the workflow commit `demo/senator-check.html`, `demo/methodology.html`,
`data/ideology/`, `data/raw/PROVENANCE.tsv` and `data/explanations/` (and the
snapshot, only when something else changed) and publish `demo/`. Otherwise
nothing is committed and the previous verified site stays live.

## Adding or changing a displayed number

1. Add the quantity to `ideology/pillars.py` (or `compute.py`) in the
   `{value, status, units, reason}` shape.
2. Add its registry entry to `ideology/methodology.py` (source, transformation,
   formula, versions, limitations, and why it can be NOT_AVAILABLE). The build
   and the tests refuse a number without one.
3. Render it in `src/civicalign/templates/senator-check.template.html` through
   `num()`.
4. Add an independent recount to `agents/supervisor.py`.
