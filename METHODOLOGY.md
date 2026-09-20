# Methodology and known limits

Drafted to be published, not hidden. Every item here is something an expert
reader would otherwise find first.

## The one-dimension assumption

Every metric in Sections 2–5 assumes politics fits on a single line from
progressive (−1.0) to conservative (+1.0). That holds up well for congressional
roll-call voting, where one dimension explains most of the variance. It holds up
considerably worse for voters, whose economic and social views do not line up as
neatly.

So "this senator is 0.4 away from their state" is a real measurement of one
particular summary of politics. It is not a measurement of politics.

## Senator coordinates

Source: Voteview (voteview.com, UCLA), `HSall_members.csv`, column
`nokken_poole_dim1` — re-estimated within each Congress, so it moves over a
career.

Two limits:

- Nokken-Poole is estimated per-Congress, so it is **not strictly a common space
  across Congresses**. Comparisons between Congresses carry that caveat.
- Voteview **revises past scores** on re-estimation. Every download is stamped in
  `data/raw/PROVENANCE.tsv`; a published figure should cite its stamp.

The alternative, `nominate_dim1`, is a career-long constant and cannot support
any claim about change over time. See `config.py`.

## Pillar 4 without a shared ruler

Voteview publishes four datasets -- Member Ideology, Congressional Votes,
Members' Votes, Congressional Parties -- and all four are roll calls and the
people who cast them. Its scores update live as new votes are recorded, which is
genuinely useful, but no version of them contains a position for the public. So
senator-vs-public cannot be a subtraction inside that data.

It does not have to be a subtraction. Two comparisons work with no shared scale
at all:

**1. Regression, not subtraction.** Fit

    senator ideology = a + b x (state presidential vote share)

across all 100 senators, then read the **residual**: actual minus predicted. The
fitted line says what ideology a state's election result typically produces; the
residual says how far a senator sits from that expectation. Units are ideology
units the whole way through -- the two scales are never subtracted, so they never
have to match. On 2024 results the fit is r-squared **0.687**, so state election
results explain about 69% of senator ideology, and a residual is deviation from a
strong pattern rather than from noise.

*What it answers:* "Is this senator more extreme than their own state's election
result predicts, compared with how every other senator relates to theirs?"

*What it does not answer:* "How far is this senator from their state's median
voter?" That is an absolute distance and still needs bridged survey data. The
residual is **relative to the Senate-wide pattern** -- a uniform shift of every
senator changes no residual at all, which is pinned as a test. If the whole Senate
moved right, this measure would not show it.

**2. Election results on both sides.** Apportionment skew becomes the average
state vote share per Senate seat minus the national vote share: **+3.37 points**
averaged over 2016/2020/2024. Each state gets two senators regardless of population, so small states
are over-weighted, and this measures exactly that. Vote share against vote share,
identical units, no assumption whatsoever. It is a structural claim about seats,
not a claim about senators' opinions.

The same method gives committees-vs-public. Report it **against the Senate's own
average**, not just the nation: the gap against the nation mostly reflects the
+2.66pt structural skew plus the fact that the majority party holds most seats on
every committee, neither of which is about the committee. Against the Senate, the
picture inverts for some -- Judiciary is +0.23 vs the nation but **-3.14 vs the
Senate**.

State lean is the average two-party presidential share over 2016, 2020 and 2024,
each election weighted equally, as partisan-lean indices such as Cook PVI do.
Three cycles is steadier than one but slower to reflect a state that is genuinely
moving, so `StateLean.swing` reports the spread between a state's most and least
Republican year -- Florida moved 6.0 points across the three, California 5.7. A
large swing means the average is hiding real movement and the residual built on
it deserves less weight.

Source: MIT Election Data and Science Lab, U.S. President 1976-2024, Harvard
Dataverse doi:10.7910/DVN/42MVDX. Chosen after rejecting a county-level
alternative whose 2016 file understated California's Democratic vote by 1.4
million. Votes are summed per candidate across every party line, because fusion
voting puts one candidate on several lines and summing by party instead loses
~292k Trump votes in 2016.

Remaining limits of vote share as the state measure: it is partisan choice rather
than policy preference, and a two-party share discards third-party votes. It
measures what voters *did*, not what they *think*.

## The survey-bridging problem (why absolute distances are still not live)

DW-NOMINATE places senators using how they vote on bills. Surveys place voters
using what they tell a pollster. Two rulers, two zero points. Subtracting one from
the other is subtracting Celsius from Fahrenheit: it returns a number, and the
number means nothing.

Bridging requires something present in both datasets. Three options, in
`sources/state_prefs.py`:

- **Option A (recommended).** Published bridged MRP estimates — Tausanovitch &
  Warshaw (2013), *Journal of Politics* — built to be comparable with legislator
  scores. Bridge already done and peer-reviewed. About a week of work.
- **Option B (most rigorous).** Build it from shared items: the Cooperative
  Election Study asks respondents about *specific actual bills* Congress voted on,
  so those bills bridge voters and senators inside one item-response model. This
  is Bafumi & Herron's leapfrog-representation design. Needs CCES data, an ACS
  poststratification frame, a Stan model and statistical review — two to three
  months.
- **Option C (placeholder only).** Stretch an existing state ideology index onto
  [−1, +1]. Fast, correlated with the right answer, but **not a bridge** — the
  distances are not real distances. If it reaches the frontend, the frontend must
  say so.

