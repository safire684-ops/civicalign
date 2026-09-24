"""README, HANDOFF and METHODOLOGY must not quietly reintroduce retired methods.

A retired method may be named only in a passage that says it is retired, removed,
diagnostic-only or not used (HANDOFF and METHODOLOGY explain why it went). A few
phrases are banned outright. Each document must also state the current Pillar 4
method and that the voter estimate is never compared directly with a senator."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "HANDOFF.md", "METHODOLOGY.md")

RISKY = re.compile(r"residual|alignment score|alignment band|out of step|statistically aligned|defian|betray|\brank(?:s|ed|ing)?\b|"
                   r"\bregression\b(?!s? tests?|_audit)|crosses_over|away from their state|distance to the median voter|worse aligned", re.I)
MARKER = re.compile(r"retired|removed|deleted|diagnostic|\bnever\b|\bno\b|\bnot\b|nothing|declined|obsolete|instead|coming back|"
                    r"does not|do not|replaced|\bwhy\b", re.I)
BANNED = ("worse aligned than", "statistically aligned with", "most out of step", "more extreme than their own state",
          "senators significantly off", "senators significantly out")


def passages(text: str) -> list[str]:
    """Blank-line paragraphs, with list items split into their own passages."""
    out = []
    for block in re.split(r"\n\s*\n", text):
        out += [p for p in re.split(r"\n(?=\s*(?:[-*]|\d+\.)\s)", block) if p.strip()]
    return out


def violations(text: str) -> list[str]:
    bad = [f"banned phrase {b!r}" for b in BANNED if b in text.lower()]
    for p in passages(text):
        flat = " ".join(p.split())
        if RISKY.search(flat) and not MARKER.search(flat):
            bad.append(flat[:160])
    return bad


@pytest.mark.parametrize("doc", DOCS)
def test_retired_methods_appear_only_as_retired(doc):
    assert not violations((ROOT / doc).read_text()), violations((ROOT / doc).read_text())


@pytest.mark.parametrize("doc", DOCS)
def test_each_document_states_the_current_method(doc):
    flat = " ".join((ROOT / doc).read_text().split()).lower()
    assert "caucus" in flat and "peer" in flat, "Pillar 4 is the caucus-group peer comparison"
    assert re.search(r"never subtracted|no comparison across the two scales|never compared directly|not directly compared", flat), \
        "the voter estimate is never compared directly with a senator"


def test_the_check_catches_a_reintroduced_method():
    assert violations("Pillar 4 reads each senator's regression residual and ranks senators by it.")
    assert violations("Ossoff is statistically aligned with Georgia voters.")
    assert violations("A table of the senators most out of step with their state, no longer shown.")
    assert not violations("The regression is retired and kept for diagnostics only.")
