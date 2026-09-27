"""Pillars 4-6: the page builder and the three views (Step 4), published to demo/ (Step 5A).

The builder reads only the saved result record, the methodology registry, the
saved anchors and the official committee names. These tests check the data it
embeds, the committed published pages in demo/, and what the pages must never
contain. Nothing here writes to data/ideology/ or demo/."""
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
from civicalign.ideology import compute as C
from civicalign.ideology import ingest as I
from civicalign.ideology import methodology as M
from civicalign.ideology.store import Table

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "src" / "civicalign" / "templates" / "senator-check.template.html").read_text()


def _block(name: str) -> str:
    """One part of the page's script, between its "// ===== <name> =====" marker and the next one."""
    s = TEMPLATE[TEMPLATE.index("<script>"):]
    start = s.index(f"// ===== {name} =====")
    nxt = s.find("// ===== ", start + 10)
    return s[start:nxt if nxt > 0 else len(s)]


@pytest.fixture(scope="module")
def data():
    try:
        return BP.payload(DEFAULT)
    except BP.BuildError as e:
        pytest.skip(f"no saved result to build from: {e}")


@pytest.fixture(scope="module")
def pages():
    return BP.build(DEFAULT)


# ---- independent recomputation from the saved, verified data (real-data tests never pin current values) ----

def _half_up(v, decimals, signed=False):
    """The page's display rule, re-implemented here: half-up, U+2212 minus, + only when signed."""
    from decimal import ROUND_HALF_UP, Decimal
    d = Decimal(repr(v)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    d = abs(d) if d == 0 else d
    return ("\u2212" if d < 0 else "+" if signed and d > 0 else "") + f"{abs(d):.{decimals}f}"


def _saved():
    """Seated senators' scores, per-state weights and current committee members, read straight
    from the saved tables with separate code."""
    from fractions import Fraction
    from statistics import median
    sen = [r for r in Table(DEFAULT.ideology_dir, "senator_ideology").current() if r["congress"] == DEFAULT.congress and r["seated"]]
    scores = {r["bioguide_id"]: r["nominate_dim1"] for r in sen if r["nominate_dim1"] is not None}
    per_state = {}
    for r in sen:
        per_state[r["state"]] = per_state.get(r["state"], 0) + 1
    pops = {r["geography_id"]: r["population"] for r in Table(DEFAULT.ideology_dir, "state_population").current()
            if r["measurement_year"] == DEFAULT.pillar5_population_year and r["vintage"] == DEFAULT.pillar5_population_vintage}
    state = {r["bioguide_id"]: r["state"] for r in sen}
    w = {b: Fraction(pops[state[b]], per_state[state[b]]) for b in scores}
    plain = sum(scores.values()) / len(scores)
    weighted = float(sum(Fraction(x) * w[b] for b, x in scores.items()) / sum(w.values()))
    members = {}
    for e in Table(DEFAULT.ideology_dir, "committee_membership_events").current():
        if e["congress"] == DEFAULT.congress and e["event"] != "observed_left":
            members.setdefault(e["committee_id"], []).append(e["bioguide_id"])
    med = median(scores.values())
    cmeds = {c: median([scores[b] for b in ms if b in scores]) for c, ms in members.items()}
    return {"sen": sen, "scores": scores, "plain": plain, "weighted": weighted, "median": med, "committees": cmeds}


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
    """The page's own wording: without styles, and with the embedded data replaced by its
    strings minus official bill titles and sponsor names (the government's words, which
    CivicAlign must not alter; e.g. the "DEFIANCE Act", or "Fiscal Year" in a title)."""
    page = re.sub(r"<style>.*?</style>", " ", page, flags=re.S)
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S)
    if not m:
        return page
    data = json.loads(m.group(1))
    data.get("p5", {}).get("outcomes", {}).pop("bills", None)
    data.get("p6", {}).pop("bills", None)          # the committee bill lists: official titles and sponsor names

    def strings(o):
        if isinstance(o, dict):
            return " ".join(strings(v) for v in o.values())
        if isinstance(o, list):
            return " ".join(strings(v) for v in o)
        return o if isinstance(o, str) else ""
    return page[:m.start()] + " " + strings(data) + " " + page[m.end():]


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
    rec = BP.latest(DEFAULT)["results"]
    # Pillar 4 (4 per seated senator), anchors, Pillar 5 (10), Pillar 6 (5 per committee + Senate median and national,
    # the national shared with Pillar 5), Pillar 5 outcomes (5 passed + 7 enacted), Pillar 6 bills handled (11 per
    # committee) and one current score per sponsor in the committee bill lists: counted from the data, not pinned
    assert len(nums) == 4 * len(rec["pillar4"]) + 3 + 10 + 5 * len(rec["pillar6"]) + 2 - 1 + 12 + 11 * len(rec["pillar6"]) \
        + len(data["p6"]["sponsors"])
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