Until one is configured, the pipeline prints `NOT AVAILABLE` for absolute
distances specifically. A missing dataset should be a visible gap in the product,
not a plausible-looking number. Note this now blocks only the absolute-distance
metric -- the regression route above is live and needs none of it.

## Definitional choices that move the headline

- **Mean vs. median.** The spec says *median* voter, but MRP naturally yields a
  mean or a distribution. These differ whenever a state's opinion is lopsided.
  Pick one and use it everywhere — Pillar 5 compares a state median to a chamber
  median, and mixing the two silently breaks the comparison.
- **Who is "the electorate."** Adults, citizens, registered voters, or actual
  voters. Turnout weighting moves the national coordinate, and every Pillar 5
  headline depends on it. Set in `config.electorate` and stated publicly.
- **National median, two definitions.** The population-weighted median of
  individuals is *not* the median of the 50 state medians. The spec means the
  former.

## Departures from the spec

**The alignment score compresses.** The spec's `(1 − gap/2) × 100` divides by the
theoretical max distance of 2.0, but real senators span roughly −0.75 to +0.94 and
state medians will bunch near the middle, so real gaps run 0 to about 1.1 and the
score almost never leaves 45–100%. Every senator looks at least half-aligned,
including the worst. A gap of 1.0 — enormous — still prints as 50%. Retained for
continuity but shown alongside a rank: "worse aligned than 94 of 100 senators".

**The sign is kept.** The spec takes an absolute value immediately. Two senators
with an identical 0.5 gap can differ completely: one is more extreme than their
state in the same direction, the other has crossed past the middle to the
*opposite* side of their own electorate. The second is far more damning and the
absolute value erases it. `Alignment.crosses_over` exposes it.

**The median senator is not the pivot.** Legislation needs 60 votes for cloture,
so the 60th senator from the left decides whether a bill advances — in the 119th
they sit 0.130 *right* of the median. Nominations need only a simple majority
since the 2013 and 2017 rules changes. Agenda control sits with the majority
party's median. All three are reported.

## Committee drift: read with care

**CCD is mostly noise.** Observed CCDs run 0.01–0.31 while internal committee
spreads run 1.07–1.68. The drift is a small fraction of the dispersion it is
summarising. Worse, with ~20 members the median lands exactly on one senator's
score, so the metric is quantized and identical CCDs recur across unrelated
committees as an artifact — Small Business and Homeland both read +0.211; Rules
and Agriculture both +0.018. **9 of 19 committees fall below the 0.10 noise
floor** and are flagged rather than published.

**The chair is the real signal.** Pillar 6 exists to explain where bills get
stuck, and the chair decides what gets a hearing. Nearly every chair sits far
right of their own committee's median — Budget's chair is +0.897 against a median
of +0.128, Commerce's +0.865 against +0.326. Gaps of 0.5–0.8, two to three times
any CCD. Caveat: chairs come from the majority party, so part of this is plain
majority control; `majority_median` is reported alongside to separate the two.

**The whitepaper's Judiciary example does not hold.** Part 7 claims the Judiciary
Committee is "significantly more partisan than the Senate as a whole." Its CCD is
**+0.051**, below the noise floor, and its members' states lean **3.14 points
less** Republican than the average Senate seat -- the opposite direction from the
claim. See `WHITEPAPER_CORRECTIONS.md` for replacement text, along with three
other claims the data contradicts.

## Uncertainty

Not everything here deserves an error bar, and bootstrapping indiscriminately
would imply a kind of uncertainty these numbers do not have. All 100 senators are
observed: the Senate is a census, not a sample. So each figure gets the treatment
that fits it.

**Chamber median — exact, and stable.** Given the scores there is no sampling
error. What is worth reporting is how tightly it is pinned: the gap between the
50th and 51st senators is 0.036, and no single departure moves it more than 0.018.
Publishable.

**Committee medians — not publishable.** A jackknife (drop one member, recompute)
answers the question that matters: would this survive one retirement? For 17 of 19
committees, no. Most medians move 0.2-0.34, larger than the CCD values themselves.
The remaining two are stable but below the noise floor. A bootstrap was not used
because it would imply members were sampled from a population; they were
appointed.

**The regression — genuine model uncertainty, computed analytically.** Slope
+4.007 with a 95% interval of [+3.472, +4.542], nowhere near zero. Residual
standard error 0.285, so a residual needs to clear roughly 0.57 to mean anything.
Residuals are leverage-corrected (studentized) because a raw residual is easier to
produce by chance at the edges of the vote-share range, where the line is least
constrained — otherwise senators from very safe states get flagged merely for
sitting at the end of the scale. Only **6 of 100** senators clear |t| > 2.

**Apportionment skew — a census of ballots, so almost no statistical error.** Its
real sensitivity is which elections were included, reported as the spread across
cycles: 2016 +4.08, 2020 +3.37, 2024 +2.66. The sign never reverses, so the
finding holds. The monotonic decline is itself worth noting.

**Not covered: score measurement error.** DW-NOMINATE and Nokken-Poole are
estimates with their own standard errors, but Voteview does not publish per-member
SEs in the member file, so this cannot be propagated. Stated rather than papered
over. It is the one remaining gap in the uncertainty treatment.

## Not yet implemented
- **Roster edge cases.** Ex officio members are currently counted like any other;
  subcommittees are excluded by the four-character code filter. Both rules should
  be deliberate and documented rather than incidental.
- **Float comparison.** Coordinates are binary floats: `0.7 − 0.2` is
  `0.49999999999999994`. Anywhere they are compared for equality — ranking ties,
  deduplicating medians — needs a tolerance.
