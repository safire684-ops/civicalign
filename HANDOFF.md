# Project handoff — CivicAlign

Rewritten 25 September 2026 for a brand-new chat. Read all of it before doing
anything. The repository and this file are the source of truth; older design
documents, the whitepaper and chat history are not.

---

## 0. Safety rule (read first)

Do NOT restart the project, redesign Steps 1–3, switch away from DW-NOMINATE
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

## 3. Completed work (Engine B, Steps 1–3)

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

---

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

Retired and not to be revived (they are still in the old code path until Step 5
removes them): the caucus-group peer comparison (`peers.py`), seats vs. nation
(`representation.py`, including the retired regression used for diagnostics
only), committee bill flow and Yes/No-split analysis (`gatekeeping.py`,
`output_ideology.py`), `landmarks.py`, and the shared 0–100 display. Also
retired long ago and never to return: senator-minus-voter subtraction,
alignment scores, defiance/betrayal language, politician rankings.

---

## 6. Test status

Run: `./.venv/bin/python -m pytest -q` (Python 3.14 venv; CI uses 3.12).

Engine B (all passing, 51 total):
- `tests/test_ideology_records.py` — 17 (validators, store, ingest from fixtures
  and from the real snapshot, population table, committee events, committed
  tables verify, no Engine A imports).
- `tests/test_ideology_pillars.py` — 20 (bridge NONE; national unresolved;
  weights incl. vacancy; weighted median and weighted mean by hand; Pillar 5
  primary mean and details; Pillars 4 and 6 by hand; config defaults; no 0–100
  anywhere; real values recomputed from the raw files with separate code).
- `tests/test_ideology_incremental.py` — 14 (unchanged / committees_only / full,
  carried = full recompute, write-once, tamper and stale detection).

Full suite: **375 passed, 9 failed.** The 9 failures are EXPECTED:

```
tests/test_perspective.py::test_18_safeguards_remain
tests/test_published_pages.py::test_demo_bill_survival_is_current
tests/test_published_pages.py::test_report_quotes_the_current_bill_figures
tests/test_published_pages.py::test_senate_wide_totals_count_distinct_bills
tests/test_supervisor.py::test_supervisor_confirms_every_figure
tests/test_whitepaper.py::test_party_landmarks_are_current
tests/test_whitepaper.py::test_committee_tables_are_current
tests/test_whitepaper.py::test_chair_gaps_are_current
tests/test_whitepaper.py::test_distinct_bill_counts_are_current
```

They compare the OLD committed page, report and whitepaper (built from the
previous bill-status archives) with the newer archives fetched on 2026-09-25
(e.g. page 5,347 distinct bills vs 5,456 in the fresh data). They belong to the
old bill-flow / whitepaper path that Step 5 removes. They fail identically
without any Engine B change. **Do not fix them before the planned removal**; do
not rebuild the old page to silence them.

---

## 7. Not built yet

- UI rewrite (the three views) and the page builder
- Methodology registry and methodology UI
- Famous-person reference anchors for Pillar 4
- A valid public-to-legislator bridge
- A national public ideology measure (definition and bridge)
- An understandable real-world explanation of the Pillar 5 numbers
- Deterministic bill ideology / legislative outcome classification
- Final GitHub workflow changes (daily schedule, ingest/compute steps)
- Final removal of the old Pillars 4–6 path, supervisor rewrite, docs rewrite
- Committee names from an official source (currently only codes; the plan adds
  the congress-legislators `committees-current` feed)
- Deployment (nothing is published; the live site still runs the old product)

---

## 8. User feedback and UX direction (the next major phase)

- **Pillar 4** must be understandable to ordinary users by showing 2–3
  recognisable political figures as reference points on the same scale. Use
  only figures with defensible, comparable congressional voting data (e.g.
  Voteview scores); never invent proxy scores for anyone.
- **Pillar 5** must explain in plain language what the Senate numbers mean in
  the real world, not just show abstract coordinates.
- **Pillar 6**: the user likes the existing committee UI; largely preserve its
  design while switching it to the new metrics (drop the bill-flow and
  Yes/No-split parts, which are retired).
- **Future bill ideology classification** must be deterministic and must not
  rely on an LLM guessing. A sponsor's ideology alone must not be treated as
  the bill's ideology without a clear, documented methodology.
- Every displayed number needs a methodology path: raw source, transformation,
  formula, version, limitations. Label provisional things provisional; say why
  anything is NOT_AVAILABLE.

---

## 9. Next step: Step 4 only

First read this file and inspect the branch (`git log`, `src/civicalign/ideology/`,
`data/ideology/`, the tests). Then, and only then, build Step 4:

1. `src/civicalign/ideology/methodology.py` — a registry with one entry per
   displayed quantity: raw source, transformation, formula, versions,
   limitations. Page and tests read it; no number may appear without an entry.
2. Page builder — rewrite `src/civicalign/build_demo.py` to read the latest
   result record (`compute.load_record` / `index`) plus the registry and write
   `demo/senator-check.html` (from a new `demo/senator-check.template.html`) and
   `demo/methodology.html` (from a rewritten `demo/methodology.template.html`).
3. Frontend structure — exactly three views: Senator / State (Pillar 4),
   Senate / Nation (Pillar 5: plain mean vs population-weighted mean and the
   difference as the main comparison; medians only in details), Committee /
   Senate / Nation (Pillar 6: selected committee, committee median, Senate
   median, national centre (not available), both drifts, member count). A
   methodology panel for every number. Numbers in native units, honestly
   rounded; each NOT_AVAILABLE item shows its reason. No 0–100, no evaluative
   labels, no Engine A "recent votes" block.

Ask the user before building the famous-person anchors or the Pillar 5
real-world explanation text (section 8): they are the next phase and need their
input. Review is local only (open `demo/senator-check.html`); do not push.

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
  `update.yml`/`scripts/update.sh` (daily; ingest → bridge → compute → rebuild →
  tests → supervisor → commit incl. `data/ideology/`; keep rebuild-before-tests);
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
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.compute    # versioned results (--verify, --full)
PYTHONPATH=src ./.venv/bin/python -m civicalign.ideology.inputs     # print current results (not stored)
./.venv/bin/python -m pytest -q tests/test_ideology_records.py tests/test_ideology_pillars.py tests/test_ideology_incremental.py
```

## 12. Other links

- Claude.ai copy of the OLD page (manual republish, does not update itself):
  https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj
- Shared methodology doc (hand-mirrored, OLD methodology):
  https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3
- Rotate the Congress.gov API key that was once pasted into an old chat; it is
  used nowhere and must never be committed.
