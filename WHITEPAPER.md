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

This is a statement about which electorates hold seats. It is not a statement
about senators' opinions, and it does not imply any senator is unrepresentative of
their own state.

## Finding 2: six senators sit further from their state than chance explains

State election results predict senator voting records well: they explain **69%**
of the variation across the chamber, with a fitted slope of +4.007 and a 95%
confidence interval of [+3.472, +4.542], nowhere near zero. The relationship is
strong and consistent, which is what makes departures from it meaningful.

Departures are measured against that pattern. The typical size of a departure is
0.285, so a senator has to sit roughly **0.57** away from the fitted line before
the gap is larger than ordinary variation. **6** of 100 senators do:

| senator | state | departure | significance |
|---|---|---|---|
| Ron Johnson | WI | +0.871 | +3.07 |
| Rick Scott | FL | +0.787 | +2.77 |
| Ted Cruz | TX | +0.652 | +2.30 |
| Ted Budd | NC | +0.617 | +2.17 |
| Jon Ossoff | GA | −0.615 | −2.17 |
| David McCormick | PA | +0.579 | +2.04 |

A positive figure means a record further to the right than the state's own
election results predict; negative, further to the left.

The remaining 94 senators sit approximately where their states' results predict. This matters for how the finding is presented: a ranked list of the ten
or twenty "most out of step" senators would mostly consist of ordinary variation
dressed up as a finding, and this project does not publish one.

Departures are also adjusted for a technical effect: a large gap is easier to
produce by chance for senators from very safe states, because the fitted line is
least constrained at the ends of the range. Without that adjustment, senators from
lopsided states would be flagged merely for being at the edge of the scale.

**What this finding does and does not say.** It says a senator's record departs
from the relationship that holds across the Senate as a whole. It does not say how
far that senator is from their state's median voter in absolute terms. Those are
different claims, and only the first is supported here: if the entire Senate
shifted in one direction, every departure measured this way would stay the same,
because the baseline would shift with it. An absolute distance would require
public opinion and voting records to be placed on a single deliberately bridged
scale, which this project does not do and does not claim to.

## Finding 3: committee ideology cannot be measured this way, and is not reported

Committees decide which bills reach the floor, so an unrepresentative committee is
a plausible explanation for why legislation dies. The obvious way to measure this
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
majority — several sit well to the side of their own colleagues: Energy +0.327,
Budget +0.286, Commerce +0.222.

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
