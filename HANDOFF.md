# Project handoff — CivicAlign, Pillars 4–6

Updated 22 September 2026. Scope is **Pillars 4, 5 and 6 only** (math-spec
sections 2–5). Pillars 1–3 and 7 belong to someone else.

## The contract, and what moves

**The methodology contract is stable, but the data is dynamic. CivicAlign
rebuilds from current source data every week. Numerical figures, rosters, bill
counts and valid same-scale conclusions are expected to change.** The project is
not frozen. What never changes without a deliberate decision: no comparison across
the Voteview and survey scales, no bill ideology from cutpoints or sponsors, no
"dead" bills, the sample-size thresholds, and the four-view interface.

Weekly chain (`.github/workflows/update.yml`, mirrored by `scripts/update.sh`):
fetch every source as one snapshot (all critical sources succeed or nothing is
installed and the job fails) → verify roster, join keys and record counts → data
tests → rebuild → public-claim tests → supervisor → commit only if the pages or
provenance changed → publish only if every gate passed. A failure leaves the
previously verified site live. `data/raw/SNAPSHOT.json` records each source's
URL, bytes, hash, content key, whether its content changed, when it last changed
and when it was last checked; `PROVENANCE.tsv` logs each content change.

## Status in one line

Weekly chain hardened (23 September 2026, published): fetch is all-or-nothing
(`agents/base.py: run_snapshot`), a pre-build `agents/verify.py` checks the
roster, join keys and record counts, the workflow gates every step and publishes
only on full success, `data/raw/SNAPSHOT.json` records each source (URL, bytes,
hash, content key, changed?, content-changed date, checked date, vintage), the
page shows "Data updated <date>" and, per source, retrieval date and vintage
separately, and zip archives are compared by content so daily republishing does
not count as change. `python -m civicalign.whitepaper` refreshes the whitepaper's
figures in one command. Tests: 143 pass; supervisor 18/18.

Backend cleanup (23 September 2026, published): the obsolete cross-scale
metrics were deleted, not hidden. `alignment.py` now only carries `Positions`
(senator Voteview score and state survey estimate side by side); removed:
abs_gap, signed_gap, spec_score, rank, crosses_over, rank_all;
`ChamberStats.apportionment_skew` (median minus national estimate);
`CommitteeStats.cnd`/`cnd_mean`; `OutputIdeology.vs_public`. The CLI prints the
two scales separately with no distance; the JSON export gains
`senator_positions` and `state_voter_estimates` (each labelled with its own
scale) and lost cnd_median, cnd_mean, vs_public and crosses_over; the supervisor
no longer verifies a "Senate-public gap". Nothing in src/ subtracts a Voteview
coordinate from a survey coordinate. The election-result regression (method A,
`representation.py`, JSON `state_alignment`) stays, documented as answering a
different question. Tests: 133 pass; supervisor 18/18.

Two measures, shown separately (22 September 2026, published): the page no
longer compares a senator's Voteview score with the state's survey estimate in
any way, not even the sign. Each senator card shows the voting pattern against
the Senate middle on the senators' scale ("More liberal than the Senate middle
(43 points)"); one state card shows the voter estimate against the national
estimate on the voters' scale ("Estimated slightly conservative on the voter
measure"); one line says the two use different methods and are shown separately.
The Senate view shows the Senate middle and 60-vote point on one line and the
national estimate (with every state as a faint tick) on another, not compared.
Public payload carries no cross-scale fields (gap, score, rank, crosses, dir,
vsUS, vsState, nRightOfPublic, medianGap, skew, dUS, cndMedian, cndMean, C block
gone); the supervisor and six new tests enforce that no public code subtracts,
compares, band-tests or ranks across the two scales. Headline: "See your
senator's voting pattern and your state's voter estimate". Report and README
state that a direct senator-versus-state measure needs a validated bridge that
CivicAlign does not currently have; method A (regression) stays separate. The
pipeline still computes the old alignment diagnostics privately (CLI, JSON
export, supervisor) but nothing public uses them. Tests: 138 pass.

No cross-scale arithmetic (22 September 2026, published): nothing a reader sees
subtracts a Voteview figure from an American Ideology Project estimate. The card
says which side of the state estimate the senator's pattern falls on, or that it
falls within the estimated range; no "points apart", no typical-gap ratios, no
named-senator distances, no widest-gap ranks, no "one of the most liberal". The
Senate view says which side of the national estimate the Senate's pattern falls
on; the gap figure and "senators right of the country" count are gone. Committee
versus public columns removed from the report and whitepaper. Senator-to-senator
and committee-to-Senate figures (one scale) remain in points. Headline is now
"How does your senator's voting pattern compare with your state?". A regression
test bans the cross-scale phrases and expressions. Tests: 132 pass.

