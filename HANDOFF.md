# Project handoff — CivicAlign, Pillars 4–6 and Pillar 1 (Stages 2–2.5)

Updated 24 September 2026. Scope: **Pillars 4, 5 and 6** (the live page) and the
deterministic foundation of **Pillar 1** (vote bindings and source packets; no
generated text). Pillars 2, 3 and 7 belong to someone else. The repository, the
live site and the claude.ai copy are in step.

## Where things are

- Live site: https://safire684-ops.github.io/civicalign/ (senator page:
  `/senator-check.html`, methodology report: `/methodology.html`)
- Repo: https://github.com/safire684-ops/civicalign (branch `main`; the weekly
  job commits as `civicalign-bot`)
- Claude.ai copy (manual republish, stylesheet inlined, does not update itself):
  https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj (version 32)
- Shared doc (hand-mirrored, methodology only):
  https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3
- Stage reports (delivered in chat, not in the repo): the Pillar 4 model audit,
  the Pillar 1 Stage 1 architecture, the Stage 2.5 source-context analysis and
  its implementation report. Their conclusions are recorded below.

## The contract, and what moves

**The methodology contract is stable, but the data is dynamic. CivicAlign
rebuilds from current source data every week. Numerical figures, rosters, bill
counts, peer groups and valid same-scale conclusions are expected to change.**
The project is not frozen.

What never changes without a deliberate decision:

1. **No comparison across the two scales.** A senator's score (Voteview,
   Nokken-Poole) and a state's voter estimate (American Ideology Project) are
   separate measurement systems with no validated bridge. Nothing public, and
   nothing in `src/`, subtracts one from the other, compares them with `<`/`>`,
   tests a senator against the state's uncertainty band, or ranks senators by any
   senator-versus-state figure. Valid comparisons stay inside one system: senator
   vs same-caucus peers (Voteview only), senator vs Senate middle, committee vs
   Senate middle, 60-vote point vs Senate middle, state vs national voter
   estimate, seats' vote share vs national vote share (election results only).
2. **The primary senator result is a peer comparison** (`peers.py`): same
   caucus group (Republican caucus; Democratic caucus = Democrats plus the
   Independents whose roster `caucus` field says Democrat; any other party value
   or a missing caucus → status `unsupported`, never a peer), other states only,
   state two-party presidential share (2016/2020/2024 averaged equally, MIT
   Election Lab) within ±4 points, minimum six peers, conclusion published only
   if it agrees at ±2, ±3, ±4 and ±5. Statuses: within / outside_liberal /
   outside_conservative / unstable / insufficient / unsupported. Nothing widens
   the window; peers are listed by state, never ordered by position; no ranking;
   "same party" is never said (Independents are shown as Independents). The page
   only words the backend status (`peerWords` / `peer_words`). The regression
   (`representation.py`) is kept for diagnostics and the methodology's audit
   only: it mostly measured the party split and, in competitive states, its line
   fell where no senator sits. The survey estimate never enters this comparison.
3. **No bill ideology.** A roll-call dividing line says where senators split, not
   what the bill was. A sponsor's record does not make a bill liberal or
   conservative. The page says both.
4. **No dead bills.** A bill not yet formally reported is "not yet sent forward",
   never buried, killed or dead. The Congress is running.
5. **Thresholds.** Two-side bill-flow comparison only with ≥ 25 bills per sponsor
   group; floor-vote split only with ≥ 7 qualifying votes, tagged "Early signal"
   below 15; a committee is flagged (under "More about this committee") as
   sitting well to one side beyond 0.15 underlying units. The Senate-wide
   bill-flow baseline is shown beside each committee's figure and described
   without a cause.
6. **Words follow one rule.** Every same-scale position is described by
   `relWords` (page) / `rel_words` (`build_demo.py`): within 0.05 underlying
   units "near the …", otherwise "on the more liberal/conservative side of
   the …". No graded categories, no significance or "chance" wording, no "most
   liberal", "extreme", "moderate", ranks, scores, grades or verdicts about
   representation.
7. **Meaning before numbers.** Cards lead with a ruler and a sentence.
   Coordinates appear only under "See details" / "More about …", introduced by
   the scale note and labelled "display-scale units"; bill-flow and vote-share
   differences are "percentage points"; the two are never mixed. Default views
   carry no academic terms (Voteview, Nokken-Poole, median, standard error,
   cutpoint, cloture live in How it works, the disclosures and the report);
   unfamiliar terms get a tap-to-open "i" hint (`help()` / `HELP`). The 30-vote
   floor is described as a CivicAlign display rule, not a validity claim.
