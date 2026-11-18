"""Reading Senate roll calls from the Congressional Record, and what follows from them.
No test here uses the network; the page formats are ones the Record really prints."""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from civicalign import legislative as L
from civicalign import record_votes as R
from civicalign.config import DEFAULT
from civicalign.sources import congressional_record as CR

ROOT = Path(__file__).resolve().parent.parent


def page(*lines) -> bytes:
    return ("<html><body><pre>\n" + "\n".join(lines) + "\n</pre></body></html>").encode()


def test_a_roll_call_is_read_with_its_lists_and_announced_result():
    roll = CR.parse_rolls(page("  The result was announced--yeas 2, nays 1, as follows:", "", "   [Rollcall Vote No. 250 Leg.]", "",
                               "      YEAS--2", "", "     Cortez Masto", "     Scott (FL)", "", "      NAYS--1", "", "     Lee", "",
                               "      NOT VOTING--1", "", "     Sullivan", "", "  The bill was passed."))[250]
    assert roll["complete"] and roll["kind"] == "Leg" and roll["announced"] == {"yea": 2, "nay": 1}
    assert roll["lists"] == {"Yea": ["Cortez Masto", "Scott (FL)"], "Nay": ["Lee"], "Not Voting": ["Sullivan"]}


@pytest.mark.parametrize("header,kind", [("[Rollcall Vote No. 8 Ex.]", "Ex"), ("[Rollcall Vote No. 8.]", None), ("[Rollcall Vote No. 8 Exec.]", "Ex"),
                                         ("[Rollcall Vote No. 8 Executive]", "Ex"), ("[Rollcall vote No. 8 Ex.]", "Ex")])
def test_every_header_the_record_prints_is_read(header, kind):
    roll = CR.parse_rolls(page("   " + header, "   YEAS--1", "     Lee"))[8]
    assert roll["complete"] and roll["kind"] == kind


@pytest.mark.parametrize("line,want", [("YEAS--- 1", "Yea"), ("ANSWERED ``PRESENT'' --1", "Present"), ("ANSWERED ``PRESENT''--1", "Present"), ("NOT VOTING--1", "Not Voting")])
def test_every_section_heading_the_record_prints_is_read(line, want):
    assert CR.parse_rolls(page("  [Rollcall Vote No. 9 Leg.]", "    " + line, "     Lee"))[9]["lists"][want] == ["Lee"]


def test_a_section_of_zero_has_no_list():
    roll = CR.parse_rolls(page("  [Rollcall Vote No. 9 Ex.]", "    YEAS--1", "     Lee", "  The nomination was confirmed."))[9]
    assert roll["complete"] and roll["lists"]["Nay"] == []


def test_a_printed_correction_doesnt_replace_the_vote_or_join_its_list():
    """Vote 119-2-99: a correction note interrupts the list and quotes the header inside a paragraph."""
    roll = CR.parse_rolls(page("  [Rollcall Vote No. 99 Leg.]", "    YEAS--1", "     Lee", "    NAYS--2", "     Reed", "", " ===== NOTE =====", "",
                               "  On page S1914, the following appears: [Rollcall Vote No. 99 Leg.] YEAS--25", "Hassan Heinrich Hickenlooper Hirono", "",
                               "     Smith", "    NOT VOTING--0"))[99]
    assert roll["complete"] and roll["lists"]["Nay"] == ["Reed", "Smith"]


def test_a_stray_angle_bracket_in_the_debate_doesnt_swallow_a_vote():
    assert CR.parse_rolls(page("  costs < 3 percent and more", "  [Rollcall Vote No. 9 Leg.]", "    YEAS--1", "     Lee", "  more than 3 > 2"))[9]["complete"]


def test_a_list_short_of_its_printed_total_is_incomplete_not_guessed():
    assert not CR.parse_rolls(page("  [Rollcall Vote No. 9 Leg.]", "    YEAS--2", "     Lee", "    NAYS--0"))[9]["complete"]


def test_a_second_list_for_a_position_stops_the_roll():
    roll = CR.parse_rolls(page("  [Rollcall Vote No. 9 Leg.]", "    YEAS--1", "     Lee", "    YEAS--1", "     Reed"))[9]
    assert roll["lists"]["Yea"] == ["Lee"]


