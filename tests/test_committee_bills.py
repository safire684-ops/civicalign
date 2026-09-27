"""Pillar 6: "Bills handled by this committee" on each committee card.

Every count comes from the saved bill_sponsor_classifications table through
bill_tallies.committee_tallies(), carries its exact bill ids, and has a
methodology entry. Referred and reported are separate lists (a committee can
report a bill never recorded as referred to it). The groups describe the
sponsor's voting record, not the bill. Fixture tests use the invented archive
from test_bills; real-data tests read the committed tables.
"""
import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest

from civicalign import build_pages as BP
from civicalign.config import DEFAULT
from civicalign.ideology import bill_tallies as T
from civicalign.ideology import bills as BL
from civicalign.ideology import compute as C
from civicalign.ideology import methodology as M
from civicalign.ideology.store import Table
from test_bills import BILLS, SENATORS, WHEN, write_archive

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "src" / "civicalign" / "templates" / "senator-check.template.html").read_text()
CLASSES = ("LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN")
PARTS = ("referred", "reported")
MEANING = ("This shows which senators sponsored the bills that moved through this committee. CivicAlign is not deciding "
           "whether the bills themselves are liberal or conservative. The groups are based only on the DW-NOMINATE voting "
           "score of each bill’s primary sponsor.")
NOT_A_SUBSET = ("A committee can sometimes report a bill that was not first recorded as referred to that committee, so the "
                "reported count does not always have to be a subset of the referred count.")


def _script() -> str:
    """The committee part of the page's script."""
    s = TEMPLATE[TEMPLATE.index("<script>"):]
    return s[s.index("// ===== Committees ====="):s.index("// ===== How it works =====")]


def visible_text_of(page: str) -> str:
    """The page without its embedded data (whose official bill titles are the government's words)."""
    return re.sub(r'<script id="data" type="application/json">.*?</script>', " ", page, flags=re.S)


def _counts(F):
    """Every count in one committee's bill section."""
    return [F[p]["total"] for p in PARTS] + [F[p][k] for p in PARTS for k in CLASSES] + [F["reported_without_referral"]]


@pytest.fixture(scope="module")
def data():
    try:
        return BP.payload(DEFAULT)
    except BP.BuildError as e:
        pytest.skip(f"no saved result to build from: {e}")


@pytest.fixture(scope="module")
def pages():
    try:
        return BP.build(DEFAULT)
    except BP.BuildError as e:
        pytest.skip(f"no saved result to build from: {e}")


@pytest.fixture
def cfg(tmp_path):
    raw = tmp_path / "FIXTURE_raw"; raw.mkdir()
    (raw / "SNAPSHOT.json").write_text(json.dumps({"run_utc": WHEN, "accepted": True, "sources": []}))
    c = dataclasses.replace(DEFAULT, raw_dir=raw, ideology_dir=tmp_path / "FIXTURE_ideology")
    Table(c.ideology_dir, "senator_ideology").append(SENATORS, "FIXTURE")
    write_archive(c, BILLS)
    BL.run(c)
    return c


# ---- the counts come from the saved data and trace to exact bills -------------------------------------------------

def test_every_committee_count_comes_from_the_saved_bill_table(data):
    tallies = T.committee_tallies(BL.current(DEFAULT))
    for c in data["p6"]["committees"]:
        t, F = tallies.get(c["code"], {}), c["bills"]
        for part in PARTS:
            want = t.get(part, T.by_classification([]))
            assert F[part]["total"]["ids"] == want["bill_ids"] and F[part]["total"]["v"] == want["total"], (c["code"], part)
            for k in CLASSES:
                assert F[part][k]["ids"] == want["by_classification"][k]["bill_ids"], (c["code"], part, k)
        assert F["reported_without_referral"]["ids"] == t.get("reported_without_referral", {"bill_ids": []})["bill_ids"]


def test_no_committee_count_is_typed_into_the_page_code():
    code = re.sub(r"//[^\n]*", "", _script())                  # comments aside
    literals = set(re.findall(r"(?<![\w.#-])\d+(?![\w%-])", code))
    assert literals <= {"0", "1", "100"}, literals              # 100: the end of the line, in the spoken description


