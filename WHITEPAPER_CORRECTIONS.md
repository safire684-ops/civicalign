# Whitepaper corrections

Claims in the CivicAlign whitepaper that the 119th Congress data does not
support, with replacement text. Figures from `./scripts/report.sh`, senator
scores from Voteview `nokken_poole_dim1`, state lean = average two-party
presidential vote share 2016/2020/2024 (MIT Election Lab).

---

## 1. Part 7 — the Judiciary Committee example

### The claim as written

> If the system identifies that the Judiciary Committee is significantly more
> partisan than the Senate as a whole, it explains why moderate judicial nominees
> might be blocked from receiving a floor vote.

### Why it does not hold

Judiciary is one of the *least* distinctive committees in the Senate:

| measure | Judiciary | reading |
|---|---|---|
| party split | 11 / 10 | near-even, close to the chamber ratio |
| committee median | +0.361 | chamber median is +0.310 |
| drift from chamber | **+0.051** | below the noise floor; indistinguishable |
| state lean vs. Senate | **−3.14 pts** | its members' states lean *less* Republican than the average Senate seat |

So on ideology it sits essentially on top of the chamber, and on geography it
leans the opposite way from the claim. Using it as the illustration of an
unrepresentative committee inverts the finding.

### Replacement text

> Committees differ from the chamber in two distinct ways, and CivicAlign
> separates them because they have different causes and different consequences.
>
> The first is **who chairs the committee**. Because a chair decides which bills
> and nominations receive a hearing at all, their own position matters more than
> the committee's average. The Energy Committee's chair sits at +0.891 against a
> median of +0.564 among the committee's own majority-party members — a gap of
> 0.327, far larger than any committee's distance from the chamber. Budget (+0.286)
> and Commerce (+0.222) show the same pattern. Where a chair is well to the side of
> even their own party's members on that panel, CivicAlign flags it as a
> gatekeeping risk, because it identifies a single actor whose preferences can
> stop legislation a majority of the committee would advance.
>
> The second is **which states hold the seats**. The Energy Committee's members
> represent states that voted 1.85 points more Republican than the average Senate
> seat, and 5.22 points more Republican than the country. Indian Affairs (+1.65)
> and Agriculture (+1.42) show the same rural tilt. This is measured entirely in
> election results on both sides, so it involves no estimate of anyone's opinions:
> it is a statement about which electorates are represented on a panel, and it
> explains why some committees systematically favour particular regional interests.
>
> CivicAlign deliberately does **not** lead with a committee's ideological median.
> On an evenly split panel that median falls in the empty space between the two
> parties, where no senator actually sits, and it therefore moves with the seat
> ratio rather than with anyone's politics.

---

## 2. Part 7 — leading with the committee median

### The claim as written

> The system dynamically calculates the ideological median of every standing
> committee by aggregating the scores of its assigned members. It then compares
> this committee median to both the full Senate median and the national population
> median.

### Why it must be dropped, not qualified

An earlier version of this correction said to suppress the median when it
describes nobody. Uncertainty testing since then shows the metric does not work at
all, so it should not be presented as a finding in any form.

Drop one member and recompute: **17 of 19 committee medians move by more than
0.05, most by 0.2 to 0.34** — larger than the CCD values themselves, which run
0.01 to 0.31. The remaining two are stable but too small to clear the noise floor.
**No committee's drift figure is publishable.**

The cause is structural and no amount of care in the code fixes it. A committee
has ~20 members in two clusters that barely overlap, so the median sits on the
party boundary and any departure near it swings the result across the gap. CCD
measures the seat split, not ideology.

On evenly split committees it is worse still — the median describes nobody:

| committee | split | median | nearest actual senator | distance |
|---|---|---|---|---|
| Budget | 10 / 10 | +0.128 | −0.205 | **0.333** |
| Ethics | 3 / 3 | +0.139 | +0.440 | 0.301 |
| Environment | 9 / 9 | +0.003 | −0.286 | 0.289 |
| Appropriations | 14 / 14 | +0.004 | −0.162 | 0.166 |

