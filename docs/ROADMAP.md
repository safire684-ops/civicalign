# CivicAlign audit, plan and checklist

Status as of November 2, 2026. This tracks [issue #5](https://github.com/safire684-ops/civicalign/issues/5). A box is
checked only when the work is implemented, tested and independently verified. "On branch" means it passed on the
branch and isn't live until the owner approves a merge.

## What already updates by itself

| Data | Source | Today |
|---|---|---|
| Senator scores, roll calls, senator votes | Voteview | Automatic, daily |
| Seated senators, committee rosters and names | unitedstates/congress-legislators | Automatic, daily |
| Bill status, passage, enactment, policy areas (S, H.R., S.J.Res., H.J.Res.) | GovInfo bulk files | Automatic, daily |
| State survey estimates | American Ideology Project | Automatic check; the survey itself changes rarely |
| State populations | Census | Automatic check |
| Senate roll-call XML | senate.gov | **Blocked since October 2026.** 55 stored copies from Oct 9 |
| Official vote lists and change-of-vote notices | Congressional Record on GovInfo | **New, on branch** |
| Plain-language vote meanings, bill facts, importance, nominations, committee votes | 50degrees export | **Manual.** Importer on branch, waiting for a publisher |

## The 50degrees dependency

The export comes from a separate pipeline (`civicalign export 119`) that isn't in this repository. Nothing here can
produce it, and no other feed is substituted for it. To finish automation, its owner has to publish these files at a
stable https address, with this `manifest.json` beside them, then set `CIVICALIGN_DROP_URL` as a repository variable
and, if it needs a key, `CIVICALIGN_DROP_TOKEN` as a secret:

    {"congress": 119, "generated_at": "<ISO time>", "files": {"meta.json": "<sha256>", "senators.json": "<sha256>", "votes.json": "<sha256>",
     "positions.json": "<sha256>", "bills.json": "<sha256>", "committee_votes.json": "<sha256>", "nominations.json": "<sha256>", "README.md": "<sha256>"}}

## Plan, in priority order

1. **Automatic updates.** Official checks that don't depend on 50degrees, the importer, monitoring.
2. **Bill explanations.** Build official summaries from GovInfo's bill-summary files, then evidence-checked explanations.
   A Congress.gov API key would add nominations, amendments and hearings.
3. **Issue positions.** Add change over time and differences from party. No ideological score per issue.
4. **Coverage.** Review PR #2 separately, then bills with no floor vote, resolutions, amendments, hearings.
5. **State comparison.** Research first. Stays unavailable unless a validated method exists.
6. **Exploration.** Senator comparison, trends, state map, search, shareable links, accessibility, real phone tests.

## Checklist

### 1. Automatic updates
- [ ] Voteview votes checked against an official source each day: *on branch; 915 of 915 roll calls match*
- [ ] The 18 provisional votes checked against official lists: *on branch; all 18 match. Plain-language meanings still need a drop*
- [ ] Official vote corrections detected automatically: *on branch; finds exactly the 3 documented changes*
- [ ] New votes noticed when the Record has them before Voteview: *on branch*
- [ ] A bad, stale or shrinking drop can't replace a good one: *on branch; tested with synthetic drops*
- [ ] Missing, stale and conflicting data reported on the site and in each run: *on branch*
- [ ] An alert opens when a run fails or data conflicts: *on branch; the live issue step can only run on `main`*
- [ ] Separate daily check of the live site: *on branch; first runs after merge*
- [ ] **New drops import unattended: BLOCKED until a publisher exists**
- [ ] A scheduled run on `main` passes on this code

### 2. Bill explanations
- [ ] Official summaries for bills beyond the 40 with facts: *on branch `voter-navigation`; 107 of 128 bills show the Congressional Research Service summary, the rest say "Not available"*
- [ ] Claim-level checks, with source excerpts and bill text links
- [ ] Yes/No meanings for the 18 newest votes
- [ ] Held and unavailable parts labelled

### 3. Issue positions
- [ ] Differences from party and Senate shown vote by vote
- [ ] Change over time, where the data supports it
- [ ] Every claim linked to its evidence

### 4. Coverage
- [ ] PR #2 reviewed and independently recounted
- [ ] Bills with no floor vote
- [ ] Resolutions and amendments
- [ ] Hearings and committee actions
- [ ] No individual committee votes shown unless a source gives them

### 5. State comparison
- [ ] Literature review of methods placing senators and the public on one scale
- [ ] Decision recorded: validated, issue by issue, or still unavailable

### 6. Exploration
- [ ] Senator-to-senator comparison
- [ ] Historical trends
- [ ] State map
- [ ] Better bill search and filters
- [ ] Senators filters and sorting (party, position, Census region, state, committee): *on branch `voter-navigation`*
- [ ] Shareable links to findings: *on branch `voter-navigation` for Senators filters, committee order and bill tabs*
- [ ] Accessibility review, real phone test, load test

## Voter navigation (branch `voter-navigation`, 2026-11-08)

Built on top of `automatic-data-updates` (not yet merged) with today's `main` merged in. Nothing here is merged or deployed.

| Requirement | State |
|---|---|
| Senators sorted by state, then last name | Done and tested |
| Filters: party, position on Voteview's scale, Census region, state, committee; combine and reset; shareable link | Done and tested |
| Sort: state, last name, party, most liberal, most conservative | Done and tested |
| Profiles reachable from search, committee members, bill sponsors, Senate chart | Done |
| Committee member opens the full profile, with a way back; a highlighted member can be cleared | Done and tested |
| Committees sorted alphabetically or by midpoint, with a marker under each and an explanation | Done and tested |
| State vs Senator card removed from the profile | Done; the data still says NOT_AVAILABLE and the supervisor still checks it |
| Voting position shown on a labelled 0 to 100 scale, never called a percentage | Done and tested |
| "How to read this" on the profile and on About | Done |
| Recent votes open the bill's official summary and checked facts | Done |
| Bill page with Overview, Voting Record, Explanation, Sources | Done and tested |
| Sponsor and party, official summary, latest action, short title for every bill | Done for all 128; summaries for 107 |
| What a bill would change | Only where checked facts exist (40 bills); "Not available" otherwise |
| Net worth and stocks | **Blocked:** see `docs/FINANCES.md` |
| Last updated date on every page | Done |
| Bill records, summaries and explanations monitored in Data checks | Done |
| Senator photos saved with the site, checked, and shown in search, profiles, committee grids and the Senate view | Done and tested: 103 of 104 senators; Alan Armstrong (seated 2026-03-24) has no official photo at any source yet, so initials show and each run asks again |

Every bill's sponsor, summary, latest action and short title come from GovInfo's bill-status files, which the
pipeline already downloads each day (three resolution archives were added so all 128 measures are covered). The
supervisor re-reads them with its own code and fails the run if the site differs.