@pytest.mark.parametrize("text,number,to,speaker", [
    ("Mr. PADILLA. Mr. President, on rollcall vote 26, I voted nay. It was my intention to vote aye.", 26, "Yea", "PADILLA"),
    ("Mr. BENNET. Mr. President, before I speak on the matter in front of us, I wanted to say that on rollcall vote 89, I voted aye. It was my intention to vote no.", 89, "Nay", "BENNET"),
    ("Ms. ALSOBROOKS. Mr. President, on rollcall vote No. 114, I was recorded as a ``yes.'' It was my intention to vote no.", 114, "Nay", "ALSOBROOKS")])
def test_the_three_real_change_of_vote_notices_are_read(text, number, to, speaker):
    notice = CR.parse_changes(page(text, "  The PRESIDING OFFICER. Without objection, it is so ordered."))
    assert notice["granted"] and notice["found"] == [{"number": number, "speaker": speaker, "to": to}]


def test_a_notice_that_cant_be_read_is_empty_rather_than_guessed():
    assert CR.parse_changes(page("Mr. LEE. Mr. President, I misspoke on an earlier vote."))["found"] == []


def test_the_metadata_names_each_vote_and_notice():
    mods = b"""<mods xmlns="http://www.loc.gov/mods/v3"><extension/><relatedItem>
      <identifier type="uri">https://www.govinfo.gov/app/details/CREC-2026-09-28/CREC-2026-09-28-pt1-PgS5021-7</identifier>
      <identifier type="congressional vote number">SENATE Rollcall Vote No.250(119th Congress)</identifier>
      <titleInfo><title>LEGISLATIVE SESSION</title></titleInfo><extension><granuleClass>SENATE</granuleClass></extension></relatedItem>
      <relatedItem><identifier type="uri">https://www.govinfo.gov/app/details/CREC-2026-09-28/CREC-2026-09-28-pt1-PgS9</identifier>
      <titleInfo><title>CHANGE OF VOTE</title></titleInfo><extension><granuleClass>SENATE</granuleClass></extension></relatedItem></mods>"""
    ix = CR.issue_index(mods)
    assert ix["votes"] == {250: "CREC-2026-09-28-pt1-PgS5021-7"} and ix["changes"] == ["CREC-2026-09-28-pt1-PgS9"]
    assert ix["senate"] == ["CREC-2026-09-28-pt1-PgS5021-7", "CREC-2026-09-28-pt1-PgS9"]


class Response:
    def __init__(self, body=b"data", url="https://www.govinfo.gov/x"):
        self.body, self.url = body, url
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.body
    def geturl(self): return self.url


def test_govinfos_error_page_counts_as_no_file(monkeypatch):
    """A missing file redirects to an ordinary page with status 200."""
    monkeypatch.setattr(CR.urllib.request, "urlopen", lambda *a, **k: Response(b"<!DOCTYPE html>", "https://www.govinfo.gov/error"))
    assert CR.fetch("https://www.govinfo.gov/metadata/pkg/CREC-2025-04-05/mods.xml", pause=0) is None


def test_a_refusal_is_not_retried(monkeypatch):
    calls = []
    def refuse(*a, **k):
        calls.append(1)
        raise CR.urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    monkeypatch.setattr(CR.urllib.request, "urlopen", refuse)
    with pytest.raises(CR.RecordError):
        CR.fetch("https://www.govinfo.gov/x", pause=0)
    assert len(calls) == 1


NAMES = {"SCOTT": [("FL", "S1"), ("SC", "S2")], "GRAHAM": [("SC", "G1"), ("SC", "G2")], "LUJAN": [("NM", "L1")], "CORTEZ MASTO": [("NV", "C1")]}


def test_printed_names_resolve_to_one_senator_or_none():
    assert R.resolve("Scott (FL)", NAMES) == "S1" and R.resolve("Cortez Masto", NAMES) == "C1"
    assert R.resolve("Scott", NAMES) is None, "two senators, no state printed"
    assert R.resolve("Luján", NAMES) == "L1"
    assert R.resolve("Unknown", NAMES) is None