def test_the_page_only_shows_numbers_from_the_data_with_a_methodology_entry(pages):
    script = TEMPLATE[TEMPLATE.index("<script>"):]
    assert not re.search(r"\d\.\d{2,}", script), "no data value is written into the template"
    assert "throw new Error('number without a methodology entry" in script
    # counts and raw values go through reg() (cnt/rawv/bills); display positions are read as recorded (p0/p1/pts)
    shown = set(re.findall(r"esc\((\w+(?:\.\w+)*)\.d\)", script))
    assert shown <= {"reg(n)"}, shown
    for field in re.findall(r"\.(p0|p1|pts)\b", script):
        assert field in ("p0", "p1", "pts")


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
    f = cfg.ideology_dir / "metrics" / f"{C.index(cfg)[-1]['input_key']}.json"     # the latest result, whatever its values
    f.write_text(f.read_text().replace('"value":', '"value": ', 1))                  # any change to its bytes must be refused
    with pytest.raises(BP.BuildError, match="index hash"):
        BP.latest(cfg)


# ---- the three views ----------------------------------------------------------------------------

def test_pillar4_senators_and_exactly_three_labelled_anchors(data):
    states = data["p4"]["states"]
    saved = _saved()
    by_state = {}
    for r in saved["sen"]:
        by_state.setdefault(r["state"], set()).add(r["bioguide_id"])
    assert {s["code"]: {x["id"] for x in s["senators"]} for s in states} == by_state, "every seated senator, in their own state"
    for s in states:
        for sen in s["senators"]:
            if sen["id"] in saved["scores"]:
                assert sen["senator_score"]["v"] == saved["scores"][sen["id"]]
                assert sen["senator_score"]["d"] == _half_up(saved["scores"][sen["id"]], 3)
    for s in states:
        for sen in s["senators"]:
            assert sen["state_on_senator_scale"]["s"] == "NOT_AVAILABLE" and sen["distance"]["s"] == "NOT_AVAILABLE"
            assert sen["state_public_estimate"]["se"] and sen["state_public_estimate"]["period"]
    a = data["p4"]["anchors"]
    assert [x["name"] for x in a] == ["Bernie Sanders", "Joe Biden", "JD Vance"]
    stored = {r["anchor_id"]: r["nominate_dim1"] for r in Table(DEFAULT.ideology_dir, "reference_anchors").current()}
    assert [(x["score"]["v"], x["score"]["d"]) for x in a] == [(stored[x["id"]], _half_up(stored[x["id"]], 3)) for x in a]
    assert a[1]["basis"].startswith("Senate voting record") and "not his presidency" in a[1]["basis"]
    assert a[2]["basis"].startswith("Senate voting record") and "not his vice presidency" in a[2]["basis"]
    assert "House" in a[0]["basis"] and "Senate" in a[0]["basis"]
    assert all(x["score"]["m"] == "p4.reference_anchor" for x in a)


def test_anchors_appear_only_in_pillar4(data):
    # official bill titles and sponsor names in the committee bill lists are the government's words
    # (e.g. "Overturn Biden's Offshore Energy Ban Act"), not a use of a reference figure
    p6 = {**data["p6"], "bills": {b: {k: v for k, v in x.items() if k not in ("t", "sn")} for b, x in data["p6"].get("bills", {}).items()}}
    elsewhere = json.dumps({"p5": data["p5"], "p6": p6})
    assert "p4.reference_anchor" not in elsewhere and "Biden" not in elsewhere and "Vance" not in elsewhere


