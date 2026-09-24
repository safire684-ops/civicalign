# Project handoff — CivicAlign, Pillars 4–6

Updated 23 September 2026. Scope is **Pillars 4, 5 and 6 only** (math-spec
sections 2–5). Pillars 1–3 and 7 belong to someone else. Everything described
here is published and the repository, the live site and the claude.ai copy are
in step.

## Where things are

- Live site: https://safire684-ops.github.io/civicalign/ (senator page:
  `/senator-check.html`, methodology report: `/methodology.html`)
- Repo: https://github.com/safire684-ops/civicalign (branch `main`; the weekly
  job commits as `civicalign-bot`)
- Claude.ai copy (manual republish, stylesheet inlined, does not update itself):
  https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj (version 31)
- Shared doc (hand-mirrored, methodology only):
  https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3

## The contract, and what moves

**The methodology contract is stable, but the data is dynamic. CivicAlign
rebuilds from current source data every week. Numerical figures, rosters, bill
counts and valid same-scale conclusions are expected to change.** The project is
not frozen.

What never changes without a deliberate decision:

1. **No comparison across the two scales.** A senator's score (Voteview,
   Nokken-Poole) and a state's voter estimate (American Ideology Project) are
   separate measurement systems with no validated bridge. Nothing public, and
   nothing in `src/`, subtracts one from the other, compares them with `<`/`>`,
   tests a senator against the state's uncertainty band, or ranks senators by any
   senator-versus-state figure. Valid comparisons stay inside one system: senator
   vs the expected position for their state (below), senator vs Senate middle,
   committee vs Senate middle, 60-vote point vs Senate middle, state vs national
   voter estimate, seats' vote share vs national vote share.
1b. **The primary senator result is a peer comparison** (`peers.py`): same
   caucus group (Republican caucus; Democratic caucus = Democrats plus the
   Independents whose roster `caucus` field says Democrat; any other party value
   or a missing caucus -> status `unsupported`, never a peer), other states
   only, state two-party presidential share (2016/2020/2024, MIT) within ±4
   points, minimum six peers, conclusion published only if it agrees at ±2, ±3,
   ±4 and ±5. Five statuses: within / outside_liberal / outside_conservative /
   unstable / insufficient. Nothing widens the window; peers are listed by state,
   never ordered by position; no ranking. The page only words the backend status
   (`peerWords` / `peer_words`). The regression (`representation.py`) is kept for
   diagnostics and the methodology's audit, and is not used for any published
   classification (it mostly measured the party split; in competitive states its
   line fell where no senator sits). The survey estimate never enters this.
2. **No bill ideology.** A roll-call dividing line says where senators split, not
   what the bill was. A sponsor's record does not make a bill liberal or
   conservative. The page says both.
3. **No dead bills.** A bill not yet formally reported is "not yet sent forward",
   never buried, killed or dead. The Congress is running.
4. **Thresholds.** Two-side bill-flow comparison only with ≥ 25 bills per sponsor
   group; floor-vote split only with ≥ 7 qualifying votes, tagged "Early signal"
   below 15; a committee is flagged (under "More about this committee") as sitting
   well to one side beyond 0.15 underlying units.
5. **Words follow one rule.** Every same-scale position is described by
   `relWords` (page) / `rel_words` (`build_demo.py`): within 0.05 underlying
   units "near the …", otherwise "on the more liberal/conservative side of
   the …". Words give the direction, the chart shows how far, the number is
   under details. No graded categories ("somewhat", "clearly" were removed
   23 Sept 2026); no "most liberal", "extreme", "moderate", ranks or scores.