The median for Budget sits a third of the way across the usable scale from the
closest real member. And these are precisely the four committees with the largest
apparent drift from the chamber — so the strongest-looking findings are the least
meaningful ones. **Only 5 of 19 committees have a drift figure that survives
this check.**

### Replacement text

> The system calculates each committee's ideological median, then tests whether
> that median describes an actual member. On a committee split evenly between the
> parties, the midpoint falls in the gap between two clusters and represents no
> senator; in the 119th Congress the Budget Committee's median sits 0.333 away
> from its nearest member, a third of the way across the usable scale. Because
> evenly split committees also produce the largest apparent divergence from the
> chamber, reporting that divergence without this test would systematically
> promote the least meaningful results. CivicAlign therefore suppresses a
> committee's drift figure when no member sits near the median, and reports the
> committee's party split and the position of its chair instead.

---

## 3. Part 6 — "dynamic DW-NOMINATE scores"

### The claim as written

> CivicAlign utilizes established political science metrics, specifically dynamic
> DW-NOMINATE scores, to assign a continuous ideological coordinate to every active
> senator based on their career voting record.

### Why it needs correcting

Voteview's `nominate_dim1` is a **single career-long constant per member**.
Murkowski is 0.204 in all ten of her Congresses. Describing it as dynamic, and
building a time series on it, would make every chart a flat line. The
per-Congress column that does move is `nokken_poole_dim1` (Murkowski: 0.124 to
0.299).

### Replacement text

> CivicAlign assigns each senator a continuous ideological coordinate from their
> roll-call record, using the per-Congress Nokken–Poole estimates published by
> Voteview. These are re-estimated within each Congress, so a senator's position
> can move as their voting behaviour changes. Voteview's career-constant
> DW-NOMINATE coordinate is retained only as a lifetime summary, since by
> construction it cannot register change over time. Because per-Congress estimates
> are not strictly comparable across Congresses, comparisons between sessions are
> reported with that caveat attached.

---

## 4. Part 5 — what the senator/state comparison can claim

### The claim as written

> By utilizing a common spatial metric, the system can calculate the exact
> distance between the senator's historical voting behavior and the ideological
> center of their home constituency.

### Why it needs correcting

There is no common metric between roll-call scores and public opinion unless one
is deliberately constructed. Senator scores come from votes; public positions
come from surveys. CivicAlign currently measures something real but different:
how far a senator sits from what their state's own election results predict,
which is a deviation from a pattern rather than an exact distance.

### Replacement text

> CivicAlign measures representation by fitting senators' voting records against
> their states' presidential election results across all one hundred seats, then
> reporting each senator's deviation from that relationship. State results explain
> roughly 69% of the variation in senator ideology, so a large deviation is a
> departure from a strong and consistent pattern. Ron Johnson of Wisconsin, whose
> state has averaged close to an even split across the last three presidential
> elections, votes further to the right than any state result would predict.
>
> This measures a senator's position relative to the pattern across the whole
> Senate, not an absolute distance from their constituents' views. Reporting an
> exact distance would require public opinion and roll-call behaviour to be placed
> on a single deliberately bridged scale, which CivicAlign does not yet do and
> does not claim to.

---

# Corrections to the DW-NOMINATE integration document

Phase 1 of that document (spatial voting model, Gaussian utility, the MLE loop)
is a sound explainer and needs no changes. Its advice not to re-estimate the
model yourself is right. The problems are all in Phase 2 and Phase 3, and three
of them would ship broken numbers.

## A. The ICPSR crosswalk drops 20% of the Senate

### As written

> This is the most frequent point of failure in civic tech. [...] you must merge
> these two systems using a "Crosswalk" file.

```python
merged_df = pd.merge(current_senate, cw_df, left_on='icpsr', right_on='icpsr_id', how='inner')
```

### What actually happens

The column name is right, but **`icpsr_id` is unpopulated for 220 of 539 rows**
in the roster file — including 20 of the 100 sitting senators. Every senator
elected in the last few cycles is missing it: Tuberville, Britt, Kelly, Ossoff,
Warnock, Fetterman, Padilla, Hickenlooper, Hagerty, Justice, McCormick, Moreno,
Alsobrooks, Schmitt, Sheehy, Ricketts, Mullin and more.