8. **The four-view interface** and its accessibility (tabs with roving tabindex,
   tracks hidden from screen readers with a spoken sentence, 44px targets).
9. **Evidence without inference.** Each senator card lists their recorded Yea or
   Nay on the most recent passage votes (block `F`, same votes for every senator,
   newest first, Voteview links). No bill description is generated (`summary`
   stays empty until a verified Pillar 1 explanation exists) and no claim is made
   about what the state's voters wanted.
10. **Pillar 1 facts come only from bound official artefacts.** A vote will be
   explained only from its source packet: the Senate's own record, the exact
   text as voted on, the Code in force at the vote, cited Public Laws, the
   matching CRS summary, and for CRA resolutions the bound rule and 5 U.S.C.
   801. No model memory, no browsing, no fallback to today's law, no summary of
   a text the Senate later amended. CRA explanations are limited to the
   resolution's own effect unless the rule is bound and separately validated;
   Senate passage is never described as enactment. No model has been called
   yet.

All ten are enforced by tests that run in the weekly job.

## What the page shows

- **Header.** "Your senators, in the context of your state" / "See how each
  senator's Senate voting record compares with senators in the same caucus group
  representing states that voted similarly in recent presidential elections." /
  "A separate survey estimate of your state's voters appears further down and is
  not directly compared with the senators." / "Senate data updated: <date> ·
  Voter estimate: 2020 wave".
- **Your senators (Pillar 4).** Takeaway ("Both Ossoff's and Warnock's voting
  records fall outside the observed range of comparable senators in the
  Democratic caucus, on the more liberal side."), state picker, "YOUR SENATORS —
  How do their voting records compare with senators in the same caucus group
  from states that voted similarly?", "Georgia recent presidential vote used for
  peer matching: 2016 · 2020 · 2024. Both senators are compared with the same
  pool of other states." Then a card per senator: "Compared with 12 senators in
  the Democratic caucus from 7 other states with similar recent presidential
  voting (i)", SENATE VOTING SCALE with the observed peer range bar, the "Peer
  middle" tick and the senator's dot, the decoder line, the one sentence from
  the backend status, "This compares the senator with senators in the same
  caucus group from states with similar recent presidential voting. It does not
  measure whether the senator agrees with the state's voters.", the vote count,
  then folds: "How were these peers chosen?" (the rule, the state's three shares
  and the average, peer states with shares, peer senators by state, conclusion
  at each window, the numbers), "Recent votes in this record", "Where they sit
  in the Senate" (the demoted Senate-middle ruler). Below the cards: "A peer
  comparison says where a voting record sits among comparable senators in the
  same caucus group. It does not say whether a senator represents, agrees with,
  or matches the state's voters." Then the collapsed "Additional voter context"
  survey fold on the VOTER ESTIMATE SCALE. A senator with fewer than 30 roll
  calls gets the "CivicAlign waits until a senator has at least 30 recorded
  floor votes" card.
- **The Senate (Pillar 5).** Leads with "How Senate seats represent the country's
  vote": a vote-share ruler (Even split, National vote, Average across Senate
  seats) and "The mix of states represented by Senate seats is N percentage
  points more Republican than the national presidential vote", by election under
  a fold. Then "How the Senate votes": Senate middle and 60-vote point ("Why 60?
  Under Senate rules, ending debate on most legislation generally requires
  three-fifths of senators…"; the fold adds that final passage usually requires a
  simple majority and names cloture only afterwards), the state survey
  estimates on their own scale, and the folded "Where familiar senators sit".
- **Committees (Pillar 6).** "Senate committees review bills before many of them
  can go to the full Senate", a four-step legislative flow, then one committee at
  a time against the Senate overall: who sits on it (ruler vs Senate middle);
  what it has sent to the full Senate (bills sent → formally sent forward (i) →
  full Senate "which may vote on it", sponsor definition, "This describes the
  sponsor, not the ideology of the bill", and "Compared with the Senate overall"
  with the Senate-wide difference beside the committee's, in percentage points,
  no cause stated); where the Yes/No split fell on its bills, with the count of
  qualifying votes.
