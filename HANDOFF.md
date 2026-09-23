# Project handoff — CivicAlign, Pillars 4–6

Updated 23 September 2026. Scope is **Pillars 4, 5 and 6 only** (math-spec
sections 2–5). Pillars 1–3 and 7 belong to someone else. Everything described
here is published and the repository, the live site and the claude.ai copy are
in step.

## Where things are

- Live site: https://safire684-ops.github.io/civicalign/ (senator page:
  `/senator-check.html`, methodology report: `/methodology.html`)
- Repo: https://github.com/safire684-ops/civicalign (branch `main`; the weekly
  job commits as `civicalign-bot`)
- Claude.ai copy (manual republish, stylesheet inlined, does not update itself):
  https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj (version 24)
- Shared doc (hand-mirrored, methodology only):
  https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3

## The contract, and what moves

**The methodology contract is stable, but the data is dynamic. CivicAlign
rebuilds from current source data every week. Numerical figures, rosters, bill
counts and valid same-scale conclusions are expected to change.** The project is
not frozen.

What never changes without a deliberate decision:

1. **No comparison across the two scales.** A senator's score (Voteview,
   Nokken-Poole) and a state's voter estimate (American Ideology Project) are
   separate measurement systems with no validated bridge. Nothing public, and
   nothing in `src/`, subtracts one from the other, compares them with `<`/`>`,
   tests a senator against the state's uncertainty band, or ranks senators by any
   senator-versus-state figure. A direct alignment measure requires a validated
   statistical bridge; CivicAlign does not have one. Valid comparisons stay inside
   one system: senator vs Senate middle, committee vs Senate middle, 60-vote point
   vs Senate middle, state vs national voter estimate, state vs state.
2. **No bill ideology.** A roll-call dividing line says where senators split, not
   what the bill was. A sponsor's record does not make a bill liberal or
   conservative. The page says both.
3. **No dead bills.** A bill not yet formally reported is "not yet sent forward",
   never buried, killed or dead. The Congress is running.
4. **Thresholds.** Two-side bill-flow comparison only with ≥ 25 bills per sponsor
   group; floor-vote split only with ≥ 7 qualifying votes, tagged "Early signal"
   below 15; a committee is flagged (under "More about this committee") as sitting
   well to one side beyond 0.15 underlying units.
5. **Words follow one rule.** Every same-scale position is described by
   `relWords` (page) / `rel_words` (`build_demo.py`): within 0.05 underlying
   units "near the …", otherwise "on the more liberal/conservative side of
   the …". Words give the direction, the chart shows how far, the number is
   under details. No graded categories ("somewhat", "clearly" were removed
   23 Sept 2026); no "most liberal", "extreme", "moderate", ranks or scores.
