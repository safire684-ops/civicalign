"""Pillars 4-6, Step 4 parts 2-3: the page builder and the three views.

The builder reads only the saved result record, the methodology registry and
the saved anchors. These tests check the data it embeds, the committed preview
pages in demo/next/, and what the pages must never contain. Nothing here
writes to data/ideology/ or demo/."""
import ast
import copy
import dataclasses
import json
import re
import shutil
from pathlib import Path

import pytest

from civicalign import build_pages as BP
from civicalign.config import DEFAULT
from civicalign.ideology import anchors as A
from civicalign.ideology import methodology as M

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "demo" / "templates" / "senator-check.template.html").read_text()


@pytest.fixture(scope="module")
def data():
    try:
        return BP.payload(DEFAULT)
    except BP.BuildError as e:
        pytest.skip(f"no saved result to build from: {e}")


@pytest.fixture(scope="module")
def pages():
    return BP.build(DEFAULT)


def numbers(obj):
    """Every displayed number in the payload (dicts carrying a registry id)."""
    if isinstance(obj, dict):
        if "m" in obj and "s" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from numbers(v)


def visible_text(page: str) -> str:
    return re.sub(r"<style>.*?</style>", " ", page, flags=re.S)


# ---- formatting ----------------------------------------------------------------------------

@pytest.mark.parametrize("value,decimals,signed,expected", [
    (0.3195, 3, False, "0.320"), (-0.216, 3, False, "−0.216"), (0.03675037944656569, 3, True, "+0.037"),
    (-0.3655, 3, True, "−0.366"), (0.0, 3, True, "0.000"), (-0.0001, 3, True, "0.000"), (0.2911, 2, False, "0.29"),
    (100, None, False, "100")])
def test_fmt_rounds_half_up_with_a_true_minus_sign(value, decimals, signed, expected):
    assert BP.fmt(value, decimals, signed) == expected


@pytest.mark.parametrize("raw,expected", [
    ("MCCONNELL, Addison Mitchell (Mitch)", "Mitch McConnell"), ("KING, Angus Stanley, Jr.", "Angus King Jr."),
    ("BLUNT ROCHESTER, Lisa", "Lisa Blunt Rochester"), ("HYDE-SMITH, Cindy", "Cindy Hyde-Smith"),
    ("LUJÁN, Ben Ray", "Ben Luján"), ("JUSTICE, James Conley, II", "James Justice II")])
def test_display_names(raw, expected):
    assert BP.display_name(raw) == expected


def test_scale_labels_use_the_whole_surname():
    assert BP.surname("BLUNT ROCHESTER, Lisa") == "Blunt Rochester" and BP.surname("MCCORMICK, David Harold") == "McCormick"


# ---- every number has its methodology ----------------------------------------------------------

def test_every_displayed_number_carries_its_registry_entry(data):
    nums = list(numbers(data))
    assert len(nums) == 400 + 3 + 10 + 16 * 5 + 2 - 1   # Pillar 4 (100 x 4), anchors, Pillar 5, Pillar 6 (16 x 5 + two shared)
    for n in nums:
        e = M.REGISTRY[n["m"]]
        if n["s"] == "NOT_AVAILABLE":
            assert n["d"] is None and n["r"] and e["not_available"], n["p"]
        else:
            assert n["d"] == BP.fmt(n["v"], e["decimals"], e["id"] in BP.SIGNED), n["p"]
        if not n["p"].startswith("reference_anchors."):
            assert M.entry_for(n["p"])["id"] == n["m"]


def test_every_registry_entry_reaches_the_page_and_the_methodology(data, pages):
    assert {n["m"] for n in numbers(data)} == set(M.REGISTRY)
    assert set(data["methods"]) == set(M.REGISTRY)
    for eid in M.REGISTRY:
        assert f'id="{eid}"' in pages["methodology.html"], eid
        m = data["methods"][eid]
        assert m["sources"] and m["formula"] and m["transformation"] and m["versions"] and m["limitations"]


def test_the_page_only_shows_numbers_through_num(pages):
    script = TEMPLATE[TEMPLATE.index("<script>"):]
    assert not re.search(r"\d\.\d{2,}", script), "no data value is written into the template"
    assert "throw new Error('number without a methodology entry" in script
    shown = re.findall(r"esc\((\w+)\.d\)", script)
    assert set(shown) <= {"n", "md", "sm", "pl", "w"}, shown     # screen-reader text repeats numbers already shown by num()


