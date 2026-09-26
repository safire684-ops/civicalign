# Methodology and known limits — Pillars 4–6 (Engine B)

Written to be published, not hidden. It describes the system that exists now.
Every displayed number also has its own entry in the methodology registry
(`src/civicalign/ideology/methodology.py`), shown on the published
`methodology.html` with the versions it was built from. Figures quoted below are
illustrations from result record `5f42ca01…` (measured 2026-09-24); the site
rebuilds daily and the page carries the current figures.

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
7. No 0–100 score and no 0–100 display of any score.
8. No evaluative labels, no ordering of politicians by score, and no causal
   claims about what a committee or the Senate did.
9. Inputs and results are versioned and append-only; nothing old is
   overwritten or deleted.
10. Committee membership dates are observed dates, labelled as such.

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
total weight, 0.083), and their difference, plain − weighted, sign kept
(+0.037). A positive difference means the weighted average sits lower on the
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

## Pillar 6 — committees and the Senate

For each of the 16 Senate standing committees (codes `SS` + two letters;
subcommittees, select and joint committees are not included):

- **Committee median**: the median score of its current members who are seated
  and scored.
- **Committee median − Senate median**, sign kept, against the plain Senate
  median. Positive means the committee median sits higher on the scale.
- **Committee − national public drift**: NOT_AVAILABLE (no national estimate,
  no bridge).

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

## Storage and versions

All Engine B inputs and results are stored in `data/ideology/` as JSON Lines,
append-only and hash-chained (`record_id = sha256(prev_record_id |
content_sha256)`); a new version is written only when content changes, and old
lines are never rewritten. Each input record carries its source, source URL,
snapshot version, SHA-256, retrieval date and a fixture flag (fixtures live only
under `tests/fixtures/`). Result records are keyed by the record ids of every
input they used plus every setting that changes a number, are written once, and
are indexed in order; only committees whose membership changed are recomputed,
and a carried result always equals a full recompute. The details are in
`docs/ENGINE_B_DATA_FLOW.md`.

## Verification

- The source snapshot is all or nothing, and the ingest refuses any raw file
  whose bytes do not match the snapshot's SHA-256.
- The page builder refuses to build if any number lacks a methodology entry,
  if the saved result does not match its recorded hash, unless exactly the three
  configured reference figures are stored, or if a committee has no official
  name. Displayed values are the saved values rounded half-up to the registry's
  decimals (three on the Voteview scale, two for survey estimates).
- The supervisor re-reads the raw files with separate code and reproduces every
  senator score and state estimate, the Pillar 5 means and medians and their
  differences, every committee median and drift, the reference figures and the
  committee names; it confirms that nothing needing the bridge or a national
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
- Census vintages revise earlier years; the vintage is part of every population
  record's key.

## Retired methods

Removed from the code and the site, and not coming back: the alignment score
(a voter estimate subtracted from a senator score and scaled to 0–100, with the
signed gap and the ordering built on it); the caucus-group peer comparison; the
seats-versus-nation election figure and the state-vote fit that was kept for
diagnostics only; the committee bill-flow and Yes/No-split analysis; landmark
bills; and every 0–100 display. None of them is replaced by a hidden
equivalent. The documents that described them are kept, marked as archived,
under `docs/archive/`.
