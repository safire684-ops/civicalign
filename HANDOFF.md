# Project handoff — CivicAlign, Pillars 4–6

Saved 21 September 2026. Scope is **Pillars 4, 5 and 6 only** (math-spec
sections 2–5). Pillars 1–3 and 7 belong to someone else.

## Where things stand

- Live site: https://safire684-ops.github.io/civicalign/ (GitHub Pages, rebuilt
  every Monday by `.github/workflows/update.yml`; last run green).
- Repo: https://github.com/safire684-ops/civicalign — 77 tests passing.
- Shared doc (Claude Docs, hand-mirrored): https://claude.ai/code/artifact/683a9e36-3046-4827-a7af-7442b49ef7e3
- Claude.ai copy of the page (manual republish, CSS inlined): https://claude.ai/artifact/Ft6hU6XZUnWHPhZwzwmzaj

## What changed in the last round, and how it was tested

| Feedback | Change | Test |
|---|---|---|
| A — perspective | Ruler of the six busiest bills placed at their roll-call cutpoints; a real "receipt" vote under each senator | `test_floor_votes.py`: whole-bill titles only, Yea side read from voters, receipts are genuine divergences |
| B — Senate vs public | Own track + four figures; 100-circle grid coloured by distance from the public, hover shows vs Senate / public / state | `test_published_pages.py`: 100 dots, US_m matches pipeline |
| C — committees | Members' midpoint vs Senate **and** public, ±0.15 gatekeeper warning; Output Ideology diamond (Budget, Appropriations, Armed Services, Veterans); survival bars kept | `test_floor_votes.py`, `test_published_pages.py` |
| D — directives | Percentage removed; "points further Left/Right" or green "Aligned with State Consensus"; freshmen null state; real baseline badge; external stylesheet | `test_published_pages.py` |

Also: three new sources (Voteview roll calls + senator votes, GovInfo House
bill archive), ten update agents, report template and whitepaper updated, clean
cloud run verified end to end.

## The feedback, verbatim

> Personal: A, on the part where we see how much each senator represents the state how do voters understand what that means? They need perspective more than just Bernie Sanders and Ted Cruz they also need to see high profile bills they'd recognize and see where those are or certain issues and where those are
> B, this has no actual data on how far the senate stands form the American people and that should look like a similar thing to what it does with the senators. Also, I'd like it if in the UI it had a senate representation with each senator being a circle and the color gradient of the senator changing based on whether he was more liberal and conservative than the American populace; and when you hovered on the circle (which would have its state inside the circle) it would give the senators name and where he lines up to the senate, the American populace as a whole, and his individual state.
> C, For the committees it doesn't show committee drift from the senate now it only shows how biased the committee is and it does this very poorly. Once again it needs to be easily understood by voters this thing lacks perspective as in the voters don't clearly understand what they are looking at. Also, it needs to show how the committee drifts form the senate and from the American populace (tell it to reuse the report for pillar 6 I gave you).
> D; [link below]
> fix all these issues and update the github

The two Gemini reports referenced:

- Pillar 6 dual-metric framework (Output Ideology + Gatekeeping Bias Index):
  https://gemini.google.com/share/b75123b297db?skid=4798bd3c-9d90-4f8a-a251-00429acbda75
- System audit & execution directives (confidence band, drop the percentage,
  receipts, freshmen, committee module):
  https://gemini.google.com/share/82bd4fe17a76?skid=e8601a35-0fb0-4b8d-b6a8-f4b2775b7142

## Decisions approved

- Publish as a public repo under `safire684-ops`; hide the personal email in history.
- Scope is Pillars 4–6 only.
- Committee module plots the members' **median** with the 0.15 threshold (Directive 5); the mean stays in fine print.
- Percentage score removed (Directive 2).
- Landmark bills = the six with the most floor votes, at their median cutpoint.
- Receipts name the bill, vote and dividing line only — no invented "material impact".
- No API key anywhere; GovInfo bulk archives and Voteview files are keyless.

## Still unresolved

- **Rotate the Congress.gov API key** pasted into chat. It is unused, but it is in the transcript.
- Directive 3's "material impact" text and Directive 4's 2024 survey wave cannot be done: the first is Pillar 1, the second does not exist.
- Two audits disagree on median vs mean for committees; median is shown per the latest, both are computed.
- Output Ideology rests on 7–28 votes per committee; four committees qualify.
- The claude.ai page copy and the shared doc do not update themselves; the GitHub site does.
- The whitepaper is hand-written; the weekly job warns, never blocks, if its figures drift.

## Next

Simplify navigation and make the site easier for an average voter to understand.
Keep methodology changes separate from that work.