def test_a_successor_with_the_same_name_and_state_is_told_apart_by_who_could_vote():
    assert R.resolve("Graham", NAMES) is None
    assert R.resolve("Graham", NAMES, {"G2", "L1"}) == "G2"


@pytest.fixture
def small(monkeypatch, tmp_path):
    """One roll call in Voteview, and stores in a temporary folder."""
    rolls = {"119-2-5": {"date": "2026-09-28", "clerk_rollnumber": "5", "yea_count": "1", "nay_count": "1", "session": "2"}}
    cast = {"119-2-5": {"A": "Yea", "B": "Nay"}}
    monkeypatch.setattr(R, "voteview", lambda cfg=DEFAULT: (rolls, cast, {"AA": [("TX", "A")], "BB": [("UT", "B")]}))
    monkeypatch.setattr(R, "store_path", lambda cfg=DEFAULT: tmp_path / "votes.jsonl")
    monkeypatch.setattr(R, "changes_path", lambda cfg=DEFAULT: tmp_path / "changes.jsonl")
    monkeypatch.setattr(R, "cache_dir", lambda cfg=DEFAULT: tmp_path / "cache")
    monkeypatch.setattr(R, "issue_dates", lambda start, today: ["2026-09-28"])
    monkeypatch.setattr(L, "load", lambda cfg=DEFAULT: {"votes": []})
    return tmp_path


def line(yea=("A",), nay=("B",), **extra):
    return {"id": "119-2-5", "issue": "2026-09-28", "granule": "G", "url": "https://www.govinfo.gov/content/pkg/CREC-2026-09-28/html/G.htm", "sha256": "0" * 64,
            "retrieved_utc": "t", "kind": "Leg", "announced": None, "complete": True, "unknown": [], "Yea": list(yea), "Nay": list(nay), **extra}


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_an_exact_match_is_verified(small):
    write(small / "votes.jsonl", [line()])
    assert R.compare()["votes"]["119-2-5"]["status"] == "verified"


def test_a_vote_not_read_yet_is_pending(small):
    assert R.compare()["votes"]["119-2-5"]["status"] == "pending"


def test_an_incomplete_list_is_pending_not_verified(small):
    write(small / "votes.jsonl", [line(complete=False)])
    assert R.compare()["votes"]["119-2-5"]["status"] == "pending"


def test_a_disagreement_with_no_official_explanation_is_a_conflict(small):
    write(small / "votes.jsonl", [line(yea=("B",), nay=("A",))])
    c = R.compare()
    assert c["votes"]["119-2-5"]["status"] == "conflict" and c["counts"]["conflict"] == 1


def test_a_granted_change_of_vote_explains_the_difference(small):
    # Voteview has the original vote; the list shows it too, and the notice gives the correction.
    write(small / "votes.jsonl", [line()])
    write(small / "changes.jsonl", [{"id": "119-2-5", "senator": "A", "to": "Nay", "granted": True, "url": "u", "issue": "2026-09-29", "granule": "N"}])
    v = R.compare()["votes"]["119-2-5"]
    assert v["status"] == "verified" and v["final"]["A"] == "Nay" and v["changes"][0]["senator"] == "A"


def test_a_change_of_vote_nobody_granted_changes_nothing_and_is_reported(small):
    write(small / "votes.jsonl", [line()])
    write(small / "changes.jsonl", [{"id": "119-2-5", "senator": "A", "to": "Nay", "granted": False, "url": "u", "issue": "2026-09-29", "granule": "N"}])
    c = R.compare()
    assert c["votes"]["119-2-5"]["final"]["A"] == "Yea" and c["unread_changes"] == ["u"]


def test_a_tally_that_differs_is_a_conflict_even_if_names_are_explained(small):
    write(small / "votes.jsonl", [line(yea=("A", "B"), nay=())])
    assert R.compare()["votes"]["119-2-5"]["status"] == "conflict"


def test_a_failed_read_appends_nothing_and_says_so(small, monkeypatch):
    def down(*a, **k):
        raise CR.RecordError("GovInfo is down")
    monkeypatch.setattr(CR, "fetch", down)
    result = R.update(today=date(2026, 9, 29))
    assert result["state"] == "unreachable" and "down" in result["detail"]
    assert not (small / "votes.jsonl").exists() and not (small / "changes.jsonl").exists()


