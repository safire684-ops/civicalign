> **ARCHIVED — historical only.** This document describes the retired Pillars 4–6
> implementation (removed in Step 5B, September 2026). Its methods, figures and file
> names are not current, and some of its claims were later found not to hold.
> The current system is described in `README.md`, `METHODOLOGY.md` and
> `docs/ENGINE_B_DATA_FLOW.md`.

# Measuring how far the Senate sits from the people it represents

**Scope: math-spec sections 2–5 (Pillars 4, 5 and 6).** Pillars 1–3 and 7 —
bill breakdowns, roll-call tracking, committee votes and the polling overlay —
are covered elsewhere and are not described here.

Every figure below is produced by `./scripts/report.sh` in this repository and is
checked by the test suite. If a number here stops matching the code, a test fails.

---

## What this measures

Two questions, both answerable from public records:

1. **Is a senator further from their state's politics than the rest of the Senate
   is from theirs?**
2. **Do the Senate's seats, and its committees' seats, represent an electorate
   that looks like the country?**

Neither question requires anyone's opinion to be estimated. Both are answered from
roll-call votes and election returns.

## The measurement problem, and how it is solved

A senator's position is measured from how they vote on bills. The public's
position, if you used a survey, would be measured from what people tell a
pollster. Those are two different scales with two different zero points.
Subtracting one from the other produces a number that means nothing — it is
subtracting Celsius from Fahrenheit.

Most attempts to compare legislators with the public either ignore this or build a
deliberate statistical bridge between the two scales. This project does neither.
It avoids the subtraction in two ways.

**Fit a line instead of taking a difference.** Senator voting records are fitted
against their states' presidential election results across all one hundred seats.
The fitted line describes what voting record a given state result typically
produces. A senator's distance from that line is then measured in voting-record
units throughout, so the two scales are never subtracted and never need to match.

**Compare like with like.** Where the question is about representation of the
public rather than about ideology, both sides are measured in election results:
the vote share of the states holding Senate seats against the vote share of the
country. Identical units, no assumption of any kind.

State partisan lean is the average two-party presidential vote share across 2016,
2020 and 2024, each election weighted equally. Senator positions are the
per-Congress Nokken–Poole estimates published by Voteview, which are re-estimated
within each Congress and therefore move as a senator's voting behaviour changes.

---

## Finding 1: the Senate's seats lean more Republican than the country

Because every state elects two senators regardless of population, the Senate
over-represents small states. Measuring that requires no estimate of anyone's
views — only a comparison of election results:

| | two-party Republican share |
|---|---|
| average state, per Senate seat | 52.52% |
| the country | 49.15% |
| **structural skew** | **+3.37 points** |

The skew has the same sign in all three elections examined — +4.08 in 2016, +3.37
in 2020, +2.66 in 2024 — so the finding does not depend on which cycle is chosen.
It is also declining steadily across the three, which is itself worth noting.

All 100 senators are also shown as a row of circles, coloured by their distance
from the public; the 60th senator from the left — the vote that decides whether
most legislation can proceed — sits at +0.440.

This is a statement about which electorates hold seats. It is not a statement
about senators' opinions, and it does not imply any senator is unrepresentative of
their own state.

## Finding 2: the senator and the state, on separate scales

A senator's position comes from roll-call votes (Voteview) and a state's from
survey answers (the American Ideology Project). Those are two measurement
systems without a validated bridge, so this project reports no distance between
a senator and their state's survey estimate, not even its sign. A direct
senator-versus-state alignment measure requires a validated statistical bridge
between voter and legislator scales. CivicAlign does not currently have that
bridge. Earlier versions reported such a distance, first as a percentage, then in
points, then as a direction; all three were withdrawn as invalid.

What the tool leads with instead is a peer comparison with election results as
the matching input: each senator against senators in the same caucus group from other states
whose recent presidential two-party vote is within four points, shown as the
observed peer range and middle on the senators' scale, with a conclusion only
where at least six peers exist and the answer is the same across nearby
windows. It answers a relative question about senators: how does this record
compare with same-caucus senators representing similarly voting states? An
earlier version led with the regression of senator position on state vote
share; an audit found that its line mostly measures the party split and falls,
for competitive states, in a gap where no senator sits, so it was retired from
the page and kept for diagnostics. Beneath the peer comparison, the tool still
shows a senator against the Senate's middle, on the senators' scale, and a
state's survey estimate against the national estimate, on the voters' scale,
each within its own system.

**Perspective.** A position on its own means nothing to a reader, so the tool
marks landmarks on the same line: the middle Democrat (−0.379), the middle
Republican (+0.563), the Senate's middle, the American public, and eight familiar
senators at their real positions. A gap is also expressed as a share of the whole
scale, as the distance between the two named senators who sit that far apart, and
against the typical senator's distance from their own state. No bills are marked:
a floor vote's dividing line says where a coalition split, not what a state's
voters wanted. The senator's number comes from every roll-call vote they have cast
this Congress; the state's from surveys asking residents where they stand on many
policy questions. The gap says how far apart they sit overall and cannot say which
issues make up the difference.

## Finding 3: committees, measured three ways

Each committee is measured against the Senate's middle (+0.310). Both sides of
that comparison come from Voteview, so it can be stated in points; no committee
figure is subtracted from the survey-based public estimate.

**Where the members sit.** The midpoint of the committee's members. A midpoint
more than 0.15 from the Senate's middle is flagged as a gatekeeper. This number is
soft: on a committee split between two parties the midpoint can fall in the gap
between them, and it can move sharply when one member is replaced — the last
column says how far.