def test_every_tally_traces_to_exact_bill_ids(data):
    for c in data["p6"]["committees"]:
        F = c["bills"]
        for n in _counts(F):
            assert n["v"] == len(n["ids"]) == len(set(n["ids"])), n["p"]
            assert all(b in data["p6"]["bills"] for b in n["ids"]), n["p"]
        for part in PARTS:
            parts = sorted(b for k in CLASSES for b in F[part][k]["ids"])
            assert parts == sorted(F[part]["total"]["ids"]), f"{c['code']} {part}: the sponsor groups partition the total"
            for k in CLASSES:
                assert all(data["p6"]["bills"][b]["c"] == k for b in F[part][k]["ids"]), (c["code"], part, k)


def test_referred_and_reported_remain_separate(data):
    rows = {r["bill_id"]: r for r in BL.current(DEFAULT)}
    for c in data["p6"]["committees"]:
        F, code = c["bills"], c["code"]
        flags = {b: next((x for x in r["referred_committees"] if x["committee_id"] == code), None) for b, r in rows.items()}
        assert set(F["referred"]["total"]["ids"]) == {b for b, x in flags.items() if x and x["referred"]}, code
        assert set(F["reported"]["total"]["ids"]) == {b for b, x in flags.items() if x and x["reported"]}, code
        assert set(F["reported_without_referral"]["ids"]) == set(F["reported"]["total"]["ids"]) - set(F["referred"]["total"]["ids"])


# ---- a bill a committee reported without a referral --------------------------------------------------------------

def test_committee_tallies_keep_a_reported_bill_without_referral(cfg):
    t = T.committee_tallies(BL.current(cfg))["SSBK"]
    assert t["referred"]["bill_ids"] == ["S1", "S2"] and t["reported"]["bill_ids"] == ["S1", "S3"]
    assert t["reported_without_referral"]["bill_ids"] == ["S3"], "S3 is an original measure the committee reported"
    assert not set(t["reported"]["bill_ids"]) <= set(t["referred"]["bill_ids"]), "reported is not forced into referred"
    for slot in t.values():
        assert T.trace_problems(slot) == []


def test_the_builder_shows_a_reported_bill_without_referral(cfg):
    per, bills, sponsors, meta, versions = BP.committee_bills_payload(cfg, ["SSBK", "SSFI", "SSZZ"])
    F = per["SSBK"]
    assert F["reported"]["total"]["ids"] == ["S1", "S3"] and F["referred"]["total"]["ids"] == ["S1", "S2"]
    assert F["reported_without_referral"]["ids"] == ["S3"] and F["reported_without_referral"]["v"] == 1
    assert F["reported"]["ZERO_SCORE_SPONSOR"]["ids"] == ["S3"]
    assert bills["S3"]["a"]["SSBK"] == [None, "2025-04-01"], "reported with no referral date: nothing is invented"
    assert bills["S1"]["a"]["SSBK"] == ["2025-02-01", "2025-05-01"]
    assert per["SSFI"]["reported"]["total"]["v"] == 0, "a discharge is not a report"
    assert all(n["v"] == 0 for n in _counts(per["SSZZ"])), "a committee with no bills shows zeros, not an error"
    with pytest.raises(BP.BuildError, match="no Pillar 6 result"):
        BP.committee_bills_payload(cfg, ["SSBK"])            # bills name SSFI, which would otherwise vanish
    assert NOT_A_SUBSET in _script()
    assert "no referral to this committee recorded" in _script()


def test_the_real_data_shows_every_reported_without_referral_case(data):
    for c in data["p6"]["committees"]:
        F = c["bills"]
        extra = sorted(set(F["reported"]["total"]["ids"]) - set(F["referred"]["total"]["ids"]))
        assert sorted(F["reported_without_referral"]["ids"]) == extra, c["code"]
        for b in extra:
            assert data["p6"]["bills"][b]["a"][c["code"]][0] is None


# ---- wording -----------------------------------------------------------------------------------------------------

