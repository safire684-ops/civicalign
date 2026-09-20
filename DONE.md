# What "done" means

**Scope: sections 2-5 of the math spec only** — Pillars 4, 5 and 6. Pillars 1-3
and 7 belong to someone else and are not measured against here.

That makes "done" answerable, because sections 2-5 are a self-contained
measurement layer with testable completion criteria.

---

## Finish line: the measurement layer (sections 2-5)

**The claim:** "Here is a reproducible, documented measurement of how far US
senators and Senate committees sit from their constituents, with every limit
stated."

Not a legislative tracker. A measurement instrument plus a methodology, which is
a real and citable thing on its own, and it is most of the way built.

### Criteria

| # | criterion | status |
|---|---|---|
| A1 | A stranger reproduces every published figure from a clean checkout in two commands | **done** (`fetch_data.sh`, `report.sh`) |
| A2 | Every figure traces to a dated, hashed source file | **done** (`PROVENANCE.tsv`) |
| A3 | No figure is published that fails its own validity check | **done** (noise floor, phantom-median, seat-count guards) |
| A4 | Every known limit is written down publicly, not buried | **done** (`METHODOLOGY.md`) |
| A5 | Every headline number carries an uncertainty range | **done** — and it changed the conclusions |
| A6 | The public write-up says what the code says | **NOT DONE** — corrections written, not applied |
| A7 | Someone who disagrees can find the exact line that produced a number | **done** (module per spec section) |

**Remaining work: A6 alone. About an hour.**

A5 did exactly what it was supposed to do — it removed findings rather than
decorating them:

* **CCD is dead.** 0 of 19 committee drift figures are publishable. 17 medians move
  more than 0.05 when a single member leaves, most by 0.2-0.34, which is larger
  than the CCD values themselves. The remaining 2 are stable but too small to
  clear the noise floor. The metric tracks the party seat split, not ideology.
* **The out-of-step list shrank from 10 to 6.** A residual has to clear roughly
  0.57 (2 x residual SE) to mean anything. Ranking by raw residual was publishing
  noise; ranking is now by leverage-corrected t.
* **The apportionment skew held.** +3.37 points, and every individual cycle keeps
  the same sign (2016 +4.08, 2020 +3.37, 2024 +2.66). It is also declining, which
  is a finding in itself.
* **The regression held.** Slope 95% CI [+3.47, +4.54], nowhere near zero.

A6 is an hour of pasting from `WHITEPAPER_CORRECTIONS.md`, and it is the only
item with an external deadline, because the current write-up makes claims the data
contradicts.

### How you know you are done

Hand the repo to someone who wants to prove you wrong. If their objections are
all about *what you chose to measure* rather than *whether your numbers are
right*, you are done. Disagreement about method is a healthy end state.
Disagreement about arithmetic is not.

---

## Out of scope: Pillars 1-3 and 7

Bill-text breakdown, roll-call ingestion, committee-vote parsing, and the polling
overlay. Someone else's part. Listed here only so the handoff is explicit — what
sections 2-5 owe them is a stable output format and an honest statement of which
figures are publishable.

The criteria below are **not** a to-do list for this scope.

### Criteria

| # | criterion | status |
|---|---|---|
| B1 | Bills ingested from source XML, stored, refreshed on a schedule | not started |
| B2 | Each bill has a plain-English pass/fail breakdown that a stranger agrees is accurate | not started |
| B3 | Every roll-call vote joined to its bill and to each senator | not started |
| B4 | Committee votes parsed out of committee reports | not started |
| B5 | One senator's page renders end to end from real data | not started |
| B6 | Ten randomly chosen bills spot-checked by hand against the source text | not started |

**Remaining work: months, and most of the risk sits in B2 and B4.**

B2 is not an engineering problem. It asks a language model to summarise law
accurately, and the failure mode is a confident wrong summary of a real bill,
attributed to a named senator. B4 means parsing prose documents with no fixed
format.

### How you know you are done

B6 is the test: pull ten bills at random, read the source text yourself, and
check the generated breakdown. If you would defend all ten in public, the
pipeline works. If you would defend eight, it does not ship — a 20% error rate on
statements about named politicians is not a product, it is a liability.

---

## What to hand over

Sections 2-5 produce four figures that survive validation, and one that does not.
The handoff needs to say both, or the dead metric will be published by someone
who assumes it works:

| figure | status |
|---|---|
| apportionment skew, +3.37 pts (range +2.66 to +4.08) | publishable |
| chamber median +0.310, cloture pivot +0.440, party gap 0.942 | publishable |
| 6 senators significantly off their state's pattern | publishable |
| committee chair vs. own majority-party median | publishable |
| committee state lean, where the gap exceeds its one-member shift | publishable |
| **committee-to-chamber drift (CCD)** | **do not publish** |

---

## A note on the specs

There are now three specification documents. All three are strong on theory and
wrong on the details that determine whether numbers come out right:

- the Judiciary example is wrong in all of them (+0.30 or "significantly more
  partisan" vs. an actual +0.051)
- `nominate_dim1` is described as dynamic; it is a career constant
- the ICPSR crosswalk, called the critical step, silently returns 80 of 100 senators
- `theunitedstates.io` no longer completes a TLS handshake

Every illustrative figure in them has been wrong so far. The pipeline is now the
more reliable document: it is the thing that has been checked against real data.

So writing more specification is not progress from here, and it feels like
progress, which is the trap. The next real progress is A5 — the error bars —
because it is the only remaining thing that could change a published conclusion.