def test_pillar5_main_result_is_the_mean_and_medians_are_details_only(data):
    p5 = data["p5"]
    assert (p5["plain"]["m"], p5["weighted"]["m"], p5["diff"]["m"]) == ("p5.plain_mean", "p5.weighted_mean", "p5.weighting_difference")
    saved = _saved()
    diff = saved["plain"] - saved["weighted"]
    assert p5["plain"]["v"] == pytest.approx(saved["plain"], abs=1e-12) and p5["weighted"]["v"] == pytest.approx(saved["weighted"], abs=1e-12)
    assert p5["diff"]["v"] == pytest.approx(diff, abs=1e-12)
    assert (p5["plain"]["d"], p5["weighted"]["d"], p5["diff"]["d"]) == \
        (_half_up(p5["plain"]["v"], 3), _half_up(p5["weighted"]["v"], 3), _half_up(p5["diff"]["v"], 3, signed=True))
    assert p5["median"]["v"] == pytest.approx(saved["median"], abs=1e-12)
    assert {p5[k]["m"] for k in ("median", "wmedian", "mdiff")} == {"p5.plain_median", "p5.weighted_median", "p5.median_difference"}
    assert p5["national"]["s"] == p5["gap"]["s"] == "NOT_AVAILABLE"
    # in the page, the medians appear only inside "How is this calculated?" under the Senate's "See details"
    s = _block("The Senate as a whole")
    how = s.index("disc('How is this calculated?'")
    uses = [m.start() for m in re.finditer(r"P5\.(median|wmedian|mdiff)\b", s)]
    assert len(uses) == 6 and all(u > how for u in uses)


def test_pillar5_plain_language_card():
    """The approved redesign (2026-09-27): one line, one sentence by default; the approved card's wording in details."""
    s = _block("The Senate as a whole")
    default = s[s.index("$('whole').innerHTML="):]
    assert "esc(W.position)" in default and "esc(W.shift)" in default and "disc('See details',details)" in default
    assert "text:'Senate'" in default and "num:" not in default, "no headline number by default"
    for text in ("Every state gets two senators regardless of its population. Population weighting gives senators from states "
                 "with more people more weight.",
                 "Normally, each senator counts equally when "
                 "calculating the Senate average. If instead senators are weighted by the number of people their state "
                 "represents, the average changes from <strong>'+esc(pl.p1)+'</strong> to <strong>'+esc(w.p1)+'</strong>.",
                 "That is a difference of '+esc(d.pts)+' points. '+esc(W.shift_detail)+'",
                 "disc('What does this mean?'",
                 "Population weighting gives senators from larger states more weight and senators from smaller states less "
                 "weight. The two senators from the same state split that state’s population weight evenly.",
                 "This describes Senate voting records and state populations only. It does not tell us which laws passed, what "
                 "voters believe, or why Congress made a decision. This weighting method is still a CivicAlign candidate "
                 "method, not a final scientific standard."):
        assert text in s, text
    for claim in ("because", "caused", "led to", "resulted in", "biased", "extreme", "unfair", "fair"):
        assert not re.search(rf"\b{claim}\b", s, flags=re.I), claim


def test_the_senate_sentences_follow_the_rules(data):
    from civicalign.ideology import display as DS
    p5 = data["p5"]
    assert p5["wording"]["position"] == DS.senate_position_sentence(p5["plain"]["v"])
    assert p5["wording"]["shift"] == DS.population_shift_sentence(p5["diff"]["v"])
    assert p5["wording"]["shift_detail"] == DS.shift_detail_sentence(p5["diff"]["v"])
    assert re.fullmatch(r"The Senate sits (on the (liberal|conservative) side of the voting scale|close to Voteview’s zero point)\.",
                        p5["wording"]["position"])
    assert re.fullmatch(r"Weighting senators by state population (moves it (slightly )?toward the (liberal|conservative) side|does not move it)\.",
                        p5["wording"]["shift"])
    assert "bigger states" not in json.dumps(p5["wording"])


def test_pillar6_uses_only_committee_median_and_senate_drift(data):
    cs = data["p6"]["committees"]
    saved = _saved()
    assert {c["code"] for c in cs} == set(saved["committees"]) == set(BP.latest(DEFAULT)["results"]["pillar6"])
    for c in cs:
        assert set(c) == {"code", "name", "official_name", "name_source", "name_retrieved", "listed", "scored", "left_out",
                          "committee_median", "committee_senate_drift", "committee_public_drift", "bills", "sentence"}
        assert c["committee_public_drift"]["s"] == "NOT_AVAILABLE"
    for c in cs:     # every committee, recomputed from the saved membership and scores
        med, drift = saved["committees"][c["code"]], saved["committees"][c["code"]] - saved["median"]
        assert c["committee_median"]["v"] == pytest.approx(med, abs=1e-12) and c["committee_median"]["d"] == _half_up(c["committee_median"]["v"], 3)
        assert c["committee_senate_drift"]["v"] == pytest.approx(drift, abs=1e-12)
        assert c["committee_senate_drift"]["d"] == _half_up(c["committee_senate_drift"]["v"], 3, signed=True)
    assert data["p6"]["senate_median"]["v"] == pytest.approx(saved["median"], abs=1e-12)
    assert data["p6"]["senate_median"]["d"] == _half_up(data["p6"]["senate_median"]["v"], 3) and data["p6"]["national"]["s"] == "NOT_AVAILABLE"