def test_the_build_refuses_a_number_without_an_entry(monkeypatch):
    rec = BP.latest(DEFAULT)
    bad = copy.deepcopy(rec)
    bad["results"]["pillar5"]["new_quantity"] = {"value": 1.0, "status": "AVAILABLE", "units": "x", "reason": None}
    monkeypatch.setattr(BP, "latest", lambda cfg: bad)
    with pytest.raises(BP.BuildError, match="new_quantity"):
        BP.payload(DEFAULT)


def test_the_build_refuses_a_tampered_record_or_missing_anchors(tmp_path):
    cfg = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "ideology")
    shutil.copytree(DEFAULT.ideology_dir, cfg.ideology_dir, ignore=shutil.ignore_patterns("reference_anchors.jsonl"))
    with pytest.raises(A.AnchorError):
        BP.payload(cfg)
    f = next((cfg.ideology_dir / "metrics").glob("*.json"))
    f.write_text(f.read_text().replace('"value":0.204', '"value":0.999', 1))
    with pytest.raises(BP.BuildError, match="index hash"):
        BP.latest(cfg)


# ---- the three views ----------------------------------------------------------------------------

def test_pillar4_senators_and_exactly_three_labelled_anchors(data):
    states = data["p4"]["states"]
    assert len(states) == 50 and all(len(s["senators"]) == 2 for s in states)
    for s in states:
        for sen in s["senators"]:
            assert sen["state_on_senator_scale"]["s"] == "NOT_AVAILABLE" and sen["distance"]["s"] == "NOT_AVAILABLE"
            assert sen["state_public_estimate"]["se"] and sen["state_public_estimate"]["period"]
    a = data["p4"]["anchors"]
    assert [x["name"] for x in a] == ["Bernie Sanders", "Joe Biden", "JD Vance"]
    assert [x["score"]["d"] for x in a] == ["−0.546", "−0.314", "0.850"]
    assert a[1]["basis"].startswith("Senate voting record") and "not his presidency" in a[1]["basis"]
    assert a[2]["basis"].startswith("Senate voting record") and "not his vice presidency" in a[2]["basis"]
    assert "House" in a[0]["basis"] and "Senate" in a[0]["basis"]
    assert all(x["score"]["m"] == "p4.reference_anchor" for x in a)


def test_anchors_appear_only_in_pillar4(data):
    elsewhere = json.dumps({k: data[k] for k in ("p5", "p6")})
    assert "p4.reference_anchor" not in elsewhere and "Biden" not in elsewhere and "Vance" not in elsewhere


def test_pillar5_main_result_is_the_mean_and_medians_are_details_only(data):
    p5 = data["p5"]
    assert (p5["plain"]["m"], p5["weighted"]["m"], p5["diff"]["m"]) == ("p5.plain_mean", "p5.weighted_mean", "p5.weighting_difference")
    assert (p5["plain"]["d"], p5["weighted"]["d"], p5["diff"]["d"]) == ("0.120", "0.083", "+0.037")
    assert {p5[k]["m"] for k in ("median", "wmedian", "mdiff")} == {"p5.plain_median", "p5.weighted_median", "p5.median_difference"}
    assert p5["national"]["s"] == p5["gap"]["s"] == "NOT_AVAILABLE"
    # in the page, the medians are rendered only into the details block
    start = TEMPLATE.index("$('p5-medians')")
    uses = [m.start() for m in re.finditer(r"P5\.(median|wmedian|mdiff)\b", TEMPLATE)]
    assert len(uses) == 3 and all(start < u < start + 600 for u in uses)
    assert '<summary><span>Medians (secondary comparison)</span></summary>\n    <div id="p5-medians">' in TEMPLATE


def test_pillar5_plain_language_card():
    """The approved Pillar 5 wording (2026-09-25): title, three rows, explanation and "What does this mean?"."""
    start = TEMPLATE.index("// ================= Pillar 5")
    p5 = TEMPLATE[start:TEMPLATE.index("// ================= Pillar 6")]
    for text in ("Counting states vs. weighting by population", "Senate average", "Each senator counted equally",
                 "Population-weighted", "Difference",
                 "Every state gets two senators regardless of its population. Normally, each senator counts equally when "
                 "calculating the Senate average. If instead senators are weighted by the number of people their state "
                 "represents, the average changes from '+num(pl)+' to '+num(w)+'.",
                 "That is a difference of '+num(d)+'. ",
                 "population weighting moves the Senate average slightly toward the '+side+' side of Voteview’s −1 to +1 voting scale.",
                 "<summary><span>What does this mean?</span></summary>",
                 "Population weighting gives senators from larger states more weight and senators from smaller states less "
                 "weight. The two senators from the same state split that state’s population weight evenly.",
                 "This describes Senate voting records and state populations only. It does not tell us which laws passed, what "
                 "voters believe, or why Congress made a decision. This weighting method is still a CivicAlign candidate "
                 "method, not a final scientific standard."):
        assert text in p5, text
    # the side follows the sign of plain - weighted, so the words cannot contradict the numbers
    assert "var side=d.v>0?'liberal':'conservative';" in p5
    # the numbers in the card are the saved Pillar 5 main result, shown through num()
    assert "num(pl)" in p5 and "num(w)" in p5 and "num(d)" in p5
    for claim in ("because", "caused", "led to", "resulted in", "bill", "biased", "extreme", "unfair", "fair"):
        assert not re.search(rf"\b{claim}\b", p5, flags=re.I), claim