- **How it works.** Plain questions and answers ("What is this site showing me?",
  "How are senators measured?", "What is the voter estimate?", "Are the senator
  and voter measures directly compared?", "Who are the comparable senators?",
  "What is a caucus group?", "What does Senate middle mean?", "Why compare
  Senate seats with the national vote?", "Why are 60 votes shown?", "What does a
  Senate committee do?", "What does sent forward mean?", "Does this tell me
  whether my senator represents me?", "Does this tell me whether a bill is
  liberal or conservative?", "When was this data updated?", "What can't this
  tell me?"), then "Show the technical methodology".
- Footer: eight sources (including the MIT election file) with publisher, link,
  vintage and retrieval date.

## Pillar 1, the concrete receipt: what exists and what does not

Target (from the original directive, still valid): turn "Recent votes in this
record" into a verified receipt: what the Senate was deciding, the exact text
before it, what a Yea and a Nay would do, how this senator voted, and the
official sources behind each line. **Stages 2 and 2.5 are built and supervised.
No summary is generated, no model is called, and the page reads none of it.**
The original v5.0 directive is used only for product intent (cognitive
ergonomics, the concrete receipt, accessibility, source transparency); its
alignment scores, defiance language, rankings, "graveyard" framing and causal
claims are not coming back.

**Stage 2, binding** (`python -m civicalign.explain.bind`, `--offline`; runs in
the weekly job after verify; writes `data/explanations/119/vote_119_S_NNNNN.json`
and `index.json`, tracked, history kept on change).
- Sources: the Senate's own roll-call XML (`sources/senate_votes.py`, senate.gov
  LIS, keyless, keyed by congress / session / clerk vote number), the bill's
  full BILLSTATUS record (`sources/billstatus.py`: text versions with GovInfo
  URLs and dates, actions with recorded-vote links, CRS summaries), Voteview for
  cross-checking. The joint-resolution archives (`sjres`, `hjres`) are
  non-critical snapshot sources. The Congress.gov API is not used.
- Rules (`explain/binding.py`): kind from the official question only
  (`QUESTION_KINDS`; anything else OTHER); PASSAGE_AS_AMENDED only when the
  Senate title says "As Amended" and/or the bill action says "with an amendment"
  and they agree; supported kinds PASSAGE, PASSAGE_AS_AMENDED,
  JOINT_RESOLUTION_PASSAGE. Text selection (`select_text`): the Senate
  engrossment dated the vote (`es`/`cps`, or `eas` for a House bill passed with
  a Senate amendment) is the measure as passed; otherwise the latest pre-vote
  version by precedence (House bills `pcs > rs > rds > rfs > eh`; Senate bills
  `pcs > rs > is`); enrolled and public-law texts never; an amended measure
  without an engrossment is TEXT_PENDING for 45 days then TEXT_AMBIGUOUS; floor
  amendments before a vote with no engrossment, or two engrossments, are
  ambiguous; the GovInfo file's `bill-stage` must match. CRA metadata from the
  two official title forms only. The receipt scaffold (headings, what Yea and
  Nay mean, next step) is fixed per kind.