| committee | members' midpoint | vs. Senate | moves if one member changes |
|---|---|---|---|
| Environment | +0.003 | −0.307 | 0.29 |
| Appropriations | +0.004 | −0.306 | 0.17 |
| Foreign Relations | +0.535 | +0.225 | 0.06 |
| Homeland/Govt Affairs | +0.520 | +0.210 | 0.34 |
| Small Business | +0.520 | +0.210 | 0.34 |
| Budget | +0.128 | −0.182 | 0.33 |

**Where the Senate split on its bills.** Take the bills a committee sent to the
floor and the dividing lines of every floor vote on them; their median is where
the Senate split on that committee's bills. This says where the Yes and No sides
divided, not whether the bills themselves were liberal or conservative. Only four
committees have seven or more such votes — most floor action is nominations and
House bills that no Senate committee reported.

| committee | floor votes | where they divided the Senate | vs. Senate |
|---|---|---|---|
| Budget | 28 | +0.077 | −0.233 |
| Appropriations | 13 | −0.110 | −0.420 |
| Armed Services | 13 | −0.161 | −0.471 |
| Veterans | 7 | −0.001 | −0.311 |

**Which bills it let through.**

Committees decide which bills reach the floor, so the direct way to measure them is
to count what they did. Every Senate bill of the 119th Congress is in the
government's own bulk release, with its author and every committee it was sent to.
Each bill takes the side of the senator who wrote it.

Being sent on is rare so far: of 5,347 distinct bills sent to a Senate committee
(5,376 referrals, since some bills go to two committees), 425 have been sent on to
the floor. The Finance Committee has sent on 1 of 876. A bill not yet sent on is
counted as pending, not dead; the Congress is still running.

Across the whole Senate, bills by conservative senators get through 2.4 percentage
points more often than bills by liberal senators. Whatever its causes, that
Senate-wide pattern appears on almost every committee, so each committee is
measured against it rather than against zero:

| committee | liberal-record sponsors: sent forward | conservative-record sponsors: sent forward | beyond baseline |
|---|---|---|---|
| Small Business | 4 of 37 | 7 of 35 | +6.8 |
| Foreign Relations | 31 of 123 | 31 of 147 | −6.6 |
| HELP | 13 of 426 | 28 of 297 | +3.9 |
| Commerce | 34 of 227 | 50 of 250 | +2.6 |

Committees with fewer than 25 bills from either side are not reported; there one
bill moves the rate by several points. Thirteen committees have enough.

A bill's side comes from its author's record, not its content, so a moderate bill
by a conservative senator counts as conservative. And bills stall for reasons other
than politics — duplicates, symbolic bills, bills folded into larger ones — which is
why the comparison between the two sides carries the finding, not the raw rate.

## Why the first committee measure was dropped

Committees decide which bills reach the floor, so an unrepresentative committee is
a plausible explanation for why legislation stalls. The obvious way to measure this
is to compare a committee's ideological midpoint with the chamber's. That measure
does not work, and this project reports it for **0 of 19** committees.

The reason is structural. A Senate committee seats roughly twenty members drawn
from two ideological groups that barely overlap. Its midpoint therefore falls on
the boundary between the parties rather than at any member's position. Removing a
single member and recalculating moves seventeen of the nineteen midpoints by more
than the drift being reported; the other two are stable but too small to be
meaningful. On evenly split committees the midpoint describes nobody at all — the
Budget Committee's sits a third of the way across the usable scale from its
nearest actual member.

What such a measure tracks is how seats are divided between the parties, not the
politics of the people holding them. Reporting it would also be actively
misleading, because the evenly split committees that produce the least meaningful
midpoints produce the largest apparent drift — so ranking committees by it
promotes the worst results to the top.

Two measures of committee composition do survive the same test, and are reported
instead.

**The chair.** A committee chair is a single identifiable person, so there is no
midpoint to destabilise, and the chair controls what receives a hearing. Measured
against the median of their own party's members on that same committee — which
separates the chair's own position from the fact that chairs always come from the
majority — several sit well to the side of their own colleagues: Energy +0.328,
Budget +0.283, Commerce +0.219.

**Which states hold the seats.** Averaged across a committee's twenty or so seats,
state partisan lean is stable, because an average over many states does not
balance on a midpoint the way a median does. The Energy Committee's seats
represent states that voted 1.85 points more Republican than the average Senate
seat; Agriculture 1.42 points. Committees with fewer seats are excluded where one
departure could move the figure by more than the figure itself.

---

## Limits, stated plainly

**Politics is treated as one dimension.** Everything here places senators and
states on a single line from progressive to conservative. That works well for
congressional roll-call voting, where one dimension explains most of the
variation. It works less well for voters, whose economic and social views do not
line up as neatly.

**Election results measure behaviour, not belief.** Vote share records what voters
did, not what they think, and a two-party share discards third-party votes.

**Three elections is a compromise.** Averaging is steadier than a single cycle but
slower to reflect a state that is genuinely moving. Florida shifted 6.0 points
across the three cycles and California 5.7, so for those states the average hides
real movement.

**The scores have their own error, which is not carried through.** Senator
positions are statistical estimates, but Voteview does not publish a margin of
error for each member, so that uncertainty cannot be propagated into these
figures. It is the main remaining gap.

**Positions within a Congress are not strictly comparable across Congresses.** The
per-Congress estimates used here are calculated within each Congress separately.

## Reproducing this

```
./scripts/fetch_data.sh    # source data, with a timestamp and hash for each file
./scripts/report.sh        # every figure above
```

Sources: Voteview (UCLA) for roll-call-based senator positions; the
`unitedstates/congress-legislators` project for who currently holds each seat and
for committee rosters; the MIT Election Data and Science Lab, U.S. President
1976–2024, for election results. Each download is recorded in
`data/raw/PROVENANCE.tsv` with its date and checksum, because the senator
estimates are revised as new votes are recorded.