def test_the_section_says_sponsor_not_bill(pages):
    s = _script()
    for text in ("Senate committees review bills before the full Senate votes.",
                 "' sent here &middot; <b>'", "sent back to the Senate</p>'", "<h4>Sent here: '", "<h4>Sent back to the Senate: '",
                 "A bill is referred when it’s sent to the committee for review, and reported when the committee formally "
                 "reports it back to the Senate.",
                 "These counts do not show why a committee reported or did not report any bill.",
                 "</b> Senate '+bills(F.referred.total)+' sent here", "' Senate '+bills(R.total)+'",
                 "disc('What does this mean?'", MEANING, NOT_A_SUBSET):
        assert text in s or text in TEMPLATE, text
    for text in ("Sponsored by senators on the liberal side of the Voteview scale",
                 "Sponsored by senators on the conservative side of the Voteview scale",
                 "See the bills sponsored by senators on the liberal side of the Voteview scale",
                 "See the bills sponsored by senators on the conservative side of the Voteview scale"):
        assert text in TEMPLATE, text
    # by default the card shows only the line, one sentence and the two bill counts; the sponsor split is behind "See bills"
    card = s[s.index("function committeeCard(c)"):s.index("function setCommittee(")]
    assert "split(" not in card and "disc('See bills',function(){return committeeBills(c)})" in card


def test_no_liberal_or_conservative_bills_wording(pages):
    bad = re.compile(r"\b(liberal|conservative) (committee )?(bill|bills|legislation|law|laws|measure|measures)\b", re.I)
    for text in (_script(), visible_text_of(pages["senator-check.html"]), pages["methodology.html"],
                 (ROOT / "src" / "civicalign" / "ideology" / "methodology.py").read_text()):
        assert not bad.search(text)


def test_no_causal_claim_in_the_committee_bill_section():
    s = _script().replace("These counts do not show why a committee reported or did not report any bill.", "")
    for phrase in ("because", "caused", "led to", "resulted in", "due to", "blocked", "buried", "killed", "gatekeep",
                   "obstruct", "favor", "bias"):
        assert phrase not in s.lower(), phrase


# ---- scores, methodology, no LLM -----------------------------------------------------------------------------------

def test_the_current_sponsor_score_comes_from_senator_ideology(data):
    now = BL.current_sponsor_scores(DEFAULT)
    for bg, s in data["p6"]["sponsors"].items():
        assert s["score"]["v"] == (now.get(bg) or {}).get("score"), bg
        assert s["score"]["m"] == "p6.bill_sponsor_score"
    rows = {r["bill_id"]: r for r in BL.current(DEFAULT)}
    moved = [b for b, x in data["p6"]["bills"].items()
             if x["sp"] in now and rows[b]["sponsor_nominate_dim1"] != now[x["sp"]]["score"]]
    for b in moved[:50]:     # the page shows the current score, not the historical one stored with the classification
        assert data["p6"]["sponsors"][data["p6"]["bills"][b]["sp"]]["score"]["v"] != rows[b]["sponsor_nominate_dim1"]
    assert "sponsor_nominate_dim1" not in BP.committee_bills_payload.__code__.co_consts


def test_every_committee_bill_number_has_methodology(data, pages):
    nums = [n for c in data["p6"]["committees"] for n in _counts(c["bills"])] + [s["score"] for s in data["p6"]["sponsors"].values()]
    assert nums
    for n in nums:
        e = M.REGISTRY[n["m"]]
        assert e["kind"] == "billflow" and M.entry_for(n["p"])["id"] == n["m"], n["p"]
        assert f'id="{n["m"]}"' in pages["methodology.html"]
        assert data["methods"][n["m"]]["versions"], n["m"]
    for eid in ("p6.bills_referred_total", "p6.bills_referred_by_sponsor", "p6.bills_reported_total",
                "p6.bills_reported_by_sponsor", "p6.bills_reported_without_referral", "p6.bill_sponsor_score"):
        assert any(n["m"] == eid for n in nums), eid
    versions = " ".join(data["methods"]["p6.bills_referred_by_sponsor"]["versions"])
    assert "committee bill archive versions — source version" in versions and "classification rule — sponsor_nominate_dim1_sign_v1" in versions
    assert "current sponsor score versions" in " ".join(data["methods"]["p6.bill_sponsor_score"]["versions"])
    assert "not the content or ideology of the bill" in " ".join(M.REGISTRY["p6.bills_reported_by_sponsor"]["limitations"])
    s = _script()
    assert "cnt(R.total)" in s and "cnt(P.total)" in s and "cnt(Wr)" in s and "s.score.p0" in s
    assert "cnt(F.referred.total)" in s and "cnt(F.reported.total)" in s


