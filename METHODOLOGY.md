# Methodology and known limits — Pillars 4–6 (Engine B)

Written to be published, not hidden. It describes the system that exists now.
Every displayed number also has its own entry in the methodology registry
(`src/civicalign/ideology/methodology.py`), shown on the published
`methodology.html` with the versions it was built from. Figures quoted below are
illustrations from result record `e0f5b6d9…` (measured 2026-09-27) and the bill
tables of the same day; the site rebuilds daily and the page carries the current
figures.

Engine A (Pillar 1: vote bindings and source packets) is documented in
`README.md` and `HANDOFF.md`; nothing here applies to it.

## Rules that apply to every number

1. Senator scores and state public estimates come from different measurement
   systems. They are never rescaled onto one scale and never compared directly.
2. No senator-to-state distance until a validated bridge exists (the active
   bridge is `none-v0`, status NONE).
3. No Senate-to-public gap and no committee-to-public drift until a national
   public estimate is defined and a bridge exists.
4. The population-weighted mean is the primary Pillar 5 method; the weighted
   median is a secondary comparison shown in details only. Both are candidate
   methods, not final.
5. Committee drift is committee median − Senate median.
6. `nominate_dim1` is the score; `nokken_poole_dim1` is stored only.
7. No 0–100 score, grade, rating or rank. The only 0–100 number is the display
   position, (`nominate_dim1` + 1) × 50: presentation only, never written as
   "/100", never applied to survey estimates, with 50 meaning Voteview's zero
   point and nothing more; the raw value is always available beneath it.
8. No evaluative labels, no ordering of politicians by score, and no causal
   claims about what a committee or the Senate did.
9. Bill counts group bills by their primary sponsor's voting position only. A
   sponsor's position is never presented as the bill's ideology, and CivicAlign
   does not classify any bill as liberal or conservative.
10. No LLM or other model is used anywhere in Engine B: every classification is
   fixed arithmetic or fixed text matching on official records.
11. Inputs and results are versioned and append-only; nothing old is
   overwritten or deleted.
12. Committee membership dates are observed dates, labelled as such.

## The one-dimension assumption

Every Engine B number places voting records on a single line, Voteview's first
DW-NOMINATE dimension, from −1 (the liberal end of roll-call voting) to +1 (the
conservative end). One dimension explains most of the variation in modern
congressional roll-call voting, so a senator's score is a real measurement of
one summary of their voting. It is not a measurement of everything they stand
for, it is relative to other members of Congress, and its zero is not "the
centre of the public".

## Senator scores

Source: Voteview (UCLA), member file `HSall_members.csv`, column
`nominate_dim1`, every Senate row of the 119th Congress, joined to the
congress-legislators roster (which decides who is seated).

- `nominate_dim1` is one score per legislator for a whole congressional career,
  on one scale across Congresses and chambers. It cannot show change within a
  career. `nokken_poole_dim1` (re-estimated per Congress) is stored beside it as
  extra data only.
- Voteview re-estimates scores as new votes are recorded, so a score can shift
  between snapshots. Every stored score names the snapshot version, SHA-256 and
  retrieval date of the file it came from.
- A seated senator Voteview has not scored yet is recorded with no score, never
  a predecessor's, and is left out of every centre and median.
- Voteview does not publish per-member standard errors in the member file, so
  score uncertainty is not propagated into any figure. Senators with few
  recorded votes have less certain scores.

## Pillar 4 — senator and state

Shown for every seated senator: their score, and separately their state
public's estimated ideology from the American Ideology Project (Tausanovitch &
Warshaw, v2022a, `mrp_ideology`, doi:10.7910/DVN/BQKU4M), 2020 wave (surveys
2017–2021), with its standard error, in the survey's own units.