6. **Meaning before numbers.** Cards lead with a ruler and a sentence.
   Coordinates appear only under "See details" / "More about …", introduced by
   the scale note ("a position on that line; not a percentage, a vote total, an
   approval rating or a grade") and labelled "display-scale units". Bill-flow
   differences are "percentage points". The two are never mixed. Default views
   carry no academic terms (Voteview, Nokken-Poole, median, standard error,
   cutpoint, cloture and so on live in How it works, the disclosures and the
   report); unfamiliar terms get a tap-to-open "i" hint (`help()` / `HELP`).
7. **The four-view interface** and its accessibility (tabs with roving tabindex,
   tracks hidden from screen readers with a spoken sentence, 44px targets).
8. **Evidence without inference.** Each senator card lists their recorded Yea or
   Nay on the most recent passage votes (block `F`, same votes for every senator,
   newest first, Voteview links). No bill description is generated (`summary`
   stays empty until a verified Pillar 1 source exists) and no claim is made about
   what the state's voters wanted.

All seven are enforced by tests that run in the weekly job.

## What the page shows

- **Header.** "Your senators, in the context of your state" / "See how each
  senator's Senate voting record compares with what we typically see from
  senators representing states that vote like yours." / "A separate survey
  estimate of your state's voters appears further down and is not directly
  compared with the senators." / "Senate data updated: <date> · Voter estimate:
  2020 wave".
- **Your senators (Pillar 4).** Takeaway ("Both Ossoff's and Warnock's voting
  records fall outside the observed range of comparable senators in the
  Democratic caucus, on the more liberal side."), state picker, "YOUR SENATORS — How do
  their voting records compare with senators in the same caucus group from
  states that voted similarly?", "Georgia recent presidential vote used for peer matching: 2016 ·
  2020 · 2024. Both senators are compared with the same pool of other states."
  Then a card per senator: "Compared with 12 senators in the Democratic caucus
  from 7 other states with similar recent presidential voting (i)", SENATE VOTING SCALE with
  the observed peer range bar, the "Peer middle" tick and the senator's dot, the
  decoder ("Bar: lowest to highest peer record · Tick: peer middle · Dot: …"),
  the one sentence from the backend status, "This compares the senator with
  senators in the same caucus group from states with similar recent presidential
  voting. It does not measure whether the senator agrees with the state's
  voters.", the vote
  count, then folds: "How were these peers chosen?" (the rule, the state's three
  shares and the average, peer states with shares, peer senators by state,
  conclusion at each window, the numbers), "Recent votes in this record",
  "Where they sit in the Senate" (demoted Senate-middle ruler). Below the cards:
  "A peer comparison says where a voting record sits among comparable senators.
  It does not say whether a senator represents, agrees with, or matches the
  state's voters." Then the collapsed "Additional voter context" survey fold.
- **The Senate (Pillar 5).** Leads with "How Senate seats represent the country's
  vote": a vote-share ruler (Even split, National vote 49.1% R, Average across
  Senate seats 52.5% R) and "The mix of states represented by Senate seats is 3.4
  percentage points more Republican than the national presidential vote", by
  election under a fold. Then "How the Senate votes": Senate middle and 60-vote
  point, "Why 60?", and the state survey estimates on their own scale; "Where
  familiar senators sit" (party middles and eight named senators) lives here,
  folded, not on the first view.
- **Committees (Pillar 6).** Legislative flow, then one committee at a time
  against the Senate overall: who sits on it (ruler vs Senate middle); what it has
  sent to the full Senate (flow, sponsor definition, "This describes the sponsor,
  not the ideology of the bill", and "Compared with the Senate overall":
  Senate-wide difference beside this committee's difference, in percentage
  points; the baseline is described without a cause); where the Yes/No split fell on its bills, with the count of qualifying
  votes and "Early signal" / "Not enough data yet".
- **How it works.** Plain questions and answers, including "What does 'expected
  for a state like mine' mean?", "Where do the election results come from?",
  "Why compare Senate seats with the national vote?", "When was this data
  updated?"; then "Show the technical methodology".
- Footer: sources (now eight, including the MIT election file) with publisher,
  link, vintage and retrieval date.

## Pillar 1 (the concrete receipt): Stage 2 built, Stages 3–5 not started

The product target from the original directive stands: turn "Recent votes in
this record" into a verified receipt (what the Senate was deciding, the exact
text before it, what a Yea and a Nay would do, how this senator voted, and the
official sources behind each line). Stage 2 is the deterministic foundation
and is live in the weekly job; **no summary is generated, no model is called,
and the page does not read any of it yet.**

- `sources/senate_votes.py` reads the Senate's own roll-call XML (senate.gov
  LIS, keyless); `sources/billstatus.py` reads a bill's full BILLSTATUS record
  (text versions with GovInfo URLs and dates, actions with recorded-vote
  links, CRS summaries are available but unused). The joint-resolution
  archives (`sjres`, `hjres`) are fetched as non-critical sources.