def test_pillar6_uses_only_committee_median_and_senate_drift(data):
    cs = data["p6"]["committees"]
    assert len(cs) == 16
    for c in cs:
        assert set(c) == {"code", "name", "listed", "scored", "left_out", "committee_median", "committee_senate_drift", "committee_public_drift"}
        assert c["committee_public_drift"]["s"] == "NOT_AVAILABLE"
    ssap = next(c for c in cs if c["code"] == "SSAP")
    assert (ssap["committee_median"]["d"], ssap["committee_senate_drift"]["d"]) == ("−0.046", "−0.366")
    assert data["p6"]["senate_median"]["d"] == "0.320" and data["p6"]["national"]["s"] == "NOT_AVAILABLE"


def test_unavailable_values_say_why_on_the_page(data):
    na = [n for n in numbers(data) if n["s"] == "NOT_AVAILABLE"]
    assert na and all(M.REGISTRY[n["m"]]["not_available"] for n in na)
    assert "function why(n)" in TEMPLATE and "'<p class=\"why\">Why: '" in TEMPLATE
    assert "row(" in TEMPLATE and "+why(n)+" in TEMPLATE


# ---- what the pages never contain -------------------------------------------------------------------

def test_no_0_100_scale(pages):
    for name, page in pages.items():
        assert not re.search(r"\b0\s*(?:-|to|–)\s*100\b|/\s*100\b|display-scale|p100|\*\s*50\s*\+\s*50", page), name


def test_no_political_judgment_labels(pages):
    banned = (r"\b(extreme|extremist|moderate|centrist|radical|fringe|biased|good|bad|misaligned|aligned|out of step|"
              r"gatekeep\w*|obstruct\w*|blocked|betray\w*|defian\w*|ranking|ranked|representation score|representative score)\b")
    for name, page in pages.items():
        hits = re.findall(banned, visible_text(page), flags=re.I)
        assert not hits, (name, hits)


def test_no_engine_a_or_bill_content(pages):
    for name, page in pages.items():
        text = visible_text(page)
        for phrase in ("Recent votes", "recent vote", "receipt", "Yea", "Nay", "sent forward", "Yes / No", "sponsor",
                       "scorecard", "bill ideology", "liberal bill", "conservative bill", "Pillar 1", "Maker", "Checker"):
            assert phrase not in text, (name, phrase)


def test_the_builder_reads_only_engine_b_results():
    tree = ast.parse((ROOT / "src" / "civicalign" / "build_pages.py").read_text())
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mods += [(node.module or "")] + [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
    forbidden = ("explain", "evaluation", "receipts", "billflow", "billstatus", "senate_votes", "pipeline", "peers",
                 "representation", "gatekeeping", "output_ideology", "landmarks", "whitepaper", "pillars", "inputs")
    assert not [m for m in mods if any(f in m for f in forbidden)], mods
    src = (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert "C.compute(" not in src and "_calculate" not in src, "the builder never recalculates"


# ---- the committed preview pages are what the builder produces -------------------------------------------

def test_committed_preview_pages_are_current(pages):
    for name, text in pages.items():
        f = ROOT / "demo" / "next" / name
        if not f.exists():
            pytest.skip("no built preview pages")
        assert f.read_text() == text, f"demo/next/{name} is stale: run python -m civicalign.build_pages"


def test_the_build_is_deterministic(pages):
    assert BP.build(DEFAULT) == pages


def test_the_old_page_is_untouched():
    """The old page and builder still serve the live product and Engine A's checks until Step 5."""
    assert (ROOT / "demo" / "senator-check.html").exists() and (ROOT / "src" / "civicalign" / "build_demo.py").exists()
    assert BP.OUT == ROOT / "demo" / "next"
