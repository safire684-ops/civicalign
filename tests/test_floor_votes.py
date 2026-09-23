"""Landmark bills, receipts and committee output ideology, all from floor votes.

These three rest on the same join: a roll call's cutpoint, its bill number, and
who voted which way. The tests pin the properties that make each one honest.
"""
import pytest

from civicalign.config import DEFAULT
from civicalign.pipeline import run
from civicalign.sources import billflow, rollcalls


@pytest.fixture(scope="module")
def report():
    r = run(DEFAULT)
    if not r.landmarks:
        pytest.skip("floor vote files not downloaded")
    return r


@pytest.fixture(scope="module")
def bills():
    return billflow.load_bills(DEFAULT.billflow_zip, DEFAULT.billflow_house_zip)


def test_short_titles_are_whole_bill_titles_not_section_titles(bills):
    """HR 1's section titles include things like 'FEHB Protection Act'. Its own
    short title is what people know it by. A section title leaking in here would
    put a wrong name on the scale."""
    hr1 = bills["HR1"]
    assert hr1.short, "HR 1 must carry a whole-bill short title"
    assert "FEHB" not in hr1.short
    assert hr1.short == "One Big Beautiful Bill Act"


def test_landmarks_are_placed_inside_the_scale_and_sorted_by_prominence(report):
    xs = [l.cutpoint for l in report.landmarks]
    assert all(-1 <= x <= 1 for x in xs)
    votes = [l.votes for l in report.landmarks]
    assert votes == sorted(votes, reverse=True)
    assert all(l.label for l in report.landmarks), "every landmark needs a name"
    assert report.landmarks[0].key == "HR1"


def test_yea_side_is_found_from_the_votes_not_assumed(report):
    """The cutpoint alone does not say which side voted Yea. The side is read
    off the voters; near-unanimous votes resolve to None rather than a guess."""
    icpsr = rollcalls.icpsr_to_bioguide(DEFAULT.members_csv, DEFAULT.congress)
    votes = rollcalls.load_votes(DEFAULT.votes_csv, icpsr)
    rcs = rollcalls.load_rollcalls(DEFAULT.rollcalls_csv, votes, report.scores)
    resolved = [rc for rc in rcs if rc.yea_is_right is not None]
    assert len(resolved) > 0.95 * len(rcs)
    # spot check: on every resolved vote, the mean Yea voter must sit on the Yea side
    import statistics as st
    for rc in resolved[:50]:
        v = votes[rc.number]
        yeas = [report.scores[b] for b, y in v.items() if y and b in report.scores]
        nays = [report.scores[b] for b, y in v.items() if not y and b in report.scores]
        assert (st.fmean(yeas) > st.fmean(nays)) == rc.yea_is_right


def test_receipts_name_a_real_vote_and_link_to_it(report):
    """Bill, question, date, the senator's own recorded Yea or Nay, and a link to
    the roll call at Voteview. No inferred state side and no cutpoint travel with
    the example, because neither is evidence of what the state's voters wanted."""
    assert report.receipts, "expected receipts"
    for b, x in report.receipts.items():
        assert x.senator_vote in ("Yea", "Nay")
        assert x.label and x.bill and x.question and x.date
        assert x.url == f"https://voteview.com/rollcall/RS{DEFAULT.congress}{x.roll:04d}"
        assert not hasattr(x, "state_implied")
        assert not hasattr(x, "cutpoint")


def test_receipts_follow_the_documented_neutral_rule(report, bills):
    """Recompute the rule independently for every scored senator: among titled
    bills they cast a Yea or Nay on, passage beats cloture beats anything else,
    then the bill with the most floor votes, then the higher roll number. Which
    way they voted and where their state sits play no part."""
    icpsr = rollcalls.icpsr_to_bioguide(DEFAULT.members_csv, DEFAULT.congress)
    votes = rollcalls.load_votes(DEFAULT.votes_csv, icpsr)
    rcs = rollcalls.load_rollcalls(DEFAULT.rollcalls_csv, votes, report.scores)
    per_bill: dict[str, int] = {}
    for rc in rcs:
        if rc.bill:
            per_bill[rc.bill] = per_bill.get(rc.bill, 0) + 1

    def rank(rc):
        q = rc.question.lower()
        return (0 if "passage" in q else 1 if "cloture" in q else 2, -per_bill[rc.bill], -rc.number)

    assert set(report.receipts) == set(report.scores)
    for b, x in report.receipts.items():
        cands = [rc for rc in rcs if rc.bill and b in votes.get(rc.number, {})
                 and rc.bill in bills and (bills[rc.bill].short or bills[rc.bill].title)]
        best = min(cands, key=rank)
        assert x.roll == best.number, f"{b}: expected roll {best.number}, got {x.roll}"
        assert x.senator_vote == ("Yea" if votes[best.number][b] else "Nay")


def test_receipts_are_not_filtered_by_how_the_senator_voted(report):
    """The removed rule kept only votes that disagreed with a side inferred from
    the state. Under the neutral rule the busiest bill's passage vote is shown for
    everyone who cast one, so Yeas and Nays both appear on that same roll call."""
    by_roll: dict[int, set[str]] = {}
    for x in report.receipts.values():
        by_roll.setdefault(x.roll, set()).add(x.senator_vote)
    commonest = max(by_roll, key=lambda r: sum(1 for x in report.receipts.values() if x.roll == r))
    assert by_roll[commonest] == {"Yea", "Nay"}


def test_receipt_selection_never_reads_state_positions_or_dividing_lines():
    """Guard at the source: the selection code must not touch the identifiers the
    old inference used. Docstrings are ignored; only names in code count."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src" / "civicalign" / "receipts.py").read_text()
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    banned = {"state_pos", "state_implied", "cutpoint", "yea_is_right", "state"}
    assert not (names & banned), names & banned


def test_output_ideology_only_reports_committees_with_enough_votes(report):
    reportable = [o for o in report.output_ideology if o.is_reportable]
    assert reportable, "expected at least one committee"
    assert all(o.n_votes >= 7 for o in reportable)
    for o in report.output_ideology:
        assert o.vs_senate == pytest.approx(o.coi - report.chamber.median)