- `explain/binding.py` — pure rules: kind from the official question only
  (`QUESTION_KINDS`; anything else is OTHER), PASSAGE_AS_AMENDED only when the
  Senate title says "As Amended" and/or the bill's action says "with an
  amendment" and the two agree; text selection (`select_text`): the Senate
  engrossment on the vote date (`es`/`cps`, or `eas` for a House bill passed
  with a Senate amendment) is the measure as passed; otherwise the latest
  pre-vote version by precedence (`pcs > rs > rds > rfs > eh`; Senate-origin
  `pcs > rs > is`); enrolled and public-law texts are never selected; an
  amended measure without an engrossment is TEXT_PENDING for 45 days then
  TEXT_AMBIGUOUS; floor amendments before a vote with no engrossment are
  ambiguous; two engrossments are ambiguous. CRA metadata (`cra_from_title`)
  comes only from the two official title forms; `underlying_rule_source` is
  a future slot and stays null. The receipt scaffold (headings, what Yea and
  Nay mean, next step) is fixed per kind, never generated.
- `explain/bind.py` (`python -m civicalign.explain.bind`, `--offline` to use
  the cache) classifies all Senate roll calls, binds the supported kinds
  (PASSAGE, PASSAGE_AS_AMENDED, JOINT_RESOLUTION_PASSAGE), fetches the Senate
  XML and the selected text into `data/raw/explanations/` (ignored, with a
  MANIFEST of hashes and stamps), verifies identity, date, question, tallies,
  threshold, member votes (LIS id → bioguide from the roster; former members
  by exact last name, first name, state and party against Voteview's member
  file, failing closed on ambiguity), measure id and the bill-status
  recorded-vote link, and writes one tracked JSON per vote under
  `data/explanations/119/` plus `index.json`. A re-run that changes nothing
  writes nothing; a changed source hash or status keeps the old record under
  `history`. Verification statuses: VERIFIED, BOUND_AWAITING_BILLSTATUS,
  FAILED, UNAVAILABLE. `summary_eligible` requires a supported kind, VERIFIED
  and TEXT_BOUND.
- Supervisor: one check re-derives every binding from the cached files with
  its own code (identity, tallies, question, measure, recorded-vote link,
  hashes, selected version exists / not enrolled / not later than three days
  after the vote / reproduced by the rule / stage attribute, eligibility, CRA
  fields from the title, no generated field present).
- Tests: `tests/test_binding.py`.
- Not done: Maker, Checker, evaluation set, any UI change. The Congress.gov
  API is not used. When Stage 3 starts, the model provider, prompt versions
  and iteration counts go into the binding's provenance, and only `verified`
  summaries may reach block `F`.

## How the weekly update works

`.github/workflows/update.yml` (Mondays 11:00 UTC, or "Run workflow"), mirrored
by `scripts/update.sh`. Every step is a gate; a failure fails the Action, commits
nothing, and leaves the previously verified site live.

1. **Fetch as one snapshot** (`python -m civicalign.agents`): all ten critical sources are
   downloaded and validated into staging; if any critical source fails, nothing
   is installed and the run stops. All ten are critical: Voteview members, roll
   calls, votes; congress-legislators roster and committee membership; American
   Ideology Project state estimates; Census populations; Senate and House
   bill-status archives; MIT election results (the state input for Pillar 4 and
   the seat comparison for Pillar 5). Two non-critical sources, the Senate and
   House joint-resolution archives, are fetched for Pillar 1; if they fail the
   previous file stands and the run continues. The binding step
   (`python -m civicalign.explain.bind`) runs after verify. Change detection is by content
   (zip members, not archive timestamps). `data/raw/SNAPSHOT.json` (tracked)
   records per source: URL, file, bytes, SHA-256, content key, changed flag,
   content-changed date, checked date, vintage. `PROVENANCE.tsv` logs content
   changes. On a fresh checkout the raw files are absent; the comparison uses the
   committed snapshot's keys, so re-downloads of identical content are not changes.
2. **Verify** (`python -m civicalign.agents.verify`): 100 seats, ≤ 2 senators per
   state, scored senators and committee members on the current roster, record
   counts sane, no source shrank > 30 %.