**Why the senator-to-state distance is not available.** Voteview places senators
by how they vote on bills; the survey places the public by what respondents tell
a pollster. Two rulers with different units and different zero points.
Subtracting one from the other returns a number that means nothing. A distance
needs a bridge: a stated, validated method (for example published estimates
built to be comparable with legislator scores, or survey items on the bills
Congress voted on, modelled together with the roll calls) that places the
public estimate on the legislator scale. The bridge registry
(`ideology/bridge.py`) records the active bridge; today it is `none-v0`, status
NONE, and no conversion method exists, so "state public on the senator scale"
and "distance" are NOT_AVAILABLE for every senator, with that reason. A bridge
could later be recorded as PROVISIONAL (shown labelled provisional) or
VALIDATED (with its validation results); a bridge naming a method that is not
implemented still yields NOT_AVAILABLE, never a guess.

**Reference figures (visual only).** Three recognisable figures are drawn on
the senator scale so a reader can place a score: Bernie Sanders (his Voteview
score, which covers his House service 1991–2007 and his Senate service since
2007 together), Joe Biden (his Senate voting record, Delaware 1973–2009 — not
his presidency; Voteview's separate President estimate, built from positions a
president announced rather than votes cast, is excluded) and JD Vance (his
Senate voting record, Ohio 2023–2025 — not his vice presidency). Each value is
read from the same verified Voteview file and must be identical on every House
and Senate row of the person's Voteview id, or the anchor is refused rather than
averaged. They are never an input to any calculation, weight, centre, median or
drift, and are not part of the result key. Limits: Vance's record is short, so
his score is less certain; comparing records from different decades relies on
DW-NOMINATE's assumptions about how the scale holds over time; the choice of
figures is editorial and says nothing about any senator being like or unlike
them. Sanders is also a seated senator and so also appears in his own right,
with the same number.

## Pillar 5 — the Senate, counted two ways

Active senators are the seated senators with a score (100 today).

**Weights.** Each active senator is weighted by their state's resident
population (Census Vintage 2024, July 1 2024 estimate) divided by the number of
senators the state has seated. A state with a vacancy gives its whole weight to
the sitting senator; an unscored seated senator's share is left out with them.

**Primary method — `population_weighted_mean_v1`.** The main comparison is the
plain Senate mean (each senator counted equally, 0.120) against the
population-weighted mean (the sum of each score times its weight, divided by the
total weight, 0.085), and their difference, plain − weighted, sign kept
(+0.035). A positive difference means the weighted average sits lower on the
scale, toward its liberal end. The published page explains this in plain words
and says that it describes Senate voting records and state populations only,
not which laws passed, what voters believe, or why Congress made a decision.

**Secondary comparison — `population_weighted_median_v1`, details only.** The
first score at which the running total of weight reaches half the total weight
(exactly half averages that score with the next), compared with the plain
Senate median (0.3195). Why it is only secondary: the Senate is split by an
empty stretch between the two parties. Senators with negative scores are 47 of
100 but represent 53.5% of the population, so the weighted median jumps across
the gap and lands at −0.216; a median can move a long way when a few senators
change. The mean moves smoothly.

Both methods are labelled CANDIDATE_METHOD_NOT_FINAL. Open questions: median or
mean; residents or adults, citizens or voters; how to treat unscored senators.

**National public estimate — unresolved.** The survey publishes state
estimates. A national centre could be the population-weighted mean of the
state estimates, a population-weighted median of them, an individual-level
national estimate from the underlying survey (not in the state file), or any of
these weighted by adults, citizens, registered voters or voters. None has been
chosen, a population-weighted average of states is not treated as the national
median, and even a defined national estimate would need a bridge. So the
national public centre and the Senate-to-public gap are NOT_AVAILABLE.

