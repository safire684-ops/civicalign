# Project handoff — CivicAlign

Rewritten 25 September 2026 for a brand-new chat; updated the same day after
Step 4 part 1 (methodology registry and Pillar 4 reference anchors) and again
after Step 4 was completed (page builder and the three views in `demo/next/`)
and after the approved Pillar 5 plain-language card was added, and after Step 5A
(new pages published in `demo/`, official committee names, Pillar 1 tests off the
old page), and after Step 5B (old Pillars 4–6 code and tests removed, new
independent supervisor). Read all of it before doing
anything. The repository and this file are the source of truth; older design
documents, the whitepaper and chat history are not.

---

## 0. Safety rule (read first)

Do NOT restart the project, redesign Steps 1–4, change the
three reference anchors, switch away from DW-NOMINATE
(`nominate_dim1`), revive the retired 0–100 display, or bring back any retired
method (section 5) unless the user explicitly asks. Do not touch Engine A while
working on Engine B. Do not push, merge or deploy without the user's approval.
Work one step at a time and stop for review after each step.

---

## 1. Current branch and repository state

- Repo: `/Users/sarthakkesavarapu/Desktop/CivicAlign`, remote
  https://github.com/safire684-ops/civicalign
- **Working branch: `pillars-4-6-rebuild` — local only, NOT pushed.** It was
  created from local `main` so the live version stays intact during the rebuild.
- Local `main` is 1 commit ahead of `origin/main` (the Stage 3 harness commit
  `c2a596a`, also never pushed). `origin/main` is what the live site runs.
- The live site (https://safire684-ops.github.io/civicalign/, page
  `/senator-check.html`, report `/methodology.html`) still runs the OLD Pillars
  4–6 product from `origin/main`. The GitHub workflow (`.github/workflows/update.yml`)
  still runs weekly (Mondays 11:00 UTC) on `origin/main` and commits as
  `civicalign-bot`; its commits will need a rebase of this branch before any
  publish (the generated pages will conflict and must simply be regenerated).

Commits on `pillars-4-6-rebuild` that are not on `origin/main` (oldest first):

| Commit | What it did |
|---|---|
| `c2a596a` | Pillar 1 (Engine A) Stage 3 Maker/Checker evaluation harness. No generation results committed. |
| `bb1d716` | Source snapshot refresh from a local fetch on 2026-09-25 (`data/raw/SNAPSHOT.json`, `PROVENANCE.tsv`). Engine B inputs unchanged from the previous snapshot; the four bill-status archives (Engine A inputs) updated. This is the snapshot the Step 1 ingest read. |
| `83f685b` | **Step 1**: versioned input records, append-only store, ingest. |
| `5563810` | **Step 2**: state population table, bridge (NONE), national estimate (unresolved), Pillars 4, 5, 6 calculations. |
| `51deb13` | Added `population_weighted_mean_v1` beside the weighted median. |
| `4f99c6b` | Made the weighted mean the PRIMARY Pillar 5 method, weighted median SECONDARY; medians moved to `details`; fixed: an unscored seated senator's share of state weight is left out with them (no current number changed). |
| `183d684` | **Step 3**: versioned result records and incremental recomputation. |
| `1bf60f6` | HANDOFF rewritten for a fresh chat. |
| `1ac2156` | **Step 4 part 1**: methodology registry (`methodology.py`) and the three Pillar 4 reference anchors (`anchors.py`, `reference_anchors` table). |
| `4b9616b` | HANDOFF update for Step 4 part 1. |
| `d049b61` | **Step 4 complete**: page builder `build_pages.py`, templates in `demo/templates/`, built preview pages in `demo/next/`, `tests/test_pages.py`, one wording fix in `methodology.py`. See section 3. |
| `7ea7424` | HANDOFF update for Step 4 complete. |
| `6eb2969` | **Pillar 5 plain-language card** (approved wording) on the Step 4 preview page; one new page test. |
| `807aed4` | HANDOFF update for the Pillar 5 card. |
| `1901202` | **Step 5A**: new pages published in `demo/`, `demo/next/` retired, official committee names, Pillar 1 tests off the old page. See section 3. |
| `ca35529` | HANDOFF update for Step 5A. |
| `a229172` | **Step 5B**: old Pillars 4–6 modules and tests removed; new independent Engine B supervisor; `pipeline.py` reduced to Pillar 1. See section 3. |
| (next) | This HANDOFF update. |

Uncommitted in the working tree (leave them; they belong to the paused Engine A
Stage 3 work): `.gitignore` (ignores `evaluation/stage3/*.log`) and
`src/civicalign/evaluation/report.py` (review report counts cached input
tokens). Local-only, gitignored: `evaluation/stage3/runs/smoke-1` and
`evaluation/stage3/runs/dev-2026-09-24-r1` (a stopped Stage 3 run).

The local raw files in `data/raw/` (gitignored) match the committed
`SNAPSHOT.json`. The Engine B ingest refuses to run if they do not.

---

## 2. What we are building (plain language)

CivicAlign is a Senate accountability tool made of two separate engines.

- **Engine A — Legislative accountability (Pillar 1).** "What did this senator
  actually vote for, and what did the vote mean?" It binds each Senate vote to
  the official record and the exact text voted on, and (in evaluation) tests
  whether a Maker/Checker model pair can write plain-English receipts from
  official sources only. Code: `src/civicalign/explain/`,
  `src/civicalign/evaluation/`, `receipts.py`, `sources/billflow.py`,
  `sources/billstatus.py`, `sources/senate_votes.py`. **Not part of the current
  work. Do not modify it.**

