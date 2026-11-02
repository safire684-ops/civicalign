# 50degrees data files for the website

These files cover the 119th Congress (2025 to now) and come from the data pipeline (`civicalign export 119`).
They are plain JSON, so the site can load them directly or copy them into its own database. The `meta.json`
file says when they were made and how many records each file holds.

| File | What it holds | Shape |
|---|---|---|
| `senators.json` | everyone who cast a Senate floor vote this Congress, with their terms | list |
| `votes.json` | every Senate floor roll call: question, result, counts, count by party, what yes and no meant, why it passed or failed | list |
| `positions.json` | how each senator voted on each roll call | `{vote id: {senator id: "Yea" / "Nay" / "Present" / "Not Voting"}}` |
| `bills.json` | every measure with a floor vote: title, importance, cost estimates, its votes, and the facts or explanations of what it does | list |
| `committee_votes.json` | committee roll calls that passed every check, with the count by party (the Partisan Action Matrix) | list |
| `nominations.json` | nominations with a floor vote, with what follows if confirmed and if not | list |

## IDs (they link the files)
- Senator: `id` is the Bioguide ID (`"A000382"`), the same key used in `positions.json`.
- Vote: `"119-1-504"` (Congress, session, roll call number). `bills[].votes` and `nominations[].votes` list these.
- Bill: `"hr1"`, `"s2296"`, `"sjres98"` (type and number, lowercase). `votes[].bill` points here; `label` is the
  printed form (`"H.R. 1"`).
- Nomination: `"PN11-1"`.

## Rules the site must keep
These are what make the project trustworthy. Please don't drop them.

1. **Bill facts (`bills[].key_facts`) are shown with their label.** For the demo, the 40 most important bills
   carry plain-English facts in place of the full AI explanation (which needs an API key we don't have yet).
   Show `key_facts.about` with them: it says the facts were drafted with AI, are tied to the exact wording of the
   bill, and were spot-checked by a person. Show each fact's `quote` (the words that prove it) and `source` next
   to its `claim`, for example behind a "show the source" link. The other 88 bills have `key_facts: null`: show
   "explanation coming soon".
   - `side`: `passes` = what happens if it becomes law; `fails` = what stays in place if it doesn't;
     `change` = what it changes in existing law. A natural layout is "If it passes" / "If it fails" columns.
   - `must_say: true` marks the main facts; `false` ones are details that can go behind "more".
   - `part` is the section of the bill (`"Sec. 2"`); `source` is `"bill"` or the law or rule quoted
     (`"8 U.S.C. 1182"`, `"88 FR 20688"`, `"Public Law 114-92"`).
2. **AI explanations (`bills[].explanations`) are empty for now.** When they arrive, each part has a `status`:
   show the text only for `verified` or `approved`; a `held` part has no text and should say it is being checked.
3. **Votes are explained in plain words already.** `votes[].meaning.yes_means`, `no_means` and `outcome` are
   written to be shown as they are (they come from fixed rules, not AI). If `meaning` is ever `null` (a vote the
   rules can't explain yet), show the question and result only.
4. **Neutral wording.** No party colors as good or bad, no "won" or "lost" for a party. Party counts are
   `by_party` (`D`, `R`, `I`; each `Yea` / `Nay` / `Present` / `Not Voting`).
5. **Committee votes:** `by_party.party` is the count by party; `by_party.caucus` folds independents into the
   party they caucus with. `notes` and `correction_note` explain anything unusual and should be visible.

## What's coming in later drops
- Full AI explanations of every part of each bill, once the API key is in (same `bills.json`, `explanations`).
- 7 facts a reviewer asked to have reworded (they're left out of this drop and return once fixed).
- Earlier Congresses, and updates twice a week.