**What the Senate actually passed.** Beside the averages, the page counts the
Senate bills (S.) of the current Congress that passed the Senate, and those of
them that were enacted, each grouped by sponsor voting position (see "Sponsor
voting position" below). Source: the GovInfo bill-status archive for the
Congress's Senate bills (`BILLSTATUS-119-s.zip`), read only if its bytes match
the verified snapshot.

- *Passed the Senate* — rule `senate_passage_loc17000_v1`: the bill's own
  record has a Library of Congress action with code 17000 ("Passed/agreed to in
  Senate"), and no later Senate action vitiates the passage. The stored evidence
  is every code-17000 action (date and text), the Senate's own floor action
  saying the bill passed, and whether an "Engrossed in Senate" text exists; a
  bill with several passage actions is one bill, dated by the earliest.
- *Enacted* — rule `enactment_signature_or_public_law_v1`: a passed-Senate bill
  whose record shows a presidential signature ("Signed by President") or a
  recorded public law (its laws element or a "Became Public Law" action, which
  also covers a law enacted without a signature or over a veto). A signed bill
  is law from the signature, so its public-law number is not required: the page
  counts enacted bills with a public-law number and those still awaiting one
  separately.
- Illustration (2026-09-27): 192 Senate bills passed the Senate (72 sponsored by
  senators on the liberal side of the Voteview scale, 120 on the conservative
  side); 41 were enacted (5 and 36), 37 with a public-law number and 4 signed and
  awaiting one.

Every count lists its exact bill ids, and each bill links to its official
record. Limits: Senate bills only (joint, simple and concurrent resolutions and
House bills the Senate passed are not included); a bill passed by unanimous
consent counts the same as one passed by a recorded vote; enactment also depends
on the House and the President. The counts do not show that the Senate's
ideological average, or any senator, caused a bill to pass.

## Pillar 6 — committees and the Senate

For each of the 16 Senate standing committees (codes `SS` + two letters;
subcommittees, select and joint committees are not included):

- **Committee median**: the median score of its current members who are seated
  and scored.
- **Committee median − Senate median**, sign kept, against the plain Senate
  median. Positive means the committee median sits higher on the scale.
- **Committee − national public drift**: NOT_AVAILABLE (no national estimate,
  no bridge).
- **Bills handled by this committee** (below).

Committee names come from the official congress-legislators committee list
(`committees-current.json`); the short name shown is the official name without
its "Senate Committee on (the)" prefix, and a name of any other form stops the
ingest rather than being guessed. Membership comes from congress-legislators
`committee-membership-current.json`. Its changes are stored as observed events
(joined, left, role changed) dated when CivicAlign first retrieved content
showing them — observed dates, never official appointment dates; the first
observation of a committee is marked as a baseline, since membership may have
begun earlier.

Limits: descriptive only — it says nothing about what a committee did, why a
bill passed or failed, or who controls it. With an even number of members whose
two middle members sit on opposite sides of the party gap (Appropriations,
Budget and Environment and Public Works today), the median falls where no
member sits. A small committee's median can move a long way when one member
changes. Every member the source lists is counted; no title (chair, ranking
member or any other) is treated differently.

**Bills handled by this committee.** From the same bill-status archive, each
committee card counts, for the Senate bills (S.) of the Congress:

- *Referred Senate bills*: bills whose own committee record shows the activity
  "Referred To" for the committee.
- *Reported Senate bills*: bills whose committee record shows "Reported By" or
  "Reported Original Measure" for the committee, meaning the committee formally
  reported the bill back to the Senate.
- *Reported without referral*: reported bills whose record has no "Referred To"
  activity for that committee (for example an original measure the committee
  wrote itself). Referred and reported are kept as separate lists, so the
  reported count is not assumed to be a subset of the referred count, and these
  bills are counted and shown, never hidden or moved.

Each count is split by sponsor voting position (see "Sponsor voting position"
below), lists its exact bill ids, and each listed bill shows its committee
action dates, its sponsor, the sponsor's current score and a link to its
official record. Illustration (2026-09-27): 5,387 referrals and 403 reports
across the 16 standing committees, with 15 reported-without-referral cases in 7
committees. Limits: only the full committee's own activities are read
(subcommittee activities are not); a bill referred to several committees counts
once for each; a discharge is not a report. The counts describe where bills
went, not why: they do not show why a committee reported or did not report any
bill, and they say nothing about a committee's motives.

## Sponsor voting position (bill counts in Pillars 5 and 6)

Every bill count groups bills by their primary sponsor only (rule
`sponsor_nominate_dim1_sign_v1`). The sponsor's Bioguide id in the bill's own
bill-status record is matched to that senator's `nominate_dim1` in the verified
`senator_ideology` table:

- score below zero: "Sponsored by senators on the liberal side of the Voteview
  scale";
- score above zero: "Sponsored by senators on the conservative side of the
  Voteview scale";
- score exactly zero: a separate group;
- no sponsor, no Bioguide id, no Voteview row or no score: UNKNOWN, with the
  reason.

**This is not bill ideology.** The group describes the sponsor's voting record,
never the content of the bill. CivicAlign does not decide whether any bill is
liberal or conservative, and the page never says "liberal bills" or
"conservative bills". Only the primary sponsor counts; cosponsors, including
those from the other party, are not considered. The sponsor's score is their
career-long Voteview score, relative to other members of Congress. No LLM or
other model is used: the rule is the sign of a stored number.

The exact current score shown beside a bill always comes from the latest
verified `senator_ideology` record. A bill's classification record also keeps,
as history, the score it was classified from; see "Storage and versions".

## How the page presents numbers

These rules change only how a stored number is shown; every calculation uses
the stored values. Each is published on `methodology.html` with its id, and the
supervisor re-derives every displayed position, label and sentence from the raw
values with separate code.

- **Display position** (`display_position_v1`): (`nominate_dim1` + 1) × 50, so
  −1 is 0, 0 is 50 and +1 is 100; a whole number on a marker, one decimal in
  details, rounded half-up from the exact decimal value. It is a position on a
  line, not a score, grade, rating or rank; higher is not better. 50 is
  Voteview's zero point, nothing more. Survey estimates of the public are never
  shown on this line.
- **Side label** (`side_label_v1`): from the sign of the raw value, "Liberal
  side of the voting scale", "Conservative side of the voting scale", or "At
  Voteview's zero point".
- **Where the Senate sits** (`senate_position_wording_v1`): from the plain
  Senate mean; within 2 display points of 50, "The Senate sits close to
  Voteview's zero point.", otherwise "The Senate sits on the liberal (or
  conservative) side of the voting scale."
- **What changes with population** (`population_shift_wording_v1`): shift =
  |plain − population-weighted| × 50 display points; exactly 0 "Weighting
  senators by state population does not move it.", under 5 points "… moves it
  slightly toward the <side> side.", 5 or more "… moves it toward the <side>
  side.", the side being where the weighted mean falls.
- **Committee compared with the Senate** (`committee_comparison_wording_v1`):
  under 2 display points from the Senate midpoint, "This committee sits close to
  the Senate midpoint."; otherwise the side it falls on.
- Every threshold is compared on the exact raw value, never on a rounded
  display number, so two committees shown with the same rounded markers can
  read differently when their exact distances fall either side of 2 points.
- **Party** labels (R, D, I) are identity data read from the verified
  congress-legislators roster when the page is built; they are never stored in
  or read from `senator_ideology`, and the roster version is recorded in the
  page's provenance.

## Storage and versions

All Engine B inputs and results are stored in `data/ideology/` as JSON Lines,
append-only and hash-chained (`record_id = sha256(prev_record_id |
content_sha256)`); a new version is written only when content changes, and old
lines are never rewritten. Each input record carries its source, source URL,
snapshot version, SHA-256, retrieval date and a fixture flag (fixtures live only
under `tests/fixtures/`). Result records are keyed by the record ids of every
input they used plus every setting that changes a number, are written once, and
are indexed in order; only committees whose membership changed are recomputed,
and a carried result always equals a full recompute.

The bill layer has two further tables. `bill_sponsor_classifications` holds one
record per Senate bill: the bill-to-sponsor classification, the bill's committee
activities, and the fingerprint of its official record. A new version is
written only when something that matters changes: the bill's official record,
its sponsor or Bioguide id, the classification rule, the class (the sign of the
sponsor's current score) or the reason a score is unavailable. A Voteview update
that moves a score but keeps it on the same side of zero writes no bill
versions; a change of side re-versions exactly that sponsor's bills. The score
stored in a classification record is historical (the score it was classified
from); current scores come only from `senator_ideology`. `senate_bill_outcomes`
holds each bill's Senate passage and enactment evidence under the two rules
above and never depends on Voteview. Each published page records the
fingerprints of the input versions it was built from (both bill tables,
`senator_ideology`, the Voteview and bill-status source versions, and the rule
versions), so any earlier page can be traced to the exact table contents behind
it. The details are in `docs/ENGINE_B_DATA_FLOW.md`.

## Verification

- The source snapshot is all or nothing, and the ingest refuses any raw file
  whose bytes do not match the snapshot's SHA-256.
- The page builder refuses to build if any number lacks a methodology entry,
  if the saved result does not match its recorded hash, unless exactly the three
  configured reference figures are stored, or if a committee has no official
  name. Displayed values are the saved values rounded half-up to the registry's
  decimals (three on the Voteview scale, two for survey estimates).
- Before anything is computed, both bill tables are verified: valid and
  hash-chained, consistent with each other, every class matching the sign of
  the sponsor's latest score, and current with the verified snapshot (a dry
  refresh would write nothing).
- The supervisor re-reads the raw files with separate code and reproduces every
  senator score and state estimate, the Pillar 5 means and medians and their
  differences, every committee median and drift, the reference figures and the
  committee names; it recounts every Pillar 5 outcome count and every Pillar 6
  committee bill count bill by bill from each bill's own XML and the Voteview
  file, checks each listed bill's sponsor, committee action dates and current
  sponsor score, confirms every stored class matches the sign of the latest
  score, and checks that the page names the current, verified input versions;
  it confirms that nothing needing the bridge or a national
  estimate carries a value, that every displayed number equals the saved record
  with its registry rounding, that every stored record is valid, hash-chained
  and append-only against the last commit, and that the published pages are the
  builder's output. Any disagreement fails the daily update, and nothing is
  published.

## Known scientific limits

- One dimension summarises roll-call voting, not every issue.
- Scores are estimated from recorded roll calls only: missed votes, and bills
  that never reached a vote, are not included. Score uncertainty is not
  propagated (no per-member standard errors are published).
- The survey estimate is a model estimate with a standard error, pooled over
  its survey period; which population it describes (adults, citizens, voters)
  is defined by the American Ideology Project, not by CivicAlign.
- There is no bridge between the two scales, so the central Pillar 4 and
  Pillar 5 comparisons with the public cannot be made yet.
- The Pillar 5 weighting counts residents, not voters, and both methods are
  candidates; the median is sensitive to the gap between the parties.
- Committee medians are sensitive to small and evenly split memberships.
- The bill counts describe sponsors, not bills, and only the primary sponsor;
  they cover Senate bills (S.) only, and the committee counts read only full
  committees' own activities.
- Census vintages revise earlier years; the vintage is part of every population
  record's key.

## Retired methods

Removed from the code and the site, and not coming back: the alignment score
(a voter estimate subtracted from a senator score and scaled to 0–100, with the
signed gap and the ordering built on it); the caucus-group peer comparison; the
seats-versus-nation election figure and the state-vote fit that was kept for
diagnostics only; the old committee bill-flow shares and the Yes/No-split
analysis (the sponsor-based "Bills handled by this committee" counts above are
a separate, new method); landmark bills; and every 0–100 score or grade (the display position above is a
separate, presentation-only transformation). None of them is replaced by a hidden
equivalent. The documents that described them are kept, marked as archived,
under `docs/archive/`.