def test_unavailable_values_say_why_on_the_page(data):
    na = [n for n in numbers(data) if n["s"] == "NOT_AVAILABLE"]
    assert na and all(M.REGISTRY[n["m"]]["not_available"] for n in na)
    s = _block("How it works")
    for eid in ("p4.distance", "p5.national_public", "p6.committee_public_drift"):
        assert f"M['{eid}'].not_available" in s, eid       # "What we can't measure yet" gives each reason
    assert "esc(on.r||M[on.m].not_available)" in TEMPLATE and "esc(dist.r||M[dist.m].not_available)" in TEMPLATE


# ---- what the pages never contain -------------------------------------------------------------------

def test_the_display_position_is_never_a_grade(pages):
    """0-100 appears only as a position on a line: never "/100", never called a score, grade, rating, rank or alignment."""
    disclaimer = "A position on a line, not a score, grade, rating, rank or alignment."     # the rule saying what it is not
    for name, page in pages.items():
        text = visible_text(page).replace(disclaimer, "")
        assert not re.search(r"/\s*100\b|out of 100|percent|%\s*(liberal|conservative)", text, re.I), name
        assert not re.search(r"\b(grade|graded|rating|rated|alignment score|approval|effectiveness|percentile)\b", text, re.I), name
    s = TEMPLATE[TEMPLATE.index("<script>"):]
    assert not re.search(r"score[^'<]{0,24}'\+\s*esc\([\w.]*\.p[01]\)", s), "a display position is never called a score"


def test_no_political_judgment_labels(pages):
    banned = (r"\b(extreme|extremist|moderate|centrist|radical|fringe|biased|good|bad|misaligned|aligned|out of step|"
              r"gatekeep\w*|obstruct\w*|blocked|betray\w*|defian\w*|ranking|ranked|representation score|representative score)\b")
    for name, page in pages.items():
        hits = re.findall(banned, visible_text(page), flags=re.I)
        assert not hits, (name, hits)