def _serve(monkeypatch, body):
    mods = b"""<mods xmlns="http://www.loc.gov/mods/v3"><relatedItem>
      <identifier type="uri">https://www.govinfo.gov/app/details/CREC-2026-09-28/CREC-2026-09-28-pt1-PgS1</identifier>
      <identifier type="congressional vote number">SENATE Rollcall Vote No.5(119th Congress)</identifier>
      <extension><granuleClass>SENATE</granuleClass></extension></relatedItem></mods>"""
    monkeypatch.setattr(CR, "fetch", lambda url, cache=None, pause=0.2: mods if url == CR.issue_url("2026-09-28") else body() if "PgS1" in url else None)


ROLL_PAGE = page("  [Rollcall Vote No. 5 Leg.]", "   YEAS--1", "     Aa", "   NAYS--1", "     Bb")


def test_a_new_vote_is_stored_with_its_address_and_hash(small, monkeypatch):
    _serve(monkeypatch, lambda: ROLL_PAGE)
    result = R.update(today=date(2026, 9, 29))
    assert result["state"] == "ok" and result["new_votes"] == 1
    stored = R.read_jsonl(small / "votes.jsonl")[0]
    assert stored["Yea"] == ["A"] and stored["Nay"] == ["B"] and stored["url"].endswith("CREC-2026-09-28-pt1-PgS1.htm")
    assert stored["sha256"] == hashlib.sha256(ROLL_PAGE).hexdigest()
    assert R.update(today=date(2026, 9, 29))["new_votes"] == 0, "nothing new, nothing added"
    assert len(R.read_jsonl(small / "votes.jsonl")) == 1


def test_a_corrected_page_adds_a_line_and_keeps_the_old_one(small, monkeypatch):
    _serve(monkeypatch, lambda: ROLL_PAGE)
    R.update(today=date(2026, 9, 29))
    corrected = page("  [Rollcall Vote No. 5 Leg.]", "   YEAS--1", "     Bb", "   NAYS--1", "     Aa")
    _serve(monkeypatch, lambda: corrected)
    result = R.update(today=date(2026, 9, 30))
    assert result["pages_changed"] == ["119-2-5"]
    rows = R.read_jsonl(small / "votes.jsonl")
    assert len(rows) == 2 and rows[0]["Yea"] == ["A"] and rows[1]["Yea"] == ["B"]
    assert R.compare()["votes"]["119-2-5"]["status"] == "conflict"


def test_a_vote_in_the_record_but_not_voteview_is_reported(small, monkeypatch):
    mods = b"""<mods xmlns="http://www.loc.gov/mods/v3"><relatedItem>
      <identifier type="uri">https://www.govinfo.gov/app/details/CREC-2026-09-28/CREC-2026-09-28-pt1-PgS1</identifier>
      <identifier type="congressional vote number">SENATE Rollcall Vote No.6(119th Congress)</identifier></relatedItem></mods>"""
    monkeypatch.setattr(CR, "fetch", lambda url, cache=None, pause=0.2: mods if url == CR.issue_url("2026-09-28") else None)
    assert R.update(today=date(2026, 9, 29))["ahead_of_voteview"] == ["119-2-6"]


# ---- the saved results ----

def test_every_stored_line_has_an_official_address_and_hash():
    rows = R.read_jsonl(R.store_path())
    assert rows and all(r["url"].startswith("https://www.govinfo.gov/content/pkg/CREC-") and len(r["sha256"]) == 64 for r in rows)


def test_stored_change_notices_are_the_three_documented_differences():
    notices = {(c["id"], c["senator"]): c["to"] for c in R.read_jsonl(R.changes_path())}
    documented = {(e["vote"], e["senator"]) for e in L.differences()["entries"]}
    assert documented <= set(notices)
    assert notices[("119-1-26", "P000145")] == "Yea" and notices[("119-1-89", "B001267")] == "Nay" and notices[("119-1-114", "A000382")] == "Nay"