Plain-language redesign (22 September 2026, published): each view answers one
question with one sentence, one simple picture, one short caveat and a "See
details" fold. The senator card shows only the state's estimated range, the
state's mark and the senator's dot; party middles, the Senate's middle, the
country and familiar senators moved into "Where familiar senators sit" and
See details. Verdicts are words ("well to the left of Georgia's voters"), the
visible distance is rounded to 5 and marked approximate, the survey vintage
(2020 wave) is on the first screen, the Senate view is two dots and a sentence
with "Why does this happen?" / "See all 100 senators" / "The numbers" folded,
and the committee view answers three questions (who is on it, what has it sent
forward, where senators divided on its bills) with "Limited data" / "Early
signal" tags below 25 bills per side or 15 floor votes. README now separates the
regression method (A) from the live survey comparison (B). Sources are a neat
linked list with download dates; all eight were re-fetched live and matched the
local files (the bill archive differs only because GovInfo republishes daily).
Tests: 131 pass, including the brief's twelve guarantees.

Reader scale is now 0 to 100 (22 September 2026, published): every displayed
position is score × 50 + 50 and every distance × 50; the data blocks and the
pipeline stay on −1 to +1, and the arithmetic section shows both. The report shows
0–100 with raw values beside the worked example.

Supervisor agent added (`src/civicalign/agents/supervisor.py`, step 5/5 in
`scripts/update.sh` and the workflow): separate code re-reads the raw files and
recomputes 19 published figures (scores, medians, 60th vote, state estimates,
national public, every committee's counts, distinct-bill totals, page blocks,
party middles, anchors, summary counts). Any disagreement fails the update.
`tests/test_supervisor.py` also proves it catches a sabotaged page figure.

Accuracy fixes found in review: referrals of Senate bills to House committees
(7 rows) no longer count toward Senate totals; every committee's counts are shown
with the two-side comparison withheld below 25 per side; the page states exactly
what "sent on" counts (formally reported; markups not yet reported and House bills
excluded) with the data date; two causal phrasings softened (gatekeeper warning,
"structural veto"); the report's source list now names all six datasets and no
longer says "nothing is estimated by us".

Five methodology concerns fixed in wording and counts (22 September 2026,
published): (1) the page and report no longer claim the survey and senator scales
are the same; they say the two rulers were built separately and every distance is a
rough comparison; (2) committee "output" is described as where the Senate split on
its bills, explicitly not bill ideology; (3) bills not yet reported are "pending" or
"not yet sent on", never buried, dead or survivors; (4) Senate-wide totals count
distinct bills (5,333) with referrals (5,368) named separately, via new Report fields
`bills_referred_unique` / `bills_reported_unique`; (5) the alignment badge is "Too
close to tell apart" with the band described as one standard error and "not the same
as agreement". The 1-SE threshold itself is unchanged.

Earlier the same day (published): the senator view shows **no
bills**. Each card explains the gap in plain terms from the page's own data: how
far it is (share of the scale, the distance between two familiar senators, and
against the typical senator's gap), where the senator sits against their party's
middle and the other 99 senators, where the state sits against the public and the
other states, and what each number is made of. The track and the "Explore the
scale" ruler carry landmarks (middle Democrat, middle Republican, Senate middle,
public, familiar senators). The page states it cannot say which issues make up
the difference and never guesses.

Everything below is **published** as of 22 September 2026: the four-view layout,
the vote-example correction and the presentation safeguards are on the live site,
`origin/main` is at the same commit, and the claude.ai copy (version 12) was
rebuilt from the same page with the stylesheet inlined. The weekly workflow ran
green (`update` and `publish` both succeeded) and only re-dated the report.

## Where things stand

- Live site: https://safire684-ops.github.io/civicalign/
- Repo: https://github.com/safire684-ops/civicalign — `origin/main` matches local `main`.
- Claude.ai copy (manual republish, CSS inlined; does not update itself): https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj
- Shared doc (hand-mirrored): https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3

## The four-view layout (published)

Three files changed. **Calculations, thresholds, data blocks and the methodology
report were not touched and must stay unchanged.**

| File | What changed |
|---|---|
| `demo/senator-check.html` | The long page became four views, one visible at a time, switched by real tabs (hash-routed: `#your-senators`, `#the-senate`, `#committees`, `#how-it-works`). Each leads with a one-line takeaway derived from figures already on the page. Extra detail sits behind "See details"; limits stay visible. Committees are chosen one at a time from an alphabetical list and show all their existing measures together. Clicking a senator's circle opens their state. |
| `demo/civicalign.css` | Tab/view styles keyed to `aria-selected`; takeaway, limit and disclosure styles; consistent spacing inside views; smooth scroll and hover scaling removed; tap targets ≥ 44px; smallest visible text 12px; the Senate "60th vote" label anchored away from the public label. |
| `tests/test_published_pages.py` | Nav test loosened for tab attributes. New tests: four tab panels with only the first shown at load; every view has a takeaway and a limit outside any disclosure; committee view is one-at-a-time and alphabetical; no smooth scroll or hover animation; existing measures and the 0.15 threshold present; highlight keyed to `aria-selected`; new How-it-works wording present and old absent; selected tab scrolled into view; pivot label anchoring; 44px tap targets. |