3. **Data tests** (`pytest`, excluding the page and whitepaper tests).
4. **Rebuild** (`python -m civicalign.build_demo`): regenerates the page's data
   blocks and `demo/methodology.html` from the template.
5. **Page tests** (`tests/test_published_pages.py`): the public-claim contract.
6. **Supervisor** (`python -m civicalign.agents.supervisor`): separate code
   re-reads the raw files and reproduces 35 figures: scores, middle, 60th vote,
   survey estimates, bill counts, every state's three-cycle two-party share, the
   national shares, the seats-minus-nation figure, the fitted line (own OLS from
   sums; diagnostics only), every senator's peer group, range, status and
   per-window sensitivity with its own loop, the rule itself, every senator's
   vote on the published floor votes; and checks the payload carries no
   cross-scale, ranking or unverified-summary field and lists peers by state.
7. **Commit** only if the pages or the provenance log changed (a check-stamp-only
   snapshot change is discarded). **Publish** only if every step passed.

Roster changes (resignations, appointments, deaths, new members) flow through
the roster join; a senator with fewer than 30 roll calls gets the
"waits until a senator has at least 30 recorded floor votes" card (a display
rule, not a validity claim), never a predecessor's score. The seat de-duplication
guard (104 Voteview rows for 100 seats) is in `sources/voteview.py`.

## Routine tasks

- Refresh the whitepaper's figures after data moves (the job only warns):
  `PYTHONPATH=src python -m civicalign.whitepaper`, then commit `WHITEPAPER.md`.
- Republish the claude.ai copy: inline `demo/civicalign.css` into
  `demo/senator-check.html` in place of the `<link>` tag, point
  `href="methodology.html"` at the live URL, and publish to the artifact URL above.
- Run everything locally: `scripts/update.sh` (uses `.venv` if present).
- Read the figures on the command line: `PYTHONPATH=src python -m civicalign`
  (`--json` for the export; each section is labelled with its scale).

## Code map (Pillars 4–6)

- `src/civicalign/pipeline.py` — `run()` builds the `Report`.
- `peers.py` — the published Pillar 4 rule (`WINDOW`, `MIN_PEERS`, `WINDOWS`,
  `peer_comparisons`, `status_from`). `representation.py` — the retired
  regression (`Fit`, `Representation` with `band` and `zone`), kept for
  diagnostics and the methodology audit, and the Pillar 5 `ChamberLean`;
  `uncertainty.py` — analytic OLS errors, `leverage`, `prediction_band`,
  `studentized`. `receipts.py` — `recent_floor_votes` (fixed neutral rule).