Run against real data, that inner join returns **80 senators, not 100**, and
raises no error. Every downstream median is then computed on a biased
four-fifths of the chamber, skewed toward longer-serving members.

The step is also unnecessary. `HSall_members.csv` already contains a
`bioguide_id` column (field 11). There is nothing to cross-walk.

### Replacement

```python
# Voteview already ships bioguide_id -- no ICPSR crosswalk required.
vv = pd.read_csv(VOTEVIEW_URL)
senate = vv[(vv.congress == 119) & (vv.chamber == "Senate")]

# Join to the CURRENT roster to resolve who actually holds a seat, on bioguide.
roster = pd.read_csv(ROSTER_URL)           # unitedstates.github.io, not theunitedstates.io
merged = senate.merge(roster, on="bioguide_id", how="inner")

assert len(merged) == 100, f"expected 100 seated senators, got {len(merged)}"
```

The assertion matters more than the join. Without it this class of bug is silent.

## B. The crosswalk URL is dead

`https://theunitedstates.io/...` resolves and accepts a TCP connection on 443
but fails the TLS handshake, so the fetch never completes. Use
`https://unitedstates.github.io/congress-legislators/legislators-current.csv`.

## C. `nominate_dim1` cannot do what Phase 2 asks of it

### As written

> Because DW-NOMINATE scores shift slightly over the course of a congressional
> session as new votes are cast, your database insertion must use an UPSERT

The UPSERT advice is correct. The column choice contradicts it:
`nominate_dim1` is a **single career-long constant per member**. Murkowski is
0.204 across all twelve of her Congresses; Crapo 0.505 across ten. Nothing to
upsert, and no time series is possible.

### Replacement

Store `nokken_poole_dim1`, which is re-estimated per Congress and does move
(Murkowski 0.124 to 0.299). Keep `nominate_dim1` in a separate column as the
lifetime summary. Note in the schema that per-Congress estimates are not strictly
comparable across Congresses.

Also: Phase 2 extracts `nominate_dim2` but nothing in Phases 2-3 uses it, and the
second dimension is weakly identified in the modern Senate. Store it if you like,
but do not build a metric on it without checking it is doing real work.

## D. Section 3.3's worked example is wrong in both magnitude and direction

### As written

> Practical Example: If the Senate Chamber Median evaluates to 0.05 [...] and the
> Judiciary Committee Median evaluates to 0.35 [...] the calculation is
> 0.35 - 0.05 = +0.30.
>
> "This committee leans significantly further right than the overall Senate,
> acting as a highly conservative gatekeeper for judicial legislation."

### Actual values, 119th Congress

| quantity | document | actual |
|---|---|---|
| chamber median | 0.05 | **+0.310** |
| Judiciary median | 0.35 | **+0.361** |
| CCD | +0.30 | **+0.051** |

The real drift is one sixth of the example's, below any sensible noise floor. The
hard-coded warning string would fire on a committee that is statistically
indistinguishable from the chamber — and Judiciary's members' states lean 3.14
points *less* Republican than the average Senate seat, so the "conservative
gatekeeper" reading is backwards on the other measure too.

Replace the example with a committee the data supports, and derive the warning
from a threshold rather than hard-coding its text. See correction 1 above.

## E. The SQL needs two guards it does not have

`PERCENTILE_CONT(0.5)` is the right function — it interpolates, so a 100-member
chamber correctly yields the mean of the 50th and 51st. Two gaps remain:

1. **`WHERE is_active = TRUE`** is the right instinct, but nothing in the
   document says how `is_active` is maintained. This is the whole problem: a
   `congress = 119` filter alone returns **104 rows for 100 seats**, because
   departed members stay in the file beside their replacements (FL, OH, OK, SC).
   All four surplus rows are Republicans, so a naive chamber median comes out
   +0.364 instead of +0.310.

2. **No phantom-median guard.** The committee query will happily return a median
   for a 10-10 panel, where it falls between the party blocs and describes no
   senator. Budget's median sits 0.333 from its nearest real member. Suppress the
   figure when no member is near it.