def test_no_engine_a_or_bill_content(pages):
    for name, page in pages.items():
        text = visible_text(page)
        # "sponsor" is now used on purpose (the Pillar 5 outcomes are grouped by sponsor voting position)
        for phrase in ("Recent votes", "recent vote", "receipt", "Yea", "Nay", "sent forward", "Yes / No",
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


# ---- Step 5A: the published pages, official committee names, Engine A separated -----------------------------

def test_published_pages_are_generated_by_the_new_builder(pages):
    assert BP.OUT == ROOT / "demo"
    for name, text in pages.items():
        f = ROOT / "demo" / name
        assert f.read_text() == text, f"demo/{name} is stale or not from build_pages: run python -m civicalign.build_pages"
    assert 'href="civicalign.css"' in pages["senator-check.html"] and 'href="civicalign.css"' in pages["methodology.html"]


def test_the_preview_folder_is_retired_and_templates_are_not_published():
    assert not (ROOT / "demo" / "next").exists(), "demo/next/ is no longer an output"
    assert "demo" + "/next" not in (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert not (ROOT / "demo" / "templates").exists(), "templates live in src/civicalign/templates/, outside the published folder"


def test_the_build_is_deterministic(pages):
    assert BP.build(DEFAULT) == pages


def test_committee_names_come_from_the_official_source(data):
    stored = {r["committee_id"]: r for r in Table(DEFAULT.ideology_dir, "committee_names").current()}
    for c in data["p6"]["committees"]:
        r = stored[c["code"]]
        assert (c["name"], c["official_name"]) == (r["display_name"], r["official_name"])
        assert c["official_name"] == "Senate Committee on " + c["name"] or c["official_name"] == "Senate Committee on the " + c["name"]
        assert c["name_source"] == I.COMMITTEE_LIST and r["source_url"].endswith("/committees-current.json") and not r["fixture"]


def test_no_fixed_committee_name_mapping_remains_in_the_builder():
    src = (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert "COMMITTEE_NAMES" not in src
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            assert not [k for k in keys if re.fullmatch(r"S[SL][A-Z]{2}", k)], keys
    assert not re.search(r"Agriculture|Appropriations|Judiciary|Armed Services", src)


def test_a_committee_without_an_official_name_stops_the_build(tmp_path):
    cfg = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "ideology")
    shutil.copytree(DEFAULT.ideology_dir, cfg.ideology_dir, ignore=shutil.ignore_patterns("committee_names.jsonl"))
    with pytest.raises(BP.BuildError, match="no official committee name"):
        BP.payload(cfg)


def test_engine_a_tests_no_longer_depend_on_the_pillars_4_6_page():
    for f in ("test_binding.py", "test_context.py", "test_evaluation.py", "test_floor_votes.py"):
        if not (ROOT / "tests" / f).exists():
            continue          # test_evaluation.py belongs to the separately developed Stage 3 work
        text = (ROOT / "tests" / f).read_text()
        assert "senator-check.html" not in text and "methodology.html" not in text and "checks(run(" not in text, f
    assert "pillar1_checks" in (ROOT / "tests" / "test_binding.py").read_text()
    assert "pillar1_checks" in (ROOT / "tests" / "test_context.py").read_text()


def test_engine_b_calculations_are_unchanged():
    """Names and the page switch are not calculation inputs: the saved result is still current and reproducible."""
    src = (ROOT / "src" / "civicalign" / "ideology" / "compute.py").read_text()
    assert "committee_names" not in src and "reference_anchors" not in src
    assert C.plan(DEFAULT)["mode"] == "unchanged"
    assert C.verify(DEFAULT) == []


RETIRED_MODULES = ("alignment", "chamber", "committees", "space", "uncertainty", "peers", "representation", "gatekeeping",
                   "output_ideology", "landmarks", "export", "whitepaper", "build_demo", "sources/state_prefs", "sources/elections")


def test_the_retired_pillars_4_6_code_is_gone():
    """Step 5B removed the old Pillars 4-6 path; nothing may import it again."""
    for m in RETIRED_MODULES:
        assert not (ROOT / "src" / "civicalign" / f"{m}.py").exists(), m
    assert not (ROOT / "demo" / "methodology.template.html").exists()
    names = {m.split("/")[-1] for m in RETIRED_MODULES}
    for f in (ROOT / "src" / "civicalign").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[-1]] + [a.name for a in node.names]
                assert not (set(mods) & names), (f.name, set(mods) & names)


# ---- page guardrails carried over from the retired test_published_pages / test_perspective (Step 5B) --------

def _script():
    return TEMPLATE[TEMPLATE.index("<script>"):]


def test_every_drawn_line_is_hidden_from_screen_readers_and_described_in_text():
    s = _script()
    fn = s[s.index("function scale(o)"):s.index("function settle(")]
    assert '<div class="pline" aria-hidden="true">' in fn and '<figcaption class="sr-only">\'+esc(o.spoken)+\'</figcaption>' in fn
    assert s.count("scale({") == 4, "senator, Senate (default and details) and committee lines"
    assert len(re.findall(r"(?<!o\.)\bspoken:", s)) == 4


def test_data_strings_are_escaped_before_html_insertion():
    s = _script()
    # plain-text strings escaped as a whole where they are inserted: screen-reader sentences (esc(o.spoken)),
    # disclosure labels (esc(label)) and live-region messages (textContent)
    assert "esc(o.spoken)" in s and "esc(label)" in s and "l.textContent=msg" in s
    s = re.sub(r"var spoken=[^;]*;", "", s)
    s = re.sub(r"spoken:'[^']*'(\+[^,}]*)*", "", s)
    s = re.sub(r"disc\('What about '\+st\.name\+'’s voters\?'", "", s)
    s = re.sub(r"say\('[^;]*\);", "", s)
    s = re.sub(r"setAttribute\('aria-label',[^;]*\)", "", s)          # set through the DOM, never parsed as HTML
    raw = re.findall(r"'\+\s*([a-z]\w*(?:\.\w+)*\.(?:name|official_name|name_source|basis|code|period|short|r|reason|label|title|t|sn|sponsor|side|sentence|party))\s*\+'", s)
    assert not raw, f"inserted without esc(): {raw}"
    assert "function esc(s)" in s and ".replace(/[&<>\"']/g" in s


def test_one_scrolling_page_with_simple_navigation():
    assert 'role="tab"' not in TEMPLATE and "tabpanel" not in TEMPLATE
    links = [("senators", "Your senators"), ("senate", "Senate"), ("committees", "Committees"), ("how", "How it works")]
    nav = re.findall(r'<li><a href="#([\w-]+)">([^<]+)</a></li>', TEMPLATE)
    assert nav == links * 2, "the section links, and the same links in the phone \"Jump to\" menu"
    assert '<nav aria-label="Sections">' in TEMPLATE and 'id="jump" aria-expanded="false" aria-controls="jump-menu">Jump to' in TEMPLATE
    assert "@media (max-width:599px){#barchip{display:none!important}.topbar nav{display:none}.jump{display:block}}" in TEMPLATE
    order = [m.group(1) for m in re.finditer(r'<section id="([\w-]+)" class="sec"', TEMPLATE)]
    assert order == ["senators", "senate", "senate-whole", "committees", "how"]
    assert TEMPLATE.index('id="senate"') < TEMPLATE.index('id="senate-whole"'), "what the Senate passed comes before the averages"


def test_sources_are_named_with_full_links(pages):
    page, meth = pages["senator-check.html"], pages["methodology.html"]
    assert 'href="https://doi.org/10.7910/DVN/BQKU4M"' in page
    for s in ("Voteview", "American Ideology Project", "Census", "congress-legislators"):
        assert s in page and s in meth, s
    assert "committees-current.json" in meth or "committees-current.json" in page


def test_survey_period_measurement_date_and_observed_dates_are_shown(data):
    assert "['Survey period',esc(pub.period||'')]" in TEMPLATE
    assert "['Measurement date',esc(m.measurement_date)]" in TEMPLATE
    assert "['Committee membership observed',esc(m.committee_observed)]" in TEMPLATE
    assert data["meta"]["measurement_date"] and data["meta"]["committee_observed"]
    assert all(s["senators"][0]["state_public_estimate"]["period"] for s in data["p4"]["states"])


def test_the_two_measurement_systems_are_described_as_separate(pages):
    text = visible_text(pages["senator-check.html"])
    assert "The survey uses a different measurement from senators’ voting records, so CivicAlign does not put them on the same line or compare them." in text
    assert "no distance between a senator and the state’s public is calculated" in text


def test_nothing_is_ordered_by_score(data):
    """States and committees are listed by name, senators within a state by surname; the only sorts in the page
    place reference labels on the line (by position, for spacing) and rank search matches by relevance."""
    names = [s["name"] for s in data["p4"]["states"]]
    assert names == sorted(names)
    cnames = [c["name"] for c in data["p6"]["committees"]]
    assert cnames == sorted(cnames)
    for s in data["p4"]["states"]:
        assert [x["short"] for x in s["senators"]] == sorted(x["short"] for x in s["senators"])
    sorts = re.findall(r"\.sort\(function\(a,b\)\{return ([^}]*)\}\)", _script())
    assert sorted(sorts) == ["a.x-b.x", "kinds[a.it.kind]-kinds[b.it.kind]||b.rel-a.rel||a.i-b.i"], sorts
    assert _script().count(".sort(") == 2


def test_both_colour_themes_are_defined():
    css = (ROOT / "demo" / "civicalign.css").read_text()
    assert "prefers-color-scheme:dark" in css and ':root[data-theme="dark"]' in css


# ---- Pillar 5: what the Senate actually passed (legislative outcomes by sponsor voting position) ----------

from civicalign.ideology import bill_outcomes as BO     # noqa: E402
from civicalign.ideology import bill_tallies as BT      # noqa: E402
from civicalign.ideology import bills as BL             # noqa: E402

CLASSES = ("LIBERAL_SPONSOR", "CONSERVATIVE_SPONSOR", "ZERO_SCORE_SPONSOR", "UNKNOWN")


def _outcome_script():
    return _block("What the Senate passed")


def test_outcome_counts_come_from_the_saved_tables(data):
    O = data["p5"]["outcomes"]
    t = BT.passed_senate_tally(BL.current(DEFAULT), BO.current(DEFAULT))
    for part in ("passed_senate", "enacted"):
        assert O[part]["total"]["ids"] == t[part]["bill_ids"] and O[part]["total"]["v"] == t[part]["total"]
        for c in CLASSES:
            assert O[part][c]["ids"] == t[part]["by_classification"][c]["bill_ids"]
    assert O["enacted"]["public_law_number_pending"]["ids"] == t["public_law_number_pending"]["bill_ids"]
    # nothing about these counts is written into the page: the only number literal in the card's code is the
    # 100 that turns counts into bar widths, and no current count appears as a literal
    s = re.sub(r"//[^\n]*", "", _outcome_script())      # code only, not its comments ("Pillar 5")
    assert set(re.findall(r"\b\d{2,}\b", s)) <= {"100"}, "the counts must be read from the data, never written in"
    live = {O[p][k]["v"] for p in ("passed_senate", "enacted") for k in ("total",) + CLASSES}
    assert not [v for v in live if v >= 2 and re.search(rf"(?<![\w.]){v}(?![\w.])", s)], live


def test_passed_senate_and_enacted_stay_separate(data):
    O = data["p5"]["outcomes"]
    assert O["passed_senate"]["total"]["m"] == "p5.outcomes_passed_total" and O["enacted"]["total"]["m"] == "p5.outcomes_enacted_total"
    assert O["passed_senate"]["total"]["p"] != O["enacted"]["total"]["p"]
    assert set(O["enacted"]["total"]["ids"]) <= set(O["passed_senate"]["total"]["ids"])
    s = _outcome_script()
    assert s.index("Passed the Senate") < s.index("Became law")


def test_every_outcome_count_traces_to_exact_bill_ids_and_official_actions(data):
    O = data["p5"]["outcomes"]
    outs = {r["bill_id"]: r for r in BO.current(DEFAULT)}
    cls = {r["bill_id"]: r for r in BL.current(DEFAULT)}
    for part in ("passed_senate", "enacted"):
        total = O[part]["total"]
        assert total["v"] == len(total["ids"]) == len(set(total["ids"]))
        assert sorted(sum((O[part][c]["ids"] for c in CLASSES), []), key=BT._order) == total["ids"], "the classes partition the total"
        for c in CLASSES:
            n = O[part][c]
            assert n["v"] == len(n["ids"]) and all(cls[b]["sponsor_classification"] == c for b in n["ids"])
    for b in O["passed_senate"]["total"]["ids"]:
        assert outs[b]["passed_senate"] and outs[b]["loc_passage_actions"], b
        assert outs[b]["bill_fingerprint"] == cls[b]["bill_fingerprint"], "the class and the outcome come from the same official record"
        assert b in O["bills"] and O["bills"][b]["label"] == f"S. {cls[b]['bill_number']}"
    for b in O["enacted"]["total"]["ids"]:
        assert outs[b]["enacted"] and (outs[b]["signed_by_president"] or outs[b]["public_law_number"])


def test_signed_bills_with_a_pending_number_count_as_enacted(data, pages):
    O = data["p5"]["outcomes"]
    pending, recorded = O["enacted"]["public_law_number_pending"], O["enacted"]["public_law_number_recorded"]
    assert set(pending["ids"]) <= set(O["enacted"]["total"]["ids"])
    assert recorded["v"] + pending["v"] == O["enacted"]["total"]["v"]
    assert all(O["bills"][b]["enacted"] and O["bills"][b]["pending"] and not O["bills"][b]["law"] for b in pending["ids"])
    s = _outcome_script()
    assert "were signed by the President and are waiting for one." in s
    assert "enacted: signed by the President" in s
    for phrase in ("not yet law", "not law yet", "not counted as law", "before becoming law", "not been enacted"):
        assert phrase not in visible_text(pages["senator-check.html"]).lower() and phrase not in s.lower(), phrase


def test_approved_scorecard_wording():
    """The redesign: two numbers by default (passed, became law); the sponsor split and approved wording behind "Explore"."""
    s = _outcome_script()
    default = s[s.index("$('passed').innerHTML="):]
    assert "cnt(P.total)" in default and "cnt(E.total)" in default and "disc('Explore the bills',explorePassed)" in default
    assert "split(" not in default, "the sponsor breakdown is not on the default view"
    for text in ("Passed the Senate: who sponsored them", "Became law", "' passed the Senate in the '",
                 "' become law.", "Grouped by who sponsored each bill, not by what the bill says.",
                 "' have public-law numbers; '",
                 "CivicAlign is not deciding whether a bill itself is liberal or conservative. Each bill is grouped only by the "
                 "DW-NOMINATE voting score of the senator who sponsored it. A negative sponsor score appears on the liberal side of "
                 "Voteview’s scale; a positive score appears on the conservative side.",
                 "This gives readers a simple way to see the voting positions of the senators whose bills moved through the Senate, "
                 "without using AI to guess the ideology of the legislation.",
                 "These counts do not prove that the Senate’s ideological average caused these bills to pass.",
                 "Becoming law also depends on the House and the President, not only on the Senate."):
        assert text in s, text
    for text in ("Sponsored by senators on the liberal side of the Voteview scale", "Sponsored by senators on the conservative side of the Voteview scale",
                 "See the bills sponsored by senators on the liberal side of the Voteview scale"):
        assert text in _script(), text


def test_no_liberal_or_conservative_bills_anywhere(pages):
    for text in [visible_text(pages["senator-check.html"]), pages["methodology.html"], TEMPLATE,
                 (ROOT / "src" / "civicalign" / "ideology" / "methodology.py").read_text(),
                 (ROOT / "src" / "civicalign" / "build_pages.py").read_text()]:
        assert not re.search(r"\b(liberal|conservative) (bill|bills|legislation|law|laws)\b", text, re.I)


def test_no_causal_claim_links_senate_ideology_to_these_outcomes():
    s = _outcome_script().replace("These counts do not prove that the Senate’s ideological average caused these bills to pass.", "")
    for phrase in ("because", "caused", "cause ", "led to", "resulted in", "result of", "due to", "thanks to", "explains why",
                   "responsible for", "drove", "driven by"):
        assert phrase not in s.lower(), phrase
    assert "do not prove" in _outcome_script()


def test_no_llm_in_the_scorecard_path():
    for f in (ROOT / "src" / "civicalign" / "build_pages.py", ROOT / "src" / "civicalign" / "templates" / "senator-check.template.html",
              ROOT / "src" / "civicalign" / "ideology" / "bill_tallies.py"):
        src = f.read_text()
        assert not re.search(r"openai|anthropic|langchain|claude|gpt-|llama|transformers|huggingface|cohere|gemini|ollama", src, re.I), f.name
        assert "subprocess" not in src and "urllib" not in src and "fetch(" not in src, f.name


def test_every_outcome_number_has_methodology(data, pages):
    O = data["p5"]["outcomes"]
    nums = [O[p][k] for p in ("passed_senate", "enacted") for k in ("total",) + CLASSES] + \
           [O["enacted"]["public_law_number_recorded"], O["enacted"]["public_law_number_pending"]]
    for n in nums:
        e = M.REGISTRY[n["m"]]
        assert e["kind"] == "outcome" and M.entry_for(n["p"])["id"] == n["m"] and f'id="{n["m"]}"' in pages["methodology.html"]
        versions = " ".join(data["methods"][n["m"]]["versions"])
        assert "outcome rule — senate_passage_loc17000_v1" in versions and "enactment rule — enactment_signature_or_public_law_v1" in versions
        assert "classification rule — sponsor_nominate_dim1_sign_v1" in versions and "bill archive versions — source version" in versions
    assert "not the content or ideology of the bill" in " ".join(M.REGISTRY["p5.outcomes_passed_by_sponsor"]["limitations"])


def test_bill_lists_are_behind_see_bills_not_on_the_main_screen():
    s = _outcome_script()
    assert "return n.v?disc(g.see,function(){return billList(n.ids,outcomeRow(enacted),'bills')}):''" in s
    assert s.count("billList(") == 1, "the bill list is built only inside the See bills sections, when opened"
    assert "LISTS[key]={ids:ids,row:row,shown:20" in _script() and "Show more" in _script()


def test_the_page_uses_the_latest_bill_table_versions(data):
    assert data["p5"]["outcomes"]["meta"]["table_fingerprints"] == BO.table_fingerprints(DEFAULT)
    iv = data["p5"]["outcomes"]["meta"]["input_versions"]
    assert iv == BO.input_versions(DEFAULT)
    for key in ("bill_sponsor_classifications", "senate_bill_outcomes", "senator_ideology", "voteview_source_versions",
                "bill_status_archive", "classification_rule", "outcome_rule", "enactment_rule"):
        assert iv[key], key
    now = BL.current_sponsor_scores(DEFAULT)
    cls = {r["bill_id"]: r for r in BL.current(DEFAULT)}
    for b, x in data["p5"]["outcomes"]["bills"].items():     # a bill's exact sponsor score is the CURRENT one, from senator_ideology
        assert x["sponsor_score"] == now[cls[b]["sponsor_bioguide_id"]]["score"], b
    assert BO.verify(DEFAULT) == [], "the tables the page was built from are current with the verified snapshot"