def test_bill_lists_are_behind_see_bills_and_link_to_congress_gov(data):
    s = _script()
    assert "return n.v?disc(g.see,function(){return billList(n.ids,committeeRow(code,part),'bills')}):''" in s
    assert "n.v?" in s, "a fold-out appears only when its group has bills"
    assert "https://www.congress.gov/bill/'+esc(CM.congress)+'th-congress/senate-bill/'+esc(x.n)+'" in s
    for x in list(data["p6"]["bills"].values())[:20]:
        assert x["t"] and isinstance(x["n"], int)


def test_no_llm_or_network_in_the_committee_bill_path():
    for f in (ROOT / "src" / "civicalign" / "build_pages.py", ROOT / "src" / "civicalign" / "ideology" / "bill_tallies.py",
              ROOT / "src" / "civicalign" / "ideology" / "methodology.py"):
        src = f.read_text()
        assert not re.search(r"openai|anthropic|langchain|claude|gpt-|llama|transformers|huggingface|cohere|gemini|ollama", src, re.I), f.name
        assert "subprocess" not in src and "urllib" not in src and "requests" not in src, f.name
    s = _script()
    assert "fetch(" not in s and "XMLHttpRequest" not in s, "the lists come from the page's own embedded data"


# ---- the rest of Pillar 6, and Pillars 4 and 5, are unchanged -------------------------------------------------------

def test_all_sixteen_standing_committees_still_render(data):
    record = C.load_record(DEFAULT, C.index(DEFAULT)[-1]["input_key"])
    codes = [c["code"] for c in data["p6"]["committees"]]
    assert sorted(codes) == sorted(record["results"]["pillar6"]) and len(codes) == 16
    for c in data["p6"]["committees"]:
        assert set(c["bills"]) == {"referred", "reported", "reported_without_referral"}
    assert "disc('See bills',function(){return committeeBills(c)})" in TEMPLATE
    assert '<option value="" selected>Choose a committee</option>' in TEMPLATE, "no committee is preselected"


def _without_bill_section(monkeypatch):
    def stub(cfg, codes):
        return {c: {} for c in codes}, {}, {}, {}, {k: [] for k in ("committee_bill_archive_versions", "classification_rule",
                                                                      "committee_sponsor_score_versions", "current_sponsor_score_versions")}
    monkeypatch.setattr(BP, "committee_bills_payload", stub)
    return BP.payload(DEFAULT)


def test_existing_pillar6_numbers_are_unchanged_by_the_bill_section(data, monkeypatch):
    plain = _without_bill_section(monkeypatch)
    strip = lambda cs: [{k: v for k, v in c.items() if k != "bills"} for c in cs]
    assert strip(data["p6"]["committees"]) == strip(plain["p6"]["committees"])
    for k in ("senate_median", "national"):
        assert data["p6"][k] == plain["p6"][k]
    record = C.load_record(DEFAULT, C.index(DEFAULT)[-1]["input_key"])
    for c in data["p6"]["committees"]:
        for k in ("committee_median", "committee_senate_drift", "committee_public_drift"):
            assert c[k]["v"] == record["results"]["pillar6"][c["code"]][k]["value"], (c["code"], k)


def test_pillars_4_and_5_are_unchanged_by_the_bill_section(data, monkeypatch):
    plain = _without_bill_section(monkeypatch)
    assert data["p4"] == plain["p4"] and data["p5"] == plain["p5"] and data["meta"] == plain["meta"]
    for eid, m in data["methods"].items():
        if M.REGISTRY[eid]["kind"] != "billflow":
            assert m == plain["methods"][eid], eid
    assert set(data["p5"]) == {"active", "diff", "gap", "mdiff", "median", "national", "outcomes", "plain", "unscored", "weighted",
                            "wmedian", "wording"}
