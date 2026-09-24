# Methodology and known limits

Drafted to be published, not hidden. Every item here is something an expert
reader would otherwise find first. Figures quoted below are illustrations from
the time of writing; the site rebuilds weekly, and the published methodology
report carries the current figures.

## The one-dimension assumption

Every metric in Sections 2–5 assumes politics fits on a single line from
progressive (−1.0) to conservative (+1.0). That holds up well for congressional
roll-call voting, where one dimension explains most of the variance. It holds up
considerably worse for voters, whose economic and social views do not line up as
neatly.

So a senator's position on the Senate voting scale is a real measurement of one
particular summary of roll-call voting. It is not a measurement of politics, and
it is not on the same scale as any measure of voters.

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

## Pillar 4: comparison with comparable senators

Voteview publishes four datasets -- Member Ideology, Congressional Votes,
Members' Votes, Congressional Parties -- and all four are roll calls and the
people who cast them. None contains a position for the public, so no comparison
of a senator with the public can be made inside that data, and CivicAlign does
not make one.

What the site shows instead stays on one scale. Each senator is compared with
senators **in the same caucus group** who represent **other states with similar
recent presidential voting** (`peers.py`):

- Caucus groups: the Republican caucus; the Democratic caucus, meaning Democrats
  plus the Independents whose Senate roster entry records that they caucus with
  them. An unrecognised or missing party or caucus value gets no comparison.
- Similar states: the two-party presidential share (2016, 2020 and 2024 averaged
  equally) within ±4 percentage points of the senator's state.
- At least six peers; the conclusion is published only if it is the same at
  ±2, ±3, ±4 and ±5 points. Otherwise the page says the result depends on the
  window, or that there are too few comparable senators.
- The result says whether the senator's record is within the observed range of
  the peers' records, or outside it on the more liberal or more conservative
  side. Peers are listed by state, never ordered, and nothing is ranked.

This describes where a voting record sits among comparable senators. It does
not measure whether a senator represents, agrees with or matches the state's
voters.

**Retired: the state-vote regression.** An earlier version fitted
`senator score = a + b x (state presidential vote share)` across all senators
and read each senator's residual. It is kept in `representation.py` for
diagnostics only and produces no published classification. It was retired
because the fitted line mostly measured the party split (senators cluster in two
groups, and the line runs between them), so in competitive states the "expected"
position fell in a gap where no senator of either party sits, and residuals
there described party membership rather than anything about the senator.

## Pillar 5: Senate seats and the national vote

**Election results on both sides.** Apportionment skew becomes the average
state vote share per Senate seat minus the national vote share: **+3.37 points**
averaged over 2016/2020/2024. Each state gets two senators regardless of population, so small states
are over-weighted, and this measures exactly that. Vote share against vote share,
identical units, no assumption whatsoever. It is a structural claim about seats,
not a claim about senators' opinions.

The same method gives committees against the country. Report it **against the Senate's own
average**, not just the nation: the gap against the nation mostly reflects the
+2.66pt structural skew plus the fact that the majority party holds most seats on
every committee, neither of which is about the committee. Against the Senate, the
picture inverts for some -- Judiciary is +0.23 vs the nation but **-3.14 vs the
Senate**.

State lean is the average two-party presidential share over 2016, 2020 and 2024,
each election weighted equally, as partisan-lean indices such as Cook PVI do. It
is used to pick comparable states for Pillar 4 and for the seats-vs-nation
figure. Three cycles is steadier than one but slower to reflect a state that is
genuinely moving, so `StateLean.swing` reports the spread between a state's most
and least Republican year -- Florida moved 6.0 points across the three,
California 5.7.

Source: MIT Election Data and Science Lab, U.S. President 1976-2024, Harvard
Dataverse doi:10.7910/DVN/42MVDX. Chosen after rejecting a county-level
alternative whose 2016 file understated California's Democratic vote by 1.4
million. Votes are summed per candidate across every party line, because fusion
voting puts one candidate on several lines and summing by party instead loses
~292k Trump votes in 2016.

Remaining limits of vote share as the state measure: it is partisan choice rather
than policy preference, and a two-party share discards third-party votes. It
measures what voters *did*, not what they *think*.

## The voter estimate: separate context, never compared directly

The site shows each state's voter estimate from the American Ideology Project
(Tausanovitch & Warshaw, newest wave 2020) as supporting context, on its own
voter-estimate scale. It is never subtracted from a senator's voting score,
never tested against the senator's score, and never used to rank senators.

The reason: DW-NOMINATE and Nokken-Poole place senators using how they vote on
bills; surveys place voters using what they tell a pollster. Two rulers, two
zero points. Subtracting one from the other is subtracting Celsius from
Fahrenheit: it returns a number, and the number means nothing.

A direct comparison would need a validated bridge -- something present in both
datasets, such as published bridged estimates built to be comparable with
legislator scores, or survey items on the actual bills Congress voted on,
modelled together with the roll calls. CivicAlign has no such bridge, and none
is configured (`sources/state_prefs.py`). Stretching a state index onto the
senators' scale is not a bridge and is not used. Until a bridge exists and has
been reviewed, no senator-to-voter comparison is published.

## Definitional choices that move the headline

- **Mean vs. median.** The spec says *median* voter, but MRP naturally yields a
  mean or a distribution. These differ whenever a state's opinion is lopsided.
  This matters only for the voter-estimate context and any future bridge; no
  published figure compares a state's voters with a senator or the chamber.
- **Who is "the electorate."** Adults, citizens, registered voters, or actual
  voters. Turnout weighting moves any national voter coordinate. Set in
  `config.electorate` and stated publicly.
- **National median, two definitions.** The population-weighted median of
  individuals is *not* the median of the 50 state medians. The spec means the
  former.

## Departures from the spec

**Retired: the alignment score.** The original spec scored each senator
against an estimate of the state's voters with `(1 − gap/2) × 100`. It required
subtracting a voter estimate from a senator score, which the scales do not
support (see above), and it invited ranking senators against one another. It
was removed from the code and the site, along with the signed gap and the
ranking built on it. Nothing replaces it; Pillar 4 uses the peer comparison.

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

**Chairs sit away from their committees.** Pillar 6 is descriptive: it shows
how each committee compares with the Senate, without claiming why a bill moved or
did not. One pattern worth knowing is that nearly every chair sits far
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

**The retired regression.** Its analytic standard errors, leverage and
prediction band are still computed (`uncertainty.py`) so the methodology report
can show why it was retired. They do not support any statement about an
individual senator, and none is published.

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
  `0.49999999999999994`. Anywhere they are compared for equality — ties at a range
  boundary, deduplicating medians — needs a tolerance.
