# Project handoff — CivicAlign, Pillars 4–6

Updated 22 September 2026. Scope is **Pillars 4, 5 and 6 only** (math-spec
sections 2–5). Pillars 1–3 and 7 belong to someone else.

## Status in one line

Five methodology concerns fixed in wording and counts (22 September 2026,
published): (1) the page and report no longer claim the survey and senator scales
are the same; they say the two rulers were built separately and every distance is a
rough comparison; (2) committee "output" is described as where the Senate split on
its bills, explicitly not bill ideology; (3) bills not yet reported are "pending" or
"not yet sent on", never buried, dead or survivors; (4) Senate-wide totals count
distinct bills (5,333) with referrals (5,368) named separately, via new Report fields
`bills_referred_unique` / `bills_reported_unique`; (5) the alignment badge is "Too
close to tell apart" with the band described as one standard error and "not the same
as agreement". The 1-SE threshold itself is unchanged.

Earlier the same day (published): the senator view shows **no
bills**. Each card explains the gap in plain terms from the page's own data: how
far it is (share of the scale, the distance between two familiar senators, and
against the typical senator's gap), where the senator sits against their party's
middle and the other 99 senators, where the state sits against the public and the
other states, and what each number is made of. The track and the "Explore the
scale" ruler carry landmarks (middle Democrat, middle Republican, Senate middle,
public, familiar senators). The page states it cannot say which issues make up
the difference and never guesses.

Everything below is **published** as of 22 September 2026: the four-view layout,
the vote-example correction and the presentation safeguards are on the live site,
`origin/main` is at the same commit, and the claude.ai copy (version 12) was
rebuilt from the same page with the stylesheet inlined. The weekly workflow ran
green (`update` and `publish` both succeeded) and only re-dated the report.

## Where things stand

- Live site: https://safire684-ops.github.io/civicalign/
- Repo: https://github.com/safire684-ops/civicalign — `origin/main` matches local `main`.
- Claude.ai copy (manual republish, CSS inlined; does not update itself): https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj
- Shared doc (hand-mirrored): https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3

## The four-view layout (published)

Three files changed. **Calculations, thresholds, data blocks and the methodology
report were not touched and must stay unchanged.**

| File | What changed |
|---|---|
| `demo/senator-check.html` | The long page became four views, one visible at a time, switched by real tabs (hash-routed: `#your-senators`, `#the-senate`, `#committees`, `#how-it-works`). Each leads with a one-line takeaway derived from figures already on the page. Extra detail sits behind "See details"; limits stay visible. Committees are chosen one at a time from an alphabetical list and show all their existing measures together. Clicking a senator's circle opens their state. |
| `demo/civicalign.css` | Tab/view styles keyed to `aria-selected`; takeaway, limit and disclosure styles; consistent spacing inside views; smooth scroll and hover scaling removed; tap targets ≥ 44px; smallest visible text 12px; the Senate "60th vote" label anchored away from the public label. |
| `tests/test_published_pages.py` | Nav test loosened for tab attributes. New tests: four tab panels with only the first shown at load; every view has a takeaway and a limit outside any disclosure; committee view is one-at-a-time and alphabetical; no smooth scroll or hover animation; existing measures and the 0.15 threshold present; highlight keyed to `aria-selected`; new How-it-works wording present and old absent; selected tab scrolled into view; pivot label anchoring; 44px tap targets. |

Wording change made at the owner's request: the How-it-works takeaway now reads
*"We combine public voting records, survey estimates, and other public data to
make these comparisons."*

## Test results

- `python -m pytest -q` → **93 passed**.
- Data blocks (`V M X G L R P C`) byte-identical to the pre-redesign page.
- Every sentence the old page rendered is still rendered identically; the new
  page additionally renders the 11 committees the old page never showed.
- Checked in a real mobile emulation at 375px, all four views: no horizontal
  overflow; smallest visible text 12px; every tap target ≥ 44px; Senate labels do
  not overlap; selected tab visible in the nav row.
- Keyboard: roving tabindex on the tabs (exactly one in the Tab order);
  ArrowLeft/Right/Home/End move selection, visible panel, hash and focus together.
  Zero console errors.

## Remaining issues

- **Real Enter/Space activation** of tabs and circles could not be driven from the
  browser pane (its key injection does not trigger native default actions — Enter
  did not toggle a plain `<details>` either). Elements are native links and
  buttons; worth one press on a real keyboard.
- **Headless-Chrome screenshots are untrustworthy at phone widths**: headless
  enforces a 500px minimum viewport, producing cropped images that once looked like
  stale wording. Use the DevTools-protocol script pattern (device emulation) for
  phone captures.
- Earlier items unchanged: rotate the Congress.gov API key pasted into chat; the
  2024 survey wave does not exist; two audits disagree on committee median vs mean
  (median shown, both computed — do not resolve during interface work); Output
  Ideology rests on 7–28 votes for four committees; the claude.ai copy and shared
  doc do not update themselves; the whitepaper is hand-written and the weekly job
  warns rather than blocks if its figures drift.

## Exact next steps

1. Owner reviews the fresh screenshots (four phone views at 390px, four desktop).
2. `git push` the local commit to `origin/main`.
3. Trigger the workflow (`gh workflow run update.yml -R safire684-ops/civicalign`)
   and confirm `update` and `publish` both succeed.
4. Verify the live site: nav present, only the first view shown at load, the same
   figures as local (`/tmp/snap2.js`-style sentence comparison).
5. Rebuild the claude.ai copy with the stylesheet inlined and republish to the
   same URL; the shared doc needs no change (methodology untouched).
6. If the weekly job re-dates `demo/methodology.html`, that is expected and
   separate from this change.

## The feedback that shaped this round, verbatim

> Replace the long scrolling page with four clear views: Your senators: state selector and two simple senator cards. The Senate: one main comparison, with the senator circles below. Committees: choose one committee and see its existing measures together. How it works: plain explanations, sources, and calculations. Each view should lead with a short takeaway and a clear chart. Put extra detail behind "See details," but keep important limits visible. Use readable text, consistent spacing, and clear labels. Avoid crowded charts and unnecessary animation. Scope: Pillars 4–6 only. Preserve all calculations, data, thresholds, and existing measures. Keep unresolved methodology disagreements separate. Do not add rankings, grades, or new claims.

Follow-ups: make the selected tab clearly visible (CSS had keyed to `aria-current`
while the tabs set `aria-selected`); replace the How-it-works takeaway wording; fix
the overlapping Senate labels on phones; confirm readability and tap targets at
phone size.

## Earlier rounds (kept for context)

The Gemini reports referenced in earlier rounds:

- Pillar 6 dual-metric framework: https://gemini.google.com/share/b75123b297db?skid=4798bd3c-9d90-4f8a-a251-00429acbda75
- System audit & execution directives: https://gemini.google.com/share/82bd4fe17a76?skid=e8601a35-0fb0-4b8d-b6a8-f4b2775b7142

Decisions approved earlier: public repo under `safire684-ops` with the personal
email hidden in history; Pillars 4–6 only; committee module plots the members'
median with the 0.15 threshold and keeps the mean in fine print; the percentage
score removed; six landmark bills at their median cutpoint; no API key anywhere.
Superseded: "receipts name the bill, vote and dividing line only" — the vote
example now shows the bill, question, date, the senator's own vote and a Voteview
link, is chosen by a neutral rule (busiest bill, passage vote first), and carries
the sentence "This vote does not tell us whether the state's voters supported the
bill." No state side is inferred from a vote's dividing line any more.
