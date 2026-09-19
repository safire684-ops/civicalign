# What "done" means

CivicAlign as specified has seven pillars. Nobody finishes a seven-pillar system
solo, so "done" has to mean something narrower and testable. Below are two
candidate finish lines with falsifiable criteria. Pick one. The other becomes a
later decision made with evidence, not a commitment made now.

---

## Finish line A: the measurement layer (recommended)

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
| A5 | Every headline number carries an uncertainty range | **NOT DONE** — ~2 days |
| A6 | The public write-up says what the code says | **NOT DONE** — corrections written, not applied |
| A7 | Someone who disagrees can find the exact line that produced a number | **done** (module per spec section) |

**Remaining work: A5 and A6. Roughly one week.**

A5 is the one that matters. `+3.37 points` and every residual are point estimates
with no error bars. Bootstrap the medians and the regression; if the skew's range
crosses zero, that is a finding and you need to know it before publishing, not
after someone else checks.

A6 is an hour of pasting, and it is the only item with an external deadline,
because the current write-up makes claims the data contradicts.

### How you know you are done

Hand the repo to someone who wants to prove you wrong. If their objections are
all about *what you chose to measure* rather than *whether your numbers are
right*, you are done. Disagreement about method is a healthy end state.
Disagreement about arithmetic is not.

---

## Finish line B: the product (one working page)

**The claim:** "Type your state, see what your senators actually did."

This needs Pillars 1-3, which do not exist: bill-text breakdown, roll-call
ingestion, committee-vote parsing. That is the substance of the original pitch —
without it there is no "what did my senator do," only an ideology dashboard.

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

## Why A first

A is nearly finished and B has not started. Finishing A gives you something real
to show, and it is the part that makes B trustworthy later: B without A is a
tracker with no yardstick, and A without B is still a citable instrument.

They are also different jobs. A is statistics and careful documentation. B is
data engineering plus a hard accuracy problem in language. Doing them at once
means doing neither.

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
