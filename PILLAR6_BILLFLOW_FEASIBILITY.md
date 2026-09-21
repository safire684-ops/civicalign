# Committee dual-metric framework: what it needs, and what is reachable today

Assessment of the bill-flow architecture (Output Ideology + Gatekeeping Bias
Index) against the data that can actually be obtained. Probed 2026-09-20.

## Metric 1 — Output Ideology (COI)

**Needs:** for each bill reported out of a committee, the ideological cutpoint of
the floor coalition that later passed it.

**Cutpoints: available.** Voteview publishes `S119_rollcalls.csv` with
`nominate_mid_1` (the cutpoint) and `bill_number` on every row. All **897** of
the 119th Senate's roll calls carry both. No API key.

**The problem is sample size.** Of those 897 votes, only **19 are passage votes,
covering 16 distinct bills** across the whole chamber. The rest are cloture (246),
nominations (221), amendments (98), motions to proceed (86) and similar. Split 16
bills across 19 committees and most committees have zero or one — a median over
one bill is not a measurement.

**Also missing:** the link from a bill back to the committee that reported it.
The rollcall file gives `bill_number` but no committee of origin.

**Verdict:** not computable this session in any meaningful form. It becomes
viable late in a Congress once passage votes accumulate, and only with a
bill-to-committee mapping.

## Metric 2 — Gatekeeping Bias Index (GBI)

**Needs:** every bill referred to each committee, its sponsor, and whether it was
reported out. Survival rates by sponsor ideology, then the difference.

**Blocked on access.** The two keyless routes fail:

| Source | Result |
|---|---|
| `api.congress.gov/v3/bill/119/s/1` | **HTTP 403** — requires an API key |
| `govinfo.gov/bulkdata/BILLSTATUS/119/s/...` | **HTTP 404** on the file and the zip; the directory endpoint returns a Bulkdata Service Error page |

**Verdict:** needs a free Congress.gov API key
(api.congress.gov/sign-up). With one, the metric is straightforward: sponsor
ideology already exists in the pipeline, and the referral and "Reported by
Committee" action codes come from the bill endpoint. Sizeable ingest — several
thousand Senate bills per Congress — but no conceptual obstacle.

## What this means for the current committee section

The existing measures stay until the above is obtainable. The framework is right
that a median over a two-party committee is a poor statistic; the pipeline already
carries the mean alongside it for that reason, and the front end shows both.

The bill-flow approach is better than either, because it measures what a committee
*did* rather than who sits on it. It is an access problem, not a method problem.