- `alignment.py` — `Positions`: senator score and state estimate side by side,
  nothing derived. `chamber.py` — median, 60th vote, party medians; carries the
  national estimate for the voter chart only. `committees.py`,
  `output_ideology.py`, `gatekeeping.py`, `landmarks.py`, `receipts.py` (the vote
  example still exists in the pipeline and JSON, not on the page).
  `representation.py` — method A, the election-result regression (answers "how
  does this senator compare with the pattern typical of states that vote
  similarly?"), kept separate from the page.
- `build_demo.py` — data blocks `V M X P G` plus `R` (peers: the rule, each
  state's shares, each senator's group, record, peer count/states/low/high/
  median, status, per-window sensitivity, peer senators by state), `E` (seats vs
  nation by election), `F` (recent passage votes with every senator's Yea/Nay);
  report placeholders including `regression_audit`; sources list; wording rules
  (`rel_words`, `peer_words`).
- `agents/` — `base.py` (snapshot), `sources.py` (ten agents with validators and
  vintages), `verify.py`, `supervisor.py`. `whitepaper.py` — figure refresher.
- `explain/` — Pillar 1 Stage 2 (see above); `sources/senate_votes.py`,
  `sources/billstatus.py`.
- Tests: `test_binding.py` (Pillar 1), `test_published_pages.py` (contract: no cross-scale arithmetic G1–G6,
  no bill ideology, no dead bills, twelve UX guarantees, ten presentation
  guarantees, twenty average-voter guarantees V1–V20), `test_perspective.py`
  (the product hierarchy: state-relative primary result, regression not survey
  subtraction, no ranking, backend-derived expectation, shared state input,
  receipts without voter claims, seats-first Senate view, Senate-wide baseline,
  guardrails), `test_update_chain.py`
  (snapshot, gates, provenance),
  `test_supervisor.py`, `test_independent.py` (raw-file recomputation),
  `test_floor_votes.py`, `test_math.py`, `test_regressions.py`,
  `test_representation.py`, `test_uncertainty.py`, `test_whitepaper.py`.
  219 pass as of this handoff; supervisor 34/34; verify 12/12.

## Open items

- The 2024 survey wave does not exist; 2020 is the newest. The page says so.
- The peer rule leaves three senators without a comparison (both Wyoming
  senators; Maine's Republican) and nine with window-dependent conclusions; the
  page says so for each. The retired regression's problems (party split, phantom
  middle) are documented in the report with live figures.
- Pillar 1 bill summaries do not exist in this repo; `FloorVote.summary` is the
  integration point and stays empty. Do not invent summaries.
- Two audits disagree on committee median vs mean; the median is shown and the
  mean is in fine print. Not resolved.
- Voteview publishes no standard errors for senator scores, so only the survey
  side has an uncertainty band.
- The claude.ai copy and the shared doc do not update themselves.
- Rotate the Congress.gov API key that was pasted into chat earlier; it is not
  used anywhere and must never be committed.
- Enter/Space on tabs and circles could not be driven from the browser pane
  (elements are native links and buttons; worth a press on a real keyboard).
- Headless Chrome enforces a 500px minimum viewport; phone screenshots need the
  DevTools-protocol emulation script pattern.

## Decision history, condensed

- Sept 2026, early rounds: Pillars 4–6 built on real data; automation via
  GitHub Actions and Pages; four-view interface; navigation and phone fixes.
- Vote examples: the "state side of a vote" inference was removed, then the
  vote example itself was removed from the senator view (bills are not marked
  on the senators' line).
- Methodology cleanup: scales described as separate; splits are not bill
  ideology; pending not dead; distinct bills vs referrals; the alignment band
  label softened, then the comparison removed altogether.
- 0-to-100 display scale (score × 50 + 50); later, numbers moved under
  details with the scale note and "display-scale units".
- Backend: obsolete cross-scale metrics (gap, score, rank, crosses_over,
  apportionment_skew on the survey scale, cnd, vs_public) deleted, not hidden.
- Weekly chain hardened: all-or-nothing snapshot, verify step, gated publish,
  content-based change detection, provenance with vintage and retrieval dates.
- Presentation: one wording rule, words before numbers, percentage points vs
  display-scale units, no ranking language. 23 Sept: graded words dropped
  (direction only), purpose sentence in the header, "Estimated political
  position of <State> voters", committee questions reworded in plain English.
  Later that day, the average-voter pass: tap-to-open hints for Senate middle,
  national voter estimate, 60-vote point and sent forward; bill flow as three
  steps; a Yes/No-split ruler; How it works as questions and answers; academic
  terms and coordinates moved behind details; no engine change. Then the product
  correction (23 Sept): the state-relative election regression became the primary
  Pillar 4 result (shared reference ruler, typical range, model-driven words,
  actual votes as evidence), the Senate view leads with seats vs nation,
  committees are read against the Senate-wide baseline, blocks R/E/F added and
  supervised. Then the statistical audit (same day) retired the regression
  from the page: block R now carries the peer comparison. Earlier still, the final
  comprehension pass: new header and freshness line, "Your senators" / "Voters in
  <State>" sections, SENATE VOTING SCALE / VOTER ESTIMATE SCALE labels on every
  ruler, the legislative flow, the three-fifths explanation of 60, FAQ reordered
  with "When was this data updated?"; removed the badge, the left/right line, the
  picker fact lines and the duplicate two-senators paragraph.

Reference reports from earlier rounds (Gemini): Pillar 6 dual-metric framework
https://gemini.google.com/share/b75123b297db?skid=4798bd3c-9d90-4f8a-a251-00429acbda75 ;
system audit and execution directives
https://gemini.google.com/share/82bd4fe17a76?skid=e8601a35-0fb0-4b8d-b6a8-f4b2775b7142 .
Later reports asked for cross-scale claims, invented bill positions and
AI-written bill impacts; those were declined and the reasons are in the commit
messages.
