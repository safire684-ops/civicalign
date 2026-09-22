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


def test_every_receipt_is_a_genuine_divergence(report):
    """The senator's recorded vote must be the opposite of the state-implied one,
    and the two must be the only two values."""
    assert report.receipts, "expected receipts"
    for b, x in report.receipts.items():
        assert {x.senator_vote, x.state_implied} == {"Yea", "Nay"}
        assert x.senator_vote != x.state_implied
        assert x.label and x.bill and x.question
        assert -1 <= x.cutpoint <= 1


def test_receipts_prefer_passage_votes_on_prominent_bills(report):
    """A receipt should be the most recognisable vote available, not an obscure
    procedural motion."""
    o = report.receipts["O000174"]
    assert "Passage" in o.question
    assert o.bill == "HR1"


def test_output_ideology_only_reports_committees_with_enough_votes(report):
    reportable = [o for o in report.output_ideology if o.is_reportable]
    assert reportable, "expected at least one committee"
    assert all(o.n_votes >= 7 for o in reportable)
    for o in report.output_ideology:
        assert o.vs_senate == pytest.approx(o.coi - report.chamber.median)
        if o.vs_public is not None:
            assert o.vs_public == pytest.approx(o.coi - report.chamber.national_coord)


def test_committee_distance_from_public_is_reported_alongside_distance_from_senate(report):
    for c in report.committees:
        assert c.cnd is not None and c.cnd_mean is not None
        assert c.cnd == pytest.approx(c.median - report.chamber.national_coord)
        assert c.cnd_mean == pytest.approx(c.mean - report.chamber.national_coord)