6. **Meaning before numbers.** Cards lead with a ruler and a sentence.
   Coordinates appear only under "See details" / "More about …", introduced by
   the scale note ("a position on that line; not a percentage, a vote total, an
   approval rating or a grade") and labelled "display-scale units". Bill-flow
   differences are "percentage points". The two are never mixed. Default views
   carry no academic terms (Voteview, Nokken-Poole, median, standard error,
   cutpoint, cloture and so on live in How it works, the disclosures and the
   report); unfamiliar terms get a tap-to-open "i" hint (`help()` / `HELP`).
7. **The four-view interface** and its accessibility (tabs with roving tabindex,
   tracks hidden from screen readers with a spoken sentence, 44px targets).

All seven are enforced by tests that run in the weekly job.

## What the page shows

- **Header.** One purpose sentence: "Use this to see where your senators sit
  within the Senate and where your state sits among voter estimates."
- **Your senators.** State picker with an orientation line ("Below: how each of
  Georgia's senators votes compared with the Senate, then where Georgia's voters
  are estimated to sit."). Each senator card: "How Ossoff votes, compared with the
  Senate middle (i)", a ruler (MORE LIBERAL ← → MORE CONSERVATIVE, Senate-middle
  tick, senator dot), "Ossoff's voting record is on the more liberal side of the
  Senate middle.", "Based on Ossoff's 844 Senate votes during the current
  Congress." One state card, "Estimated political position of Georgia voters":
  "Voter estimate, compared with the national voter estimate (i)", ruler with
  "Shaded area = estimated range.", the sentence, "Academic survey estimate,
  American Ideology Project, 2020 wave." Under details: what the estimate is and
  is not (not a poll, election result, registration, approval rating), then the
  numbers. Below the cards: "These show two different things: how the senator
  votes within the Senate, and where the state's voters are estimated to sit among
  voter estimates. They are not directly compared." "Where familiar senators sit" (folded) puts
  the middle Democrat, middle Republican, Senate middle and eight named senators on
  the senators' line.
- **The Senate.** "This shows the middle of current Senate voting patterns and
  where the 60-vote point falls." Senate middle and 60-vote point on the senators'
  line ("The 60-vote point sits on the more conservative side of the Senate
  middle. (i)" / "Why 60? Many Senate actions need 60 votes to move forward.");
  the state estimates on their own line with every state as a faint tick. Folded:
  why it matters (two senators per state; "not every bill does"; cloture named
  after the explanation), all 100 circles coloured by side of the Senate middle,
  the numbers.
- **Committees.** "Senate committees review bills before many of them can go to
  the full Senate. Pick a committee to see who is on it, what it has sent forward,
  and what happened on Senate votes about those bills." One committee at a time,
  three questions: who is on it (ruler, sentence); what it has sent to the full
  Senate (a three-step flow: bills sent to this committee → formally sent forward
  (i) → full Senate; "N still in committee … not dead"; "Sponsor = the senator who
  introduced the bill"; bars grouped by sponsor record; "Limited data" below 25 per
  group); what happened when those bills reached the full Senate ("On Senate votes
  involving these bills, this shows where the Yes and No sides divided", a ruler
  with the Yes/No split against the Senate middle, "It does not tell us whether the
  bill itself was liberal or conservative", "Based on 28 Senate votes on these
  bills" or "Only 7 … too little data for a strong conclusion", numbers under
  "More about these votes").
- **How it works.** Nine plain questions and answers (where the senator and
  voter information comes from, what the Senate middle is, whether the two are
  compared, whether this says if a senator represents you, whether a bill is
  liberal or conservative, whether "still in committee" means dead, what it cannot
  tell you, where population and bill figures come from), the weekly-check line,
  link to the report, and "Show the technical methodology" (two lines, why
  separate, raw values, same-scale arithmetic, sources with exact files).
- Header: "Data updated <date>", with the note that the survey wave is 2020.
  Footer: sources with publisher, link, vintage and retrieval date.

## How the weekly update works

`.github/workflows/update.yml` (Mondays 11:00 UTC, or "Run workflow"), mirrored
by `scripts/update.sh`. Every step is a gate; a failure fails the Action, commits
nothing, and leaves the previously verified site live.

1. **Fetch as one snapshot** (`python -m civicalign.agents`): all ten sources are
   downloaded and validated into staging; if any critical source fails, nothing
   is installed and the run stops. All ten are critical: Voteview members, roll
   calls, votes; congress-legislators roster and committee membership; American
   Ideology Project state estimates; Census populations; Senate and House
   bill-status archives; MIT election results. Change detection is by content
   (zip members, not archive timestamps). `data/raw/SNAPSHOT.json` (tracked)
   records per source: URL, file, bytes, SHA-256, content key, changed flag,
   content-changed date, checked date, vintage. `PROVENANCE.tsv` logs content
   changes. On a fresh checkout the raw files are absent; the comparison uses the
   committed snapshot's keys, so re-downloads of identical content are not changes.
2. **Verify** (`python -m civicalign.agents.verify`): 100 seats, ≤ 2 senators per
   state, scored senators and committee members on the current roster, record
   counts sane, no source shrank > 30 %.
3. **Data tests** (`pytest`, excluding the page and whitepaper tests).
4. **Rebuild** (`python -m civicalign.build_demo`): regenerates the page's data
   blocks and `demo/methodology.html` from the template.
5. **Page tests** (`tests/test_published_pages.py`): the public-claim contract.
6. **Supervisor** (`python -m civicalign.agents.supervisor`): separate code
   re-reads the raw files and reproduces 18 figures, and checks the payload
   carries no cross-scale field.
7. **Commit** only if the pages or the provenance log changed (a check-stamp-only
   snapshot change is discarded). **Publish** only if every step passed.

Roster changes (resignations, appointments, deaths, new members) flow through
the roster join; a senator with fewer than 30 roll calls gets the
"Insufficient data" card, never a predecessor's score. The seat de-duplication
guard (104 Voteview rows for 100 seats) is in `sources/voteview.py`.

## Routine tasks

- Refresh the whitepaper's figures after data moves (the job only warns):
  `PYTHONPATH=src python -m civicalign.whitepaper`, then commit `WHITEPAPER.md`.
- Republish the claude.ai copy: inline `demo/civicalign.css` into
  `demo/senator-check.html` in place of the `<link>` tag, point
  `href="methodology.html"` at the live URL, and publish to the artifact URL above.
- Run everything locally: `scripts/update.sh` (uses `.venv` if present).
- Read the figures on the command line: `PYTHONPATH=src python -m civicalign`
  (`--json` for the export; each section is labelled with its scale).

## Code map (Pillars 4–6)

- `src/civicalign/pipeline.py` — `run()` builds the `Report`.
- `alignment.py` — `Positions`: senator score and state estimate side by side,
  nothing derived. `chamber.py` — median, 60th vote, party medians; carries the
  national estimate for the voter chart only. `committees.py`,
  `output_ideology.py`, `gatekeeping.py`, `landmarks.py`, `receipts.py` (the vote
  example still exists in the pipeline and JSON, not on the page).
  `representation.py` — method A, the election-result regression (answers "how
  does this senator compare with the pattern typical of states that vote
  similarly?"), kept separate from the page.
- `build_demo.py` — data blocks `V M X P G` (no cross-scale field), report
  placeholders, sources list, wording rule.
- `agents/` — `base.py` (snapshot), `sources.py` (ten agents with validators and
  vintages), `verify.py`, `supervisor.py`. `whitepaper.py` — figure refresher.
- Tests: `test_published_pages.py` (contract: no cross-scale arithmetic G1–G6,
  no bill ideology, no dead bills, twelve UX guarantees, ten presentation
  guarantees, fifteen average-voter guarantees V1–V15), `test_update_chain.py`
  (snapshot, gates, provenance),
  `test_supervisor.py`, `test_independent.py` (raw-file recomputation),
  `test_floor_votes.py`, `test_math.py`, `test_regressions.py`,
  `test_representation.py`, `test_uncertainty.py`, `test_whitepaper.py`.
  170 pass as of this handoff; supervisor 18/18; verify 12/12.

## Open items

- The 2024 survey wave does not exist; 2020 is the newest. The page says so.
- Two audits disagree on committee median vs mean; the median is shown and the
  mean is in fine print. Not resolved.
- Voteview publishes no standard errors for senator scores, so only the survey
  side has an uncertainty band.
- The claude.ai copy and the shared doc do not update themselves.
- Rotate the Congress.gov API key that was pasted into chat earlier; it is not
  used anywhere and must never be committed.
- Enter/Space on tabs and circles could not be driven from the browser pane
  (elements are native links and buttons; worth a press on a real keyboard).
- Headless Chrome enforces a 500px minimum viewport; phone screenshots need the
  DevTools-protocol emulation script pattern.

## Decision history, condensed

- Sept 2026, early rounds: Pillars 4–6 built on real data; automation via
  GitHub Actions and Pages; four-view interface; navigation and phone fixes.
- Vote examples: the "state side of a vote" inference was removed, then the
  vote example itself was removed from the senator view (bills are not marked
  on the senators' line).
- Methodology cleanup: scales described as separate; splits are not bill
  ideology; pending not dead; distinct bills vs referrals; the alignment band
  label softened, then the comparison removed altogether.
- 0-to-100 display scale (score × 50 + 50); later, numbers moved under
  details with the scale note and "display-scale units".
- Backend: obsolete cross-scale metrics (gap, score, rank, crosses_over,
  apportionment_skew on the survey scale, cnd, vs_public) deleted, not hidden.
- Weekly chain hardened: all-or-nothing snapshot, verify step, gated publish,
  content-based change detection, provenance with vintage and retrieval dates.
- Presentation: one wording rule, words before numbers, percentage points vs
  display-scale units, no ranking language. 23 Sept: graded words dropped
  (direction only), purpose sentence in the header, "Estimated political
  position of <State> voters", committee questions reworded in plain English.
  Later that day, the average-voter pass: tap-to-open hints for Senate middle,
  national voter estimate, 60-vote point and sent forward; bill flow as three
  steps; a Yes/No-split ruler; How it works as questions and answers; academic
  terms and coordinates moved behind details; no engine change.

Reference reports from earlier rounds (Gemini): Pillar 6 dual-metric framework
https://gemini.google.com/share/b75123b297db?skid=4798bd3c-9d90-4f8a-a251-00429acbda75 ;
system audit and execution directives
https://gemini.google.com/share/82bd4fe17a76?skid=e8601a35-0fb0-4b8d-b6a8-f4b2775b7142 .
Later reports asked for cross-scale claims, invented bill positions and
AI-written bill impacts; those were declined and the reasons are in the commit
messages.