- **Engine B — Institutional and ideological context (Pillars 4–6).** Code:
  `src/civicalign/ideology/`. Nothing in it imports Engine A (a test enforces this).
  - **Pillar 4 — senator vs. state.** Where a senator's voting record sits
    (Voteview DW-NOMINATE) compared with the estimated ideological centre of
    their state's public (American Ideology Project). The two are different
    measurement systems, so the senator-to-state distance needs a "bridge"
    between the scales; until one exists, the two are shown separately and the
    distance is not calculated.
  - **Pillar 5 — Senate vs. population and nation.** Where the Senate's centre
    sits; how that centre would move if each senator were weighted by the
    population they represent (the equal-state representation effect); and,
    once a national public estimate and a bridge exist, how the Senate compares
    with the national public.
  - **Pillar 6 — committees vs. Senate and public.** Where each standing
    committee's membership sits compared with the Senate (and, later, the
    public). Descriptive only: it never claims a committee blocked, obstructed
    or decided anything.

Pillars 2, 3 and 7 belong to someone else and are out of scope.

---

## 3. Completed work (Engine B, Steps 1–4, 5A and 5B)

### Step 1 — versioned inputs (`records.py`, `store.py`, `ingest.py`)

`python -m civicalign.ideology.ingest [--dry-run]` reads only files the source
snapshot accepted and whose bytes still match its SHA-256 (else "INGEST
REFUSED"). Each record carries `source`, `source_url`, `source_version` (the
snapshot content key), `source_sha256`, `retrieved_at` (when CivicAlign first
retrieved that content) and `fixture` (true only for test fixtures).

Tables in `data/ideology/` (JSON Lines, tracked in git):

| Table | Key | Content |
|---|---|---|
| `senator_ideology.jsonl` | bioguide_id, congress | Every Senate row of the 119th Congress in Voteview `HSall_members.csv`, with **both `nominate_dim1` (the default) and `nokken_poole_dim1` (extra data only)**, vote count, Voteview party code, `seated` (from the congress-legislators roster), roster version and date. A seated senator Voteview has not scored is recorded with null scores, never a predecessor's. Guards: one Voteview row per senator; roster and Voteview agree on state; ≤2 seated per state; ≤100 seated. Today: 104 rows, 100 seated, 4 departed (FL, OH, OK, SC) kept but not seated. |
| `constituency_ideology.jsonl` | geography_type, geography_id, methodology_version | American Ideology Project v2022a `mrp_ideology`, **estimate and standard error in AIP's own units**, survey period, wave, sample size, and a scale note stating it has no common metric with Voteview. All waves (2008, 2016, 2020) × 51 (50 states + DC) = 153. Source DOI https://doi.org/10.7910/DVN/BQKU4M. No national row. |
| `state_population.jsonl` | geography_type, geography_id, measurement_year, vintage | Census Vintage 2024 July 1 estimates, 2020–2024, 50 states + DC (Puerto Rico is in the file but elects no senators, so it is left out) = 255. The vintage is in the key because later vintages revise earlier years. |
| `committee_membership_events.jsonl` | congress, committee_id, bioguide_id | Standing committees only (`SS*`, four characters; no subcommittees, select or joint). Events `observed_joined` / `observed_left` / `observed_role_changed` with rank, title, majority/minority side. **Every date is OBSERVED**: the day CivicAlign first retrieved content showing the change, never an official appointment date (the `date_basis` field says so and the validator enforces it). The first observation of a committee is flagged `baseline` with a note that membership may have begun earlier. `records.membership_intervals()` derives `observed_start_date` / `observed_end_date`. Today: 351 baseline events, 16 committees, observed 2026-09-23. |
| `ideology_bridge.jsonl` | bridge_version | See Step 2. |
| `reference_anchors.jsonl` | anchor_id | The three Pillar 4 reference anchors; see Step 4 part 1. Visual only. |

Store (`store.py`): append-only; a new version is written only when content
differs from the key's current version; each key's versions are hash-chained
(`record_id = sha256(prev_record_id | content_sha256)`); `verify()` re-hashes,
re-walks the chains and re-validates; lines are never rewritten.

### Step 2 — bridge, national estimate, calculations

- `result.py`: every quantity is `{value, status (AVAILABLE | PROVISIONAL |
  NOT_AVAILABLE), units, reason, ...}`. Units always travel with the number.
- `bridge.py`: bridge records with status NONE / PROVISIONAL / VALIDATED and
  the fields each status requires. **The only bridge is `none-v0`, status NONE,
  and it is the active one** (`config.active_bridge_version`). `METHODS` is
  empty: no conversion exists. Anything needing the bridge returns
  NOT_AVAILABLE with the reason; a bridge naming an unimplemented method also
  returns NOT_AVAILABLE, never a guess. `python -m civicalign.ideology.bridge`
  records the default.
- `national.py`: the national public estimate is **UNRESOLVED**. Candidate
  definitions are listed (population-weighted mean of state estimates;
  population-weighted median; an individual-level national survey estimate; any
  of these by adults/citizens/voters). None is chosen; a population-weighted
  average of states is NOT treated as the national median. Always NOT_AVAILABLE.
