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

### Why it needs qualifying

The calculation is fine; presenting it as the primary finding is not. On evenly
split committees the median describes nobody:

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