- Verification: Senate record exists; congress/session/vote number, date,
  question, tallies and threshold match Voteview; every member's vote matches
  (LIS id → bioguide from the roster; former members by exact last name, first
  name, state and party against Voteview's member file, failing closed);
  measure id matches; the bill status links this vote. Statuses VERIFIED /
  BOUND_AWAITING_BILLSTATUS / FAILED / UNAVAILABLE. Today: 899 roll calls
  classified; 54 bound (19 bill passage, 35 joint resolution), all VERIFIED and
  TEXT_BOUND; 27 are CRA.

**Stage 2.5, source context and packets** (`python -m civicalign.explain.context`,
`--offline`, `--only=S2,HR4`; an offline job, NOT in the weekly workflow because
the title archives are slow; the workflow only re-verifies the tracked records).
- References: structured `external-xref` citations from the voted XML (no prose
  regex for the Code); amendatory status from the innermost enclosing block.
- Selection policy (`select_sections`): sections cited in amendatory
  instructions, else all cited sections, capped at 12; above the cap, and for
  voted texts over 30,000 words, the context stays PENDING until a
  large-measure policy exists.
- The Code in force (`sources/uscode.py`): OLRC release points, one per enacted
  Public Law. Rule: the latest release point on or before the vote **whose
  archive for the title is published**; every release point between it and the
  vote is checked against OLRC's classification table (`tbl119pl_1st/2nd.htm`),
  and the context is ambiguous if any intervening law touched a cited section.
  Never a later release point, never today's law. Sections are extracted
  byte-exact by USLM identifier (OLRC uses an en-dash in hyphenated numbers;
  both spellings match) and hashed. Release points 119-23 and 119-26 publish no
  archives; neither does 118-274, the one in force for S.5.
- Public Laws (`sources/publaw.py`, GovInfo USLM): a cited section is extracted;
  a whole-law or division citation is identified and hashed only, "not to be
  described". Laws before the USLM era (e.g. 91-672, 104-172) are not served
  and stay pending.
- CRS summary: version, date and relationship MATCHED / EARLIER_SAME_TEXT /
  PRE_AMENDMENT / UNKNOWN; only the first two go into a packet.
- CRA (`sources/federal_register.py`): the rule bound by citation through the FR
  API (client User-Agent, `per_page=1000` with pagination, day query by start
  page; GovInfo issue XML is the documented fallback). Document type recorded
  (four bound documents are Notices deemed rules). GAO determinations
  (`GAO_RULE_DETERMINATION`) identified from the resolution text: opinion date,
  Congressional Record date and pages; not retrieved. 5 U.S.C. 801 sourced from
  the Code in force. Modes `resolution_only` / `rule_bound`; rule content is
  withheld from packets (`content_included: false`) until the CRA validation
  cohort passes.
- Output: one tracked context record per vote (`data/explanations/119/context/`,
  plus `index.json`) and, for READY states, a packet (`packets/`) whose every
  `content` field is a byte-exact copy of a hashed artefact. Volatile fetch
  messages are kept out of tracked records, so an offline rerun writes nothing
  when nothing changed. Completeness COMPLETE / LIMITED / PENDING / AMBIGUOUS →
  generation READY_FOR_GENERATION / READY_WITH_LIMITS / SOURCE_CONTEXT_PENDING /
  SOURCE_CONTEXT_AMBIGUOUS. Today: 12 ready (S.J.Res.10, 37, 49, 71, 77, 81, 88;
  H.J.Res.142; S.2; H.R.4; S.331; H.R.7148), 27 ready with limits (all CRA), 13
  pending (large texts or pre-USLM laws), 2 ambiguous (S.5 by the in-force rule
  itself; H.R.6938 by intervening laws).
- Raw cache: `data/raw/explanations/` (Senate XML, texts, title archives,
  release-point pages, classification tables, law XML, FR queries and documents;
  about 360 MB, ignored by git) with `MANIFEST.json`; immutable artefacts are
  served from the cache once recorded.

**Decisions on record.** First Maker/Checker cohort: the 8 self-contained
resolutions (S.J.Res.10, 37, 49, 71, 77, 81, 88; H.J.Res.142) + S.2 + H.R.4, all
READY with COMPLETE packets. S.5 stays ambiguous; do not solve it with current
law. CRA explanations wait for a separate validation cohort (one rule-bound,
one GAO-deemed) and are never published before it passes.

**Not built.** Maker, Checker, the evaluation run, any UI change, the
large-measure section-selection policy, Statutes at Large for pre-USLM laws,
retrieval of GAO opinions from the Congressional Record. When Stage 3 starts:
the Maker runs sandboxed on the packet alone; the Checker uses a different
prompt (ideally a different model) from the Maker; model provider, prompt
versions and iteration counts go into the packet's provenance; only `verified`
summaries may reach block `F`; the deterministic checks in the Stage 1 design
(identity, hash, Yea/Nay semantics, every effect cited, no stale summary after
a source change) gate publication.

## How the weekly update works

`.github/workflows/update.yml` (Mondays 11:00 UTC, or "Run workflow"), mirrored
by `scripts/update.sh`. Every step is a gate; a failure fails the Action, commits
nothing, and leaves the previously verified site live.

1. **Fetch as one snapshot** (`python -m civicalign.agents`): all ten critical
   sources (Voteview members, roll calls, votes; congress-legislators roster and
   committee membership; American Ideology Project state estimates; Census
   populations; Senate and House bill-status archives; MIT election results) are
   downloaded and validated into staging; if any fails, nothing is installed and
   the run stops. Two non-critical sources (the joint-resolution archives) keep
   their previous file on failure. Change detection is by content (zip members,
   not archive timestamps). `data/raw/SNAPSHOT.json` (tracked) records per
   source: URL, file, bytes, SHA-256, content key, changed flag, content-changed
   date, checked date, vintage. `PROVENANCE.tsv` logs content changes.
2. **Verify** (`python -m civicalign.agents.verify`): 100 seats, ≤ 2 senators per
   state, scored senators and committee members on the current roster, record
   counts sane, no source shrank > 30 %.
3. **Bind** (`python -m civicalign.explain.bind`): Pillar 1 Stage 2; a network
   failure leaves previous bindings in place.
4. **Data tests** (`pytest`, excluding the page and whitepaper tests).
5. **Rebuild** (`python -m civicalign.build_demo`): the page's data blocks and
   `demo/methodology.html` from the template.
6. **Page tests** (`tests/test_published_pages.py`): the public-claim contract.
7. **Supervisor** (`python -m civicalign.agents.supervisor`): separate code
   re-reads the raw files and reproduces 36 checks: scores, middle, 60th vote,
   survey estimates, bill counts, every state's three-cycle two-party share and
   the national shares, the seats-minus-nation figure, the retired line (own OLS
   from sums; diagnostics only), every senator's peer group, range, status and
   per-window sensitivity with its own loop, the caucus grouping from the roster,
   every senator's vote on the published floor votes, every Pillar 1 binding
   (identity, tallies, members, measure, recorded-vote link, hashes, text
   version rule and stage), every context record and packet (references,
   selection, in-force archive, fragment hashes, packet hashes, CRS relationship,
   CRA mode, generation state, no generated field), and that the payload carries
   no cross-scale, ranking or unverified-summary field.
8. **Commit** only if the pages, provenance or bindings changed (a check-stamp-only
   snapshot change is discarded). **Publish** only if every step passed.

Roster changes flow through the roster join; a senator with fewer than 30 roll
calls gets the waiting card, never a predecessor's score. The seat
de-duplication guard (104 Voteview rows for 100 seats) is in
`sources/voteview.py`.

## Routine tasks

- Refresh the whitepaper's figures after data moves (the job only warns):
  `PYTHONPATH=src python -m civicalign.whitepaper`, then commit `WHITEPAPER.md`.
- Republish the claude.ai copy: inline `demo/civicalign.css` into
  `demo/senator-check.html` in place of the `<link>` tag, point
  `href="methodology.html"` at the live URL, and publish to the artifact URL above.
- Rebuild Pillar 1 context offline after a new binding or a source change:
  `PYTHONPATH=src python -m civicalign.explain.context` (the first run fetches
  archives; later runs use the cache), then run the supervisor and commit
  `data/explanations/`.
- Run everything locally: `scripts/update.sh` (uses `.venv` if present).
- Read the figures on the command line: `PYTHONPATH=src python -m civicalign`
  (`--json` for the export; each section is labelled with its scale).
- After any deploy, compare the live page with the repo byte for byte before
  reporting it live.

## Code map

- `src/civicalign/pipeline.py` — `run()` builds the `Report`.
- `peers.py` — the published Pillar 4 rule (`WINDOW`, `MIN_PEERS`, `WINDOWS`,
  `caucus_group`, `peer_comparisons`, `status_from`). `representation.py` — the
  retired regression (`Fit`, `Representation`), diagnostics only, plus the
  Pillar 5 `ChamberLean`. `uncertainty.py` — analytic OLS errors, leverage,
  prediction band. `receipts.py` — `FloorVote`, `recent_floor_votes` (fixed
  neutral rule; `summary` is the Pillar 1 integration point and stays empty).
- `alignment.py` — `Positions`, senator score and state estimate side by side,
  nothing derived. `chamber.py`, `committees.py`, `output_ideology.py`,
  `gatekeeping.py`, `landmarks.py`.
- `build_demo.py` — data blocks `V M X P G` plus `R` (peers), `E` (seats vs
  nation), `F` (recent passage votes with every senator's Yea/Nay); report
  placeholders including `regression_audit`; the sources list; wording rules
  (`rel_words`, `peer_words`).
- `agents/` — `base.py` (snapshot, `sha256_bytes`), `sources.py` (agents with
  validators and vintages), `verify.py`, `supervisor.py`. `whitepaper.py` —
  figure refresher.
- `explain/` — `binding.py` (rules), `bind.py` (Stage 2 runner), `context.py`
  (Stage 2.5 runner and packet builder), `fetch.py` (cache with manifest,
  retries, immutable entries). `sources/senate_votes.py`, `sources/billstatus.py`,
  `sources/uscode.py`, `sources/publaw.py`, `sources/federal_register.py`.
  `config.py` holds the archive and directory paths.
- Tests: `test_published_pages.py` (the public contract: G1–G6, UX guarantees,
  presentation guarantees, V1–V20), `test_perspective.py` (product hierarchy),
  `test_peers.py` (the peer rule, caucus grouping, thresholds), `test_binding.py`
  and `test_context.py` (Pillar 1), `test_update_chain.py`, `test_supervisor.py`,
  `test_independent.py`, `test_floor_votes.py`, `test_math.py`,
  `test_regressions.py`, `test_representation.py`, `test_uncertainty.py`,
  `test_whitepaper.py`. 249 pass as of this handoff; supervisor 36/36; verify
  12/12.

## Open items

- Pillar 1 Stage 3 and after: Maker/Checker on the ten-case cohort, then the
  CRA validation cohort, then a large-measure section-selection policy (13
  votes pending on it), Statutes at Large for pre-USLM laws, GAO opinion
  retrieval from the Congressional Record (GovInfo CREC by date and page).
- The peer rule leaves three senators without a comparison (both Wyoming
  senators; Maine's Republican) and nine with window-dependent conclusions; the
  page says so for each.
- The 2024 survey wave does not exist; 2020 is the newest. The page says so.
- Two audits disagree on committee median vs mean; the median is shown and the
  mean is in fine print. Not resolved.
- Voteview publishes no standard errors for senator scores, so only the survey
  side has an uncertainty band.
- The claude.ai copy and the shared doc do not update themselves.
- Rotate the Congress.gov API key that was pasted into chat earlier; it is not
  used anywhere and must never be committed.
- federalregister.gov's HTML pages are bot-blocked from some networks; the API
  works with a client User-Agent. uscode.house.gov serves archives slowly
  (about 60 KB/s), which is why the context build is an offline job.
- Enter/Space on tabs and circles could not be driven from the browser pane
  (native links and buttons; worth a press on a real keyboard). Headless Chrome
  enforces a 500px minimum viewport; phone screenshots use the DevTools-protocol
  emulation script pattern.

## Decision history, condensed

- Sept 2026, early rounds: Pillars 4–6 built on real data; GitHub Actions and
  Pages automation; four-view interface; navigation and phone fixes.
- Vote examples: the "state side of a vote" inference removed, then the vote
  example removed from the senator view; later restored as plain recorded votes
  with no inference (block `F`).
- Methodology cleanup: scales separate; splits are not bill ideology; pending not
  dead; distinct bills vs referrals; the senator-vs-survey alignment band
  softened, then removed altogether; obsolete cross-scale metrics (gap, score,
  rank, crosses_over, apportionment_skew, cnd, vs_public) deleted from the
  backend, not hidden.
- 0-to-100 display scale (score × 50 + 50); numbers moved under details with the
  scale note and "display-scale units"; one wording rule, words before numbers,
  no ranking language; graded words dropped (direction only); average-voter
  pass (tap-to-open hints, bill flow as steps, Yes/No-split ruler, FAQ);
  comprehension pass (scale labels on every ruler, legislative flow,
  three-fifths wording with cloture named afterwards, freshness line).
- Weekly chain hardened: all-or-nothing snapshot, verify step, gated publish,
  content-based change detection, provenance with vintage and retrieval dates.
- 23 Sept: the product correction made a state-relative election regression the
  primary Pillar 4 result, the Senate view lead with seats vs nation, and
  committees read against the Senate-wide baseline (blocks R/E/F). The same
  day's statistical audit found the regression measured the party split and
  produced a phantom middle in competitive states, so it was retired from the
  page in favour of the same-caucus peer comparison (window ±4, minimum six,
  cross-window check), with the survey estimate as separate context; "same
  party" was corrected to caucus groups with fail-closed grouping and the
  30-vote wording became a display rule. Version 31 is the Pillar 4 baseline.
- 23–24 Sept: Pillar 1 Stage 1 design; Stage 2 bindings (54 votes verified
  against Senate.gov, GovInfo and Voteview; bind step added to the weekly job);
  Stage 2.5 source context and packets (12 ready, 27 limited, 13 pending, 2
  ambiguous); first cohort and CRA rules decided as above. No page change in
  any Pillar 1 stage; the live page stayed byte-identical to the repo.

Reference reports from earlier rounds (Gemini): Pillar 6 dual-metric framework
https://gemini.google.com/share/b75123b297db?skid=4798bd3c-9d90-4f8a-a251-00429acbda75 ;
system audit and execution directives
https://gemini.google.com/share/82bd4fe17a76?skid=e8601a35-0fb0-4b8d-b6a8-f4b2775b7142 .
Later reports asked for cross-scale claims, invented bill positions and
AI-written bill impacts; those were declined and the reasons are in the commit
messages.