- `pillars.py` (pure functions):
  - **Pillar 4**, per seated senator: `senator_score` (nominate_dim1, Voteview
    units), `state_public_estimate` (AIP estimate + standard error + survey
    period, AIP units), `state_on_senator_scale` NOT_AVAILABLE, `distance`
    NOT_AVAILABLE.
  - **Pillar 5**: "active senators" = seated and scored. Weights: each
    senator gets their state's population ÷ the number of senators the state has
    seated (a vacancy gives the sitting senator the whole state; an unscored
    senator's share is left out with them). Methods in `WEIGHTING_METHODS`, each
    labelled `CANDIDATE_METHOD_NOT_FINAL` with a definition and open questions:
    - `population_weighted_mean_v1` — **role PRIMARY** (the configured method):
      Σ score × weight ÷ Σ weight, compared with the plain Senate mean.
    - `population_weighted_median_v1` — **role SECONDARY_COMPARISON**: the first
      score where cumulative weight reaches half the total (exactly half averages
      with the next score), compared with the plain Senate median.
    Output: `plain_center`, `population_weighted_center`,
    `population_weighting_difference` (= plain − weighted, sign kept) for the
    configured method; `details` holds `chamber_median`, `chamber_mean` and every
    method's three numbers; `national_public` and `chamber_public_gap` NOT_AVAILABLE.
  - **Pillar 6**, per standing committee: members listed/scored/left out,
    `committee_median` (median of current members' nominate_dim1),
    `committee_senate_drift` = committee median − **Senate median** (sign kept),
    `committee_public_drift` NOT_AVAILABLE.
- `inputs.py`: `load()` assembles current inputs; `calculate()` runs all three
  pillars (not stored); `python -m civicalign.ideology.inputs` prints them.
- Config (`src/civicalign/config.py`, Engine B section): `pillars_score_column
  = "nominate_dim1"`, `standing_committee_prefix = "SS"`, `ideology_dir =
  data/ideology`, `pillars_aip_wave = 2020`, `active_bridge_version =
  "none-v0"`, `pillar5_weighting_method = "population_weighted_mean_v1"`,
  `pillar5_population_year = 2024`, `pillar5_population_vintage = "Vintage 2024"`.

### Step 3 — versioned results and incremental recomputation (`compute.py`)

`python -m civicalign.ideology.compute` (`--verify`, `--full`).

- Result key = hash of every input record_id used (senators, AIP rows,
  population rows, committee events per committee, bridge) + every
  number-changing setting (Congress, score column, AIP wave, weighting method,
  population year and vintage, bridge version, committee prefix).
- `data/ideology/metrics/<input_key>.json`: one record, **write-once**
  (exclusive create; refuses to overwrite even an unindexed file). Contains
  settings, versions (Congress; measurement date = newest input retrieval date;
  legislator model, roster, public model, population, committee membership and
  bridge versions with source hashes and retrieval dates; weighting methods;
  national UNRESOLVED), fingerprints, `computed_in` (which record computed each
  result), and the results.
- `data/ideology/metrics_index.jsonl`: append-only; each line chains to the
  previous key and carries the file's content hash and `computed_at`.
- Modes: **unchanged** (key exists → nothing written); **committees_only**
  (only membership changed → only those committees recomputed, everything else
  carried and credited to the record that computed it; removed committees
  dropped); **full** (any other change: senator scores or seats, public
  estimates, populations, bridge, settings). A carried result always equals a
  full recompute (tested).
- `verify()`: every indexed file exists, matches its hash and its key; the index
  chains; no unindexed files; the latest result was computed from the current
  inputs (else "no longer current: run compute"); and it equals a full recompute.
- Committed: one real record, key `5f42ca01…4cc5`, mode full, measurement date
  2026-09-24. A second run writes nothing; verify passes.

### Step 4 part 1 — methodology registry and reference anchors (`methodology.py`, `anchors.py`)

**Methodology registry** (`src/civicalign/ideology/methodology.py`). It now
exists and covers every displayed metric: 19 entries, one per displayed number
(Pillar 4: senator score, state public estimate, state on senator scale,
distance, reference anchors; Pillar 5: senators included, plain mean, weighted
mean, weighting difference, and in details the plain median, weighted median
and median difference, plus national public and chamber–public gap; Pillar 6:
members listed, members scored, committee median, committee–Senate drift,
committee–public drift). Each entry has: label, pillar, views
(`senator_state`, `senate_nation`, `committee_senate_nation`), placement
(`main` or `details`), kind (`quantity`, `count`, `reference`), the result-record
paths it covers (`*` = any senator or committee), units, display decimals
(3 for the Voteview scale, 2 for AIP estimates), sources, transformation,
formula, the record `versions` keys that trace it, limitations, and why it is
NOT_AVAILABLE when it is. Functions: `entry_for(path)` (KeyError = the number
may not be displayed), `coverage(record)` (every quantity and count in a result
record has an entry, every entry has its number, every cited version exists,
and the record's configured Pillar 5 method is `population_weighted_mean_v1`,
the method the registry describes), `problems()` (the registry's own
consistency), `anchor_problems(rows)`. `coverage` of the committed record is
empty. Pillar 5 means are `main`; medians are `details` (tested).

**Pillar 4 reference anchors** (`src/civicalign/ideology/anchors.py`, table
`data/ideology/reference_anchors.jsonl`, key `anchor_id`). Chosen by the user on
2026-09-25. Exactly three (the code refuses two, four or a duplicate):

| Anchor | nominate_dim1 | Voteview id | Record used | Votes scored |
|---|---|---|---|---|
| Bernie Sanders (`S000033`) | −0.546 | ICPSR 29147 | His Voteview `nominate_dim1`, which reflects his whole congressional voting history: House (Congresses 102–109, 1991–2007) and Senate (110–119, since 2007). Voteview estimates one score for the career. **This must be disclosed in the methodology** (it is, in the registry entry `p4.reference_anchor`). | House 6,910; Senate 5,432 |
| Joe Biden (`B000444`) | −0.314 | ICPSR 14101 | His **Senate voting record** only (Delaware, Congresses 93–111, 1973–2009). **Not his presidency**: Voteview's separate "President" rows (ICPSR 99913, −0.32, estimated from positions a president announced, not votes cast) are excluded. | Senate 10,910 |
| JD Vance (`V000137`) | +0.850 | ICPSR 42304 | His **Senate voting record** (Ohio, Congresses 118–119, 2023–2025); not his vice presidency. A short record, disclosed as less certain. | Senate 512 |

Exact source: Voteview `HSall_members.csv`
(https://voteview.com/static/data/out/members/HSall_members.csv), snapshot
content key / SHA-256 `2c2ac0de7ac8fefb885e047199a5d492e1c23a872f43fdb895f122b116244eab`,
retrieved 2026-09-24T13:40:44Z — the same file and version as the senator
scores. `python -m civicalign.ideology.anchors` reads it only if its bytes match
`data/raw/SNAPSHOT.json` (else "ANCHORS REFUSED"). The anchor is the Voteview id
on the person's Senate rows; its value is `nominate_dim1` and must be identical
on every House and Senate row of that id, else the anchor is refused (never
averaged). President rows are never read. Each record stores the display name,
the label (`record_basis`), Voteview id and name, score column, value, Congress
ranges and votes per chamber, `use`, and the usual source fields.

**The anchors are visual references only and never affect calculations.** No
calculation module (`pillars`, `compute`, `inputs`, `national`, `bridge`,
`store`, `records`, `ingest`, `result`) imports `anchors` or `methodology`;
`compute` never reads `reference_anchors`; the result key is unchanged
(`5f42ca01…`) with or without the anchors, and changing an anchor's value leaves
every result identical (all tested). Sanders is also a seated senator and so
appears among the 100 senators in his own right; his anchor is the same number
(tested).

---

### Step 4 parts 2–3 — page builder and the three views (`build_pages.py`, `demo/next/`) — STEP 4 IS COMPLETE

**Where it is (updated by Step 5A).** Step 4 built the frontend in `demo/next/`;
Step 5A moved it to the published files `demo/senator-check.html` and
`demo/methodology.html` (see "Step 5A" below). It is still **not live**: the
branch is not pushed.

**Builder** (`src/civicalign/build_pages.py`;
`PYTHONPATH=src python -m civicalign.build_pages [--out DIR] [--check]`). Reads
only the latest saved result record (checked against its index hash), the
methodology registry, and the three saved anchors (`anchors.current()`); it
never recalculates and imports no Engine A or old-path module. It refuses to
build if `methodology.problems()`, `coverage(record)` or `anchor_problems` report
anything, i.e. a number without a registry entry stops the build. Every number
is embedded as `{value, display, status, reason, units, registry id, path}`;
display = the registry's decimals, rounded half-up from the stored decimal text,
true minus sign, `+` only on differences. Templates:
`demo/templates/senator-check.template.html` (marker `<!--DATA-->`) and
`demo/templates/methodology.template.html` (marker `<!--METHODOLOGY-->`). The
pages link `../civicalign.css`, so preview them through a local server (e.g.
`python -m http.server 8765 --directory demo`, then
http://localhost:8765/next/senator-check.html), not straight from disk.

**Every displayed number is connected to methodology.** In the page, numbers
are rendered only through one JS function, `num()`, which throws if a number has
no registry entry; each number is a button that opens a panel with its raw
source, transformation, formula, versions from this build, limitations and a
link to `methodology.html#<entry id>`. Every NOT_AVAILABLE value shows "Not
available", a "Why?" button, and the registry's reason inline (the record's
exact reason in the panel). `methodology.html` has one linkable section per
registry entry (19), the anchor table, and the binding rules.

**The three views**
- **Senator / State (Pillar 4).** State picker; one card per senator with their
  score and a −1 to +1 Voteview scale ("more liberal voting" / "more
  conservative voting"). **Sanders, Biden and Vance are shown as visual
  reference anchors only** (ticks above the line, labels staggered so they
  never overlap; the senator's dot below). A separate card shows the state
  public's AIP estimate with its standard error and survey period, labelled as
  a different measurement system; "state public on the senator scale" and
  "distance" show as not available with the reason. A fold-out lists the three
  anchors with their labels (Biden and Vance: "Senate voting record … not his
  presidency / vice presidency"; Sanders: House and Senate career) and their
  limitations. Anchors never appear in Pillars 5 or 6 (tested).
- **Senate / Nation (Pillar 5).** Pillar 5 now includes the **approved
  plain-language card** (wording approved by the user on 2026-09-25, commit
  `6eb2969`), titled "Counting states vs. weighting by population", marked
  "candidate method, not final". Under "Senate average" it shows the main
  numbers as three tiles:
  - Each senator counted equally: **0.120**
  - Population-weighted: **0.083**
  - Difference: **+0.037**

  Then the approved explanation: every state gets two senators regardless of
  population; normally each senator counts equally; weighted by population the
  average changes from 0.120 to 0.083; that is a difference of +0.037, and "in
  plain terms, population weighting moves the Senate average slightly toward
  the liberal side of Voteview's −1 to +1 voting scale" — true for the current
  data. **The direction word changes automatically if the sign changes**
  (`side = difference > 0 ? 'liberal' : 'conservative'`; a zero difference says
  the average does not move). The word "slightly" is fixed text chosen for the
  current +0.037; revisit it if a future difference is much larger. A "What
  does this mean?" fold-out explains that population weighting gives senators
  from larger states more weight and senators from smaller states less (the two
  senators from a state split its weight evenly), and says clearly that this
  describes Senate voting records and state populations only and **does not
  tell us which laws passed, what voters believe, or why Congress made a
  decision**; the method **is still a CivicAlign candidate method, not a final
  scientific standard**. All numbers in the card are `num()` buttons that open
  their methodology. Below it, the existing scale chart (labels "Counted
  equally" / "Population-weighted"; the markers nearly overlap because the gap
  is small, and the full −1 to +1 scale is kept rather than zoomed). The old
  takeaway sentence and side note were removed as duplicates. National public
  centre and Senate–public gap: not available, with reasons. Medians (0.320,
  −0.216, +0.536) only inside the "Medians (secondary comparison)" fold-out
  (tested). **No calculations changed and no bill classifications were
  added.** The wording is locked by `test_pillar5_plain_language_card`.
- **Committees (Pillar 6).** Preserves the old committee UI (picker, `.cm` card,
  name header, member counts, scale with a "Senate median" mark and a "This
  committee" dot, "More about this committee" fold-out) but shows **only the
  committee ideology metrics**: committee median, Senate median, committee −
  Senate median, national centre (not available), committee − public (not
  available), members listed, members with a score. **Bill flow and the Yes/No
  split are removed.** The committee dot is neutral grey, not red/blue.

**What the page does not have (tested):** no 0–100 scale, no political judgment
labels, no Engine A recent-vote content, no bill scorecard, and no bill
classification yet.

**Committee names** are temporarily from a fixed list of official names in
`build_pages.COMMITTEE_NAMES`, shown beside the official code, and the page says
they are not yet from a versioned source. **Step 5 must move them to the
official congress-legislators `committees-current` feed.**

Senator names are Voteview's names formatted for reading (e.g. "Mitch
McConnell", "Bernard Sanders" style formal first names), except that an anchor's
own senator uses the anchor's display name ("Bernie Sanders").

**Checked in the browser pane at desktop and phone width (375 px)**: all three
views and the methodology page render, no horizontal scroll, no console errors,
and every number on screen (31 in the checked state) opens its methodology.

### Step 5A — published pages, official committee names, Pillar 1 off the old page — STEP 5A IS COMPLETE (`1901202`)

- **`demo/senator-check.html` and `demo/methodology.html` are now generated by
  the new builder** (`python -m civicalign.build_pages`; `--check` compares).
  The templates moved to `src/civicalign/templates/` (the site publishes all of
  `demo/`, so unfilled templates must not live there); the stylesheet link is
  now `civicalign.css`. **`demo/next/` is retired** (deleted). The published
  page equals the approved Step 4 preview except the stylesheet path and one
  line in the committee fold-out (the old "names are not yet from a versioned
  source" note became the official name and its source). All numbers, names
  and the approved Pillar 5 wording are identical.
- **Committee names now come from the official congress-legislators
  `committees-current.json`**
  (https://unitedstates.github.io/congress-legislators/committees-current.json).
  New source "committee names" in `agents/sources.py`; it was added to the
  accepted snapshot on its own with `python -m civicalign.agents --add "committee
  names"` (`agents.base.add_source`: refuses a source the snapshot already has
  or an unaccepted snapshot; nothing else was refetched, so no other input
  changed; retrieved 2026-09-26T00:30:06Z, SHA-256 `640ab5c2…34ec`). New
  versioned table `committee_names` (key `committee_id`: `official_name`,
  `display_name` = the official name without "Senate Committee on (the)", plus
  source fields; the validator enforces the derivation; a name of any other
  form is refused at ingest). `ingest.run` now also writes it (16 standing
  committees). The builder's fixed name list is gone; a committee code with no
  official name stops the build.
- **Pillar 1 tests no longer depend on the old senator-check page.**
  `test_binding` and `test_context` call the new `supervisor.pillar1_checks()`
  (the same `_binding_checks` and `_context_checks`, same inputs and condition,
  no page, no pipeline report); `test_evaluation` checks Pillar 1's own
  floor-vote output (`pipeline.run(...).floor_votes` carry no generated
  summary). No Pillar 1 logic changed; 97/97 Pillar 1 tests pass.
- **The Pillars 4–6 result record did not change**: key `5f42ca01…`, compute
  plan "unchanged", `compute --verify` passes. Committee names and anchors are
  not calculation inputs (tested).
- **Current focused tests pass**: 39 page tests, 71 Engine B tests, 97 Pillar 1
  tests (`test_binding`, `test_context`, `test_evaluation`).
- **Full suite: 321 passed, 122 failed.** All 122 failures are in the six old
  Pillars 4–6 test files (`test_published_pages`, `test_perspective`,
  `test_peers`, `test_supervisor`, `test_update_chain`, `test_whitepaper`),
  which check the old page that is no longer published; with the Step 5A
  changes set aside those same files fail only the 9 known tests. **Step 5B
  will delete or rewrite them.** None is a Pillar 1 test.
- **Do not run the old builder or old automation before Step 5B is complete**:
  `python -m civicalign.build_demo` would overwrite the new page with the old
  one, and `scripts/update.sh`, the GitHub workflow and the old supervisor
  `main` expect the old page and would fail.
- The page still carries "Local preview build of the rebuilt Pillars 4–6. Not
  published." — true until publishing; remove it in Step 6.

### Step 5B — old Pillars 4–6 path removed, independent supervisor — STEP 5B IS COMPLETE (`a229172`)

- **Old Pillars 4–6 modules and old tests were removed.** Modules:
  `alignment`, `chamber`, `committees`, `space`, `uncertainty`, `peers`,
  `representation`, `gatekeeping`, `output_ideology`, `landmarks`, `export`,
  `whitepaper`, `build_demo`, `sources/state_prefs`, `sources/elections`, and
  `demo/methodology.template.html`; plus five helpers only they used
  (`population.load_populations`, `rosters.majority_party`/`find_chair`,
  `voteview.roll_calls_cast`, `billflow.load_referrals`/`BillReferral`) and four
  unused settings (`cloture_threshold`, `electorate`, `state_source`,
  `ccd_noise_floor`, plus the `elections_csv` path). Tests: `test_published_pages`,
  `test_perspective`, `test_peers`, `test_whitepaper`, `test_math`,
  `test_uncertainty`, `test_representation`, `test_independent`. Nothing Pillar 1
  needs was removed (checked with an import map).
- **`pipeline.py`** now only builds Pillar 1's floor-vote evidence (receipts and
  the recent floor votes). **Pillar 1 output is unchanged**: scores, receipts,
  floor votes and both Pillar 1 check results fingerprinted identical before
  and after. `cli.py` (`python -m civicalign`) prints the saved Pillars 4–6
  record with the page's rounding (`--json` for the record).
- **The new supervisor** (`agents/supervisor.py`; `python -m
  civicalign.agents.supervisor`; `checks()` = `engine_b_checks()` +
  `pillar1_checks()`) **independently verifies Pillars 4–6 from the raw source
  files** with its own readers (it imports neither `ideology.pillars` nor
  `ideology.inputs`): every stored senator `nominate_dim1` and every seated
  senator's score; every state public estimate and SE; Pillar 5 Senate mean,
  population-weighted mean and difference, and the median details; every
  committee median and committee − Senate drift (and member counts); the three
  anchors against Voteview (one Senate id, one career score) and only in Pillar 4
  on the page; committee names against `committees-current.json`, stored and on
  the page; no distance while the bridge is NONE, no Senate–public gap and no
  committee–public drift while the national estimate is unresolved (record and
  page); every displayed number has a registry entry and equals the record with
  its rounding; every entry on the page and in the methodology page; every table
  valid and hash-chained, the result index intact and current, stored records
  append-only against the last commit (`git show HEAD:`), and the published
  pages equal the builder's output. 31 checks (29 Engine B + 2 Pillar 1), all
  confirmed. The Pillar 1 checks were copied verbatim.
- Tests: new `test_supervisor.py` (every sabotage caught; Pillar 1 sabotage
  tests unchanged); `test_update_chain.py` rewritten (snapshot, `add_source`,
  workflow gates); `test_floor_votes.py` and `test_regressions.py` trimmed to
  Pillar 1 and the Voteview/roster regressions; 9 page guardrails carried from
  the deleted page tests into `test_pages.py`.
- **Current test status: 275 passed, 0 failed, 4 expected-fail markers**
  (strict xfail, so each turns into a failure once fixed and must be removed).
  The 4 markers are only for: the GitHub workflow still using the deleted
  builder/tests; `scripts/update.sh` still using them; `scripts/build_demo.sh`
  still using them (Step 5C); README/METHODOLOGY still naming retired files
  (docs step).
- **Do not run the old automation** (`.github/workflows/update.yml`,
  `scripts/update.sh`, `scripts/build_demo.sh`) **until Step 5C is complete.**
- **The current Pillars 4–6 result values did not change** (record
  `5f42ca01…`, `compute --verify` passes, pages current).

## 4. Current real numbers (record `5f42ca01…`, nominate_dim1, 100 active senators)

**Pillar 5 — main comparison (PRIMARY method `population_weighted_mean_v1`)**

| Quantity | Value |
|---|---|
| Plain Senate mean | 0.11971 |
| Population-weighted Senate mean | 0.08296 |
| Population weighting difference (plain − weighted) | +0.03675 |

**Pillar 5 — details only (SECONDARY method `population_weighted_median_v1`)**

| Quantity | Value |
|---|---|
| Plain Senate median | 0.3195 |
| Population-weighted Senate median | −0.2160 |
| Median difference (plain − weighted) | +0.5355 |

Why the median is only secondary: senators with negative scores are 47 of 100
but represent 53.5% of the population, so the weighted median jumps across the
empty stretch between the two parties (largest gap between neighbouring
senators: −0.170 to +0.124) and lands on Shaheen/Warner at −0.216. The mean
moves smoothly. National public and chamber–public gap: NOT_AVAILABLE.

**Pillar 6** (committee median; minus Senate median 0.3195; public drift NOT_AVAILABLE)

| Committee | Members | Median | Drift |
|---|---|---|---|
| SSGA | 15 | 0.536 | +0.2165 |
| SSFR | 22 | 0.4495 | +0.130 |
| SSSB | 19 | 0.444 | +0.1245 |
| SSVA | 19 | 0.387 | +0.0675 |
| SSBK | 24 | 0.3705 | +0.051 |
| SSAF, SSFI, SSJU | 23, 27, 21 | 0.362 | +0.0425 |
| SSAS | 27 | 0.354 | +0.0345 |
| SSCM | 28 | 0.3315 | +0.012 |
| SSEG | 20 | 0.3035 | −0.016 |
| SSRA | 17 | 0.285 | −0.0345 |
| SSHR | 23 | 0.124 | −0.1955 |
| SSBU | 20 | 0.073 | −0.2465 |
| SSEV | 18 | 0.0065 | −0.313 |
| SSAP | 28 | −0.046 | −0.3655 |

Known and accepted: SSAP, SSBU and SSEV have even memberships whose two middle
members sit on opposite sides of the party gap, so their medians fall where no
member sits. The user reviewed this and said the committee median behaviour
should not change.

**Pillar 4**: 100 senators, each with nominate_dim1 and their state's AIP 2020
estimate and standard error (example: Murkowski 0.204 Voteview; Alaska 0.176
AIP units). Distance NOT_AVAILABLE for all.

---

## 5. Methodology decisions (binding)

1. Never independently rescale public-ideology estimates and Voteview scores and
   present them as one scale. They are never compared directly.
2. No senator-to-state distance until a valid bridge exists (active bridge is
   `none-v0`, status NONE).
3. No national-public gap (Pillar 5) or committee-to-public drift (Pillar 6)
   until a national public estimate is defined AND a bridge exists.
4. `population_weighted_mean_v1` is the primary Pillar 5 method. The weighted
   median is retained only as a secondary comparison, shown only in
   methodology/details. Both stay labelled candidate, not final.
5. Committee drift is committee median − Senate median. Do not change it.
6. `nominate_dim1` is the default score; `nokken_poole_dim1` is stored only.
7. No arbitrary 0–100 representation score and no 0–100 display of any score.
8. No politically evaluative labels (good/bad, aligned/misaligned as a grade,
   extreme, moderate, biased, fringe, representative score), no rankings of
   politicians, and no causal claims (gatekeeping, obstruction, why a bill failed).
9. Historical records must remain reproducible: inputs and results are
   append-only and versioned; nothing old is overwritten or deleted.
10. Committee membership dates are observed dates, labelled as such.
11. Fixtures live only in `tests/fixtures/ideology/` (FIXTURE names, fake ids,
    non-existent states ZZ/ZY; README there) and never reach `data/ideology/`.
12. Pillar 4 has exactly three reference anchors — Sanders, Biden (Senate
    record), Vance (Senate record) — with their real Voteview `nominate_dim1`.
    They are visual references only and never enter any calculation. Biden and
    Vance are labelled as their Senate voting records; Sanders's score covers
    his House and Senate service, and the methodology must say so.
13. No number is displayed without a methodology registry entry.

Retired and not to be revived (their code was removed in Step 5B): the caucus-group peer comparison (`peers.py`), seats vs. nation
(`representation.py`, including the retired regression used for diagnostics
only), committee bill flow and Yes/No-split analysis (`gatekeeping.py`,
`output_ideology.py`), `landmarks.py`, and the shared 0–100 display. Also
retired long ago and never to return: senator-minus-voter subtraction,
alignment scores, defiance/betrayal language, politician rankings.

---

## 6. Test status

Run: `./.venv/bin/python -m pytest -q` (Python 3.14 venv; CI uses 3.12).

**After Step 5B: 275 passed, 0 failed, 4 expected-fail markers.**
- Engine B (71): `test_ideology_records.py` (incl. committee names),
  `test_ideology_pillars.py`, `test_ideology_incremental.py`,
  `test_ideology_methodology.py`.
- Page (47): `test_pages.py` — every number has methodology and the right
  display; approved Pillar 5 wording; published pages are the builder's output;
  official committee names; no fixed name map; Pillar 1 tests independent of the
  page; results unchanged; guardrails (accessibility, escaping, three views,
  sources, dates, separate scales, no ordering by score, themes, retired code gone).
- Supervisor (21): `test_supervisor.py`.
- Pillar 1 (103): `test_binding.py`, `test_context.py`, `test_evaluation.py`,
  `test_floor_votes.py`.
- Snapshot, regressions and docs (33 + 4 xfail): `test_update_chain.py`,
  `test_regressions.py`, `test_readme.py`, `test_docs.py`.

Expected-fail markers (strict): `test_update_chain.py::test_every_module_the_update_runs_exists`
for the workflow, `update.sh` and `build_demo.sh` (Step 5C), and
`test_readme.py::test_every_code_file_the_docs_name_exists` (docs step).

History: before Step 5A the full suite was 425 passed, 9 failed (old page,
report and whitepaper against newer bill archives); after Step 5A, 321 passed,
122 failed (all in the six old test files, removed in Step 5B).

---

## 7. Not built yet

- Publishing the new page live (Step 6; the files in `demo/` are switched but not pushed)
- **Anchor refresh in automation** (Step 5C): `python -m civicalign.ideology.anchors`
  is not yet in `update.yml`/`scripts/update.sh`.
- A valid public-to-legislator bridge
- A national public ideology measure (definition and bridge)
- Deterministic bill ideology / legislative outcome classification
- GitHub workflow and scripts on the new pipeline (daily schedule, ingest/compute steps) (Step 5C)
- README / METHODOLOGY rewrite and `docs/ENGINE_B_DATA_FLOW.md` (docs step)
- Deployment (nothing is published; the live site still runs the old product)

---

## 8. User feedback and UX direction (the next major phase)

- **Pillar 4** must be understandable to ordinary users by showing
  recognisable political figures as reference points on the same scale.
  DONE (data): the user chose Sanders, Biden (Senate record), Vance (Senate
  record); see Step 4 part 1. Never invent proxy scores for anyone.
- **Pillar 5** must explain in plain language what the Senate numbers mean in
  the real world, not just show abstract coordinates. DONE: approved card
  (`6eb2969`); see section 3. No legislative-outcome claims until the user asks.
- **Pillar 6**: the user likes the existing committee UI; largely preserve its
  design while switching it to the new metrics (drop the bill-flow and
  Yes/No-split parts, which are retired). DONE in `demo/next/` (Step 4).
- **Future bill ideology classification** must be deterministic and must not
  rely on an LLM guessing. A sponsor's ideology alone must not be treated as
  the bill's ideology without a clear, documented methodology.
- Every displayed number needs a methodology path: raw source, transformation,
  formula, version, limitations. Label provisional things provisional; say why
  anything is NOT_AVAILABLE.

---

## 9. Next step: Step 5C only

Step 5B is complete (`a229172`; section 3). The next task is **Step 5C: the
automation and scripts on the new Engine B pipeline** — `update.yml` daily in the
order fetch → verify → ingest → bridge → anchors → compute → build pages → tests
→ supervisor → commit; `scripts/update.sh` the same; `scripts/build_demo.sh`
calls the new builder or is removed; the unused election-results fetch removed
if nothing depends on it; the three automation expected-fail markers become
passing tests. Not in 5C: README/METHODOLOGY (docs step), UI or calculation
changes.

The Pillar 5 plain-language card is done; do not change its wording without the
user. Review is local only; do not push.

Remaining approved plan after Step 4:
- **Step 5**: remove the old path (`peers.py`, `representation.py`,
  `gatekeeping.py`, `output_ideology.py`, `landmarks.py`, `uncertainty.py`,
  `alignment.py`, `chamber.py`, `committees.py`, `space.py`, `export.py`,
  `whitepaper.py`, `sources/state_prefs.py` — whose AIP class wrongly claims
  `is_bridged = True`); reduce `pipeline.py` to what Engine A's `receipts.py`
  needs; rewrite `cli.py`; rewrite the Engine B parts of
  `agents/supervisor.py` (independent recount of every Engine B number, bridge
  and national gating, methodology coverage, store integrity; keep all Pillar 1
  checks); add the `committees-current` source; update
  `update.yml`/`scripts/update.sh` (daily; ingest → bridge → **anchors** → compute →
  rebuild → tests → supervisor → commit incl. `data/ideology/`; keep
  rebuild-before-tests; the supervisor should also check the anchors match the
  snapshot's Voteview file);
  delete/replace the old tests (`test_peers`, `test_perspective`,
  `test_published_pages`, `test_representation`, `test_uncertainty`,
  `test_math`, `test_independent`, `test_whitepaper`; adjust `test_floor_votes`,
  `test_regressions`, `test_supervisor`, `test_update_chain`, `test_readme`,
  `test_docs`); rewrite README, METHODOLOGY.md, and add `docs/ENGINE_B_DATA_FLOW.md`.
- **Step 6**: run the whole chain locally, commit locally, report. Publishing
  needs the user's explicit approval (then rebase on `origin/main`, regenerate
  pages, push, run the workflow, check live/repo parity).

---

## 10. Engine A status (for reference only; do not modify during Engine B work)

- Pillar 1 Stage 2 (vote bindings) and Stage 2.5 (source packets) are complete
  and run in the weekly workflow (`explain.bind`, `explain.context --check-fresh`).
  54 bindings; 10 packets READY_FOR_GENERATION (the first cohort: S.J.Res.10,
  37, 49, 71, 77, 81, 88, H.J.Res.142, S.2, H.R.4), 27 CRA READY_WITH_LIMITS,
  15 pending, 2 ambiguous. S.2 is READY_FOR_GENERATION + REVIEW_REQUIRED
  (178,614 source characters; decided to keep it in the cohort).
- Stage 3 (Maker/Checker development evaluation) harness is built
  (`src/civicalign/evaluation/`, prompts `evaluation/prompts/maker_v1.txt` and
  `checker_v1.txt` with hashes in `PROMPTS.json`). It runs a sealed `claude`
  CLI (2.1.281, `/opt/homebrew/bin/claude`, the user's own login; Maker
  claude-opus-5, Checker claude-sonnet-5). A run was STOPPED by the user after
  5 of 10 cases passed automated checks; results are local and gitignored. No
  generated explanation is published or on the page.

---

## 11. Commands

```
PYTHONPATH=src ./.venv/bin/python -m civicalign.agents              # fetch the source snapshot (all or nothing)
PYTHONPATH=src ./.venv/bin/python -m civicalign.agents.verify       # check the snapshot
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.ingest     # versioned inputs (--dry-run)
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.bridge     # record the none-v0 bridge
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.anchors    # record the 3 Pillar 4 reference anchors (--dry-run)
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.compute    # versioned results (--verify, --full)
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.inputs     # print current results (not stored)
PYTHONPATH=src ./.venv/bin/python -m civicalign.build_pages        # build demo/senator-check.html and demo/methodology.html (--check)
PYTHONPATH=src ./.venv/bin/python -m civicalign.agents.supervisor   # independent recount of every published number
PYTHONPATH=src ./.venv/bin/python -m civicalign                     # print the saved Pillars 4-6 record
./.venv/bin/python -m pytest -q tests/test_ideology_records.py tests/test_ideology_pillars.py tests/test_ideology_incremental.py tests/test_ideology_methodology.py tests/test_pages.py
```

## 12. Other links

- Claude.ai copy of the OLD page (manual republish, does not update itself):
  https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj
- Shared methodology doc (hand-mirrored, OLD methodology):
  https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3
- Rotate the Congress.gov API key that was once pasted into an old chat; it is
  used nowhere and must never be committed.
