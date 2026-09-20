# Methodology — math spec sections 2–5

Every figure the pipeline publishes, with its formula, its input, and how to
check it by hand. Verified by `tests/test_independent.py`, which recomputes all
of it from the raw files without importing any pipeline code.

## Section 2 — the metric space

X = [−1.0, +1.0]. −1.0 progressive, +1.0 conservative.

Senators and state publics are both placed inside X by the sources below, on the
same dimension, which is what makes the subtraction in section 3 legal.

| quantity | symbol | source | column |
|---|---|---|---|
| senator position | x_i | Voteview `HSall_members.csv` | `nokken_poole_dim1`, congress 119, chamber Senate |
| state public position | s_k | American Ideology Project v2022 `aip_states_ideology_v2022a.tab` | `mrp_ideology`, 2020 wave |
| state estimate error | — | same file | `mrp_ideology_se`, typically 0.037 |
| who holds each seat | — | `legislators-current.json` | joined on bioguide id |

`nokken_poole_dim1` rather than `nominate_dim1`: the latter is a single
career-long constant per member and cannot move. Voteview's file carries 104
Senate rows for the 119th because departed members remain alongside their
replacements, so the roster join reduces it to the 100 seated.

## Section 3 — senator vs. state (Pillar 4)

```
Δ_State(i,k) = |x_i − s_k|
AS_i         = (1 − Δ_State / 2) × 100
```

Worked example, Jon Ossoff (GA):

```
x_i = −0.547      s_k = +0.060
Δ   = |−0.547 − 0.060| = 0.607
AS  = (1 − 0.607 / 2) × 100 = 69.7%
```

The signed difference is retained alongside the absolute value, so a senator on
the opposite side of centre from their own state is distinguishable from one
merely further out in the same direction. Ossoff is the former.

Top five by Δ:

| senator | state | x_i | s_k | Δ | AS |
|---|---|---|---|---|---|
| Rick Scott | FL | +0.926 | +0.002 | 0.924 | 53.8% |
| Ron Johnson | WI | +0.897 | +0.004 | 0.893 | 55.4% |
| Ted Cruz | TX | +0.865 | +0.052 | 0.813 | 59.4% |
| Mike Lee | UT | +0.891 | +0.107 | 0.784 | 60.8% |
| Tommy Tuberville | AL | +0.936 | +0.198 | 0.738 | 63.1% |

Median Δ across all 100 is 0.336, so large gaps are the norm in this chamber;
the ranking identifies who is furthest out by that standard.

## Section 4 — chamber vs. nation (Pillar 5)

```
Ch_m = median{ x_i : i ∈ all 100 seated senators }
US_m = Σ(s_k × pop_k) / Σ(pop_k)        over all 51 state estimates
Δ_US = Ch_m − US_m
```

```
Ch_m = +0.3100
US_m = −0.0288
Δ_US = +0.3388
```

Δ_US > 0, so the chamber sits conservative of the national public.

US_m is population-weighted because the specification asks for the centre of the
national electorate, and the estimates resolve to states rather than individuals.
The distribution of state centres is near-symmetric, so the weighted mean lands
within about 0.01 of the weighted median; it is an approximation and is labelled
as one. DC is included — its residents are part of the national public.

Also reported, since the median senator is not the deciding vote: the 60th
senator from the left (+0.440), the cloture pivot for legislation, and the two
party medians (+0.564 and −0.378).

## Section 5 — committee drift (Pillar 6)

```
CM_j   = mean{ x_i : i ∈ committee j }
Ch_mean = mean{ x_i : i ∈ all 100 senators } = +0.1206
CCD_j  = CM_j − Ch_mean
```

The **mean**, not the median. A median in a ~20-member group split between two
clusters that barely overlap lands in the empty gap between them and moves by up
to 0.342 when a single member leaves — more than the drift it reports. The mean
accounts for the density and extremity of members on both sides; its worst
one-member shift is 0.111, and typically under 0.05.

A drift is reported only when it is at least twice the amount one departure would
move it. Four of nineteen clear that bar:

| committee | n | CM_j | CCD_j | one-drop | ratio |
|---|---|---|---|---|---|
| Environment | 18 | +0.014 | −0.107 | 0.051 | 2.1× |
| Homeland/Govt Affairs | 15 | +0.226 | +0.105 | 0.050 | 2.1× |
| Foreign Relations | 22 | +0.218 | +0.097 | 0.035 | 2.8× |
| Appropriations | 28 | +0.036 | −0.084 | 0.026 | 3.3× |

The pivot-voter alternative (the N/2+1 member) was tested and is not used: on
evenly split panels that member sits on the party boundary and inherits the
median's instability, swinging 0.666 on Budget and 0.602 on Ethics.

Committee rosters are the four-character Senate codes (`SS*` standing, `SL*`
select) from `committee-membership-current.json`; longer codes are subcommittees
and would double-count their parent's members.

## How to reproduce

```bash
./scripts/fetch_data.sh     # three source files, each stamped with date + sha256
./scripts/report.sh         # every figure above
./scripts/report.sh --json  # the same, machine-readable
python3 -m pytest -q        # 57 tests
```

`data/raw/PROVENANCE.tsv` records the date and checksum of every download, since
Voteview revises scores as new votes are recorded.

## Known limits

- **One dimension.** Everything sits on a single progressive–conservative line.
  This holds well for roll-call voting and less well for voters.
- **Senator score error is not propagated.** Voteview publishes no per-member
  standard errors, so it cannot be. The state estimates do carry one (±0.037) and
  it is shown on the demo.
- **Cross-Congress comparisons.** Nokken–Poole is estimated within each Congress,
  so comparing across Congresses carries a caveat.
- **Whole records, not single votes.** x_i summarises a career into one number.