Wording change made at the owner's request: the How-it-works takeaway now reads
*"We combine public voting records, survey estimates, and other public data to
make these comparisons."*

## Test results

- `python -m pytest -q` → **93 passed**.
- Data blocks (`V M X G L R P C`) byte-identical to the pre-redesign page.
- Every sentence the old page rendered is still rendered identically; the new
  page additionally renders the 11 committees the old page never showed.
- Checked in a real mobile emulation at 375px, all four views: no horizontal
  overflow; smallest visible text 12px; every tap target ≥ 44px; Senate labels do
  not overlap; selected tab visible in the nav row.
- Keyboard: roving tabindex on the tabs (exactly one in the Tab order);
  ArrowLeft/Right/Home/End move selection, visible panel, hash and focus together.
  Zero console errors.

## Remaining issues

- **Real Enter/Space activation** of tabs and circles could not be driven from the
  browser pane (its key injection does not trigger native default actions — Enter
  did not toggle a plain `<details>` either). Elements are native links and
  buttons; worth one press on a real keyboard.
- **Headless-Chrome screenshots are untrustworthy at phone widths**: headless
  enforces a 500px minimum viewport, producing cropped images that once looked like
  stale wording. Use the DevTools-protocol script pattern (device emulation) for
  phone captures.
- Earlier items unchanged: rotate the Congress.gov API key pasted into chat; the
  2024 survey wave does not exist; two audits disagree on committee median vs mean
  (median shown, both computed — do not resolve during interface work); Output
  Ideology rests on 7–28 votes for four committees; the claude.ai copy and shared
  doc do not update themselves; the whitepaper is hand-written and the weekly job
  warns rather than blocks if its figures drift.

## Exact next steps

1. Owner reviews the fresh screenshots (four phone views at 390px, four desktop).
2. `git push` the local commit to `origin/main`.
3. Trigger the workflow (`gh workflow run update.yml -R safire684-ops/civicalign`)
   and confirm `update` and `publish` both succeed.
4. Verify the live site: nav present, only the first view shown at load, the same
   figures as local (`/tmp/snap2.js`-style sentence comparison).
5. Rebuild the claude.ai copy with the stylesheet inlined and republish to the
   same URL; the shared doc needs no change (methodology untouched).
6. If the weekly job re-dates `demo/methodology.html`, that is expected and
   separate from this change.

## The feedback that shaped this round, verbatim

> Replace the long scrolling page with four clear views: Your senators: state selector and two simple senator cards. The Senate: one main comparison, with the senator circles below. Committees: choose one committee and see its existing measures together. How it works: plain explanations, sources, and calculations. Each view should lead with a short takeaway and a clear chart. Put extra detail behind "See details," but keep important limits visible. Use readable text, consistent spacing, and clear labels. Avoid crowded charts and unnecessary animation. Scope: Pillars 4–6 only. Preserve all calculations, data, thresholds, and existing measures. Keep unresolved methodology disagreements separate. Do not add rankings, grades, or new claims.

Follow-ups: make the selected tab clearly visible (CSS had keyed to `aria-current`
while the tabs set `aria-selected`); replace the How-it-works takeaway wording; fix
the overlapping Senate labels on phones; confirm readability and tap targets at
phone size.

## Earlier rounds (kept for context)

The Gemini reports referenced in earlier rounds:

- Pillar 6 dual-metric framework: https://gemini.google.com/share/b75123b297db?skid=4798bd3c-9d90-4f8a-a251-00429acbda75
- System audit & execution directives: https://gemini.google.com/share/82bd4fe17a76?skid=e8601a35-0fb0-4b8d-b6a8-f4b2775b7142

Decisions approved earlier: public repo under `safire684-ops` with the personal
email hidden in history; Pillars 4–6 only; committee module plots the members'
median with the 0.15 threshold and keeps the mean in fine print; the percentage
score removed; six landmark bills at their median cutpoint; no API key anywhere.
Superseded: "receipts name the bill, vote and dividing line only" — the vote
example now shows the bill, question, date, the senator's own vote and a Voteview
link, is chosen by a neutral rule (busiest bill, passage vote first), and carries
the sentence "This vote does not tell us whether the state's voters supported the
bill." No state side is inferred from a vote's dividing line any more.
