"""The supervisor must confirm every published number from the raw files, and catch a wrong one.

Engine B (Pillars 4-6): each sabotage below changes one number or record on a
copy -- the result record, a stored table, the page's embedded data -- and the
matching check must fail. Pillar 1: the three binding and context sabotage
tests are unchanged from before Step 5B.
"""
import copy
import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from civicalign.agents import supervisor as S
from civicalign.config import DEFAULT
from civicalign.ideology import compute as C
from civicalign.ideology.store import Table

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def raw():
    return S.eb_raw(DEFAULT)


@pytest.fixture(scope="module")
def record():
    return C.load_record(DEFAULT, C.index(DEFAULT)[-1]["input_key"])


@pytest.fixture(scope="module")
def page_data():
    return S.eb_page_data((ROOT / "demo" / "senator-check.html").read_text())


@pytest.fixture(scope="module")
def senators():
    return Table(DEFAULT.ideology_dir, "senator_ideology").current()


@pytest.fixture(scope="module")
def anchors():
    return Table(DEFAULT.ideology_dir, "reference_anchors").current()


@pytest.fixture(scope="module")
def names():
    return Table(DEFAULT.ideology_dir, "committee_names").current()


def failed(checks, prefix):
    return [c for c in checks if not c.ok and c.name.startswith(prefix)]


# ---- everything confirmed -----------------------------------------------------------------------------

def test_supervisor_confirms_every_figure():
    results = S.checks(DEFAULT)
    bad = [c.line() for c in results if not c.ok]
    assert not bad, "\n".join(bad)
    names_ = [c.name for c in results]
    for required in ("Engine B: every stored senator nominate_dim1 re-read from Voteview",
                     "Engine B: Pillar 5 Senate mean (each senator counted equally)",
                     "Engine B: Pillar 5 population-weighted Senate mean", "Engine B: Pillar 5 population weighting difference",
                     "Engine B: Pillar 5 details: Senate median", "Engine B: Pillar 5 details: population-weighted median",
                     "Engine B: every committee median recomputed", "Engine B: every committee-to-Senate drift recomputed",
                     "Engine B: three anchors match the Voteview source", "Engine B: committee names match the official list",
                     "Engine B: no senator-to-state distance while the bridge is NONE",
                     "Engine B: no Senate-to-public gap while the national estimate is unresolved",
                     "Engine B: no committee-to-public drift while bridge and national estimate are unavailable",
                     "Engine B: every displayed number has methodology and equals the record",
                     "Engine B: every stored record valid and hash-chained", "Engine B: stored records append-only against the last commit",
                     "Pillar 1 bindings re-derived from cached first-party files",
                     "Pillar 1 context and packets re-derived from tracked artefacts"):
        assert required in names_, required


def test_the_supervisor_does_not_reuse_the_engine_b_calculations():
    src = (ROOT / "src" / "civicalign" / "agents" / "supervisor.py").read_text()
    for forbidden in ("ideology.pillars", "ideology import pillars", "ideology.inputs", "from ..pipeline", "build_demo", "peers"):
        assert forbidden not in src, forbidden


# ---- the recount catches a wrong number --------------------------------------------------------------

def test_a_wrong_senator_score_is_caught(raw, record, senators):
    r = copy.deepcopy(record)
    r["results"]["pillar4"][0]["senator_score"]["value"] += 0.001
    assert failed(S.eb_recount_checks(DEFAULT, raw, r, senators), "Engine B: every seated senator's score")
    s = copy.deepcopy(senators)
    s[0]["nominate_dim1"] = 0.5
    assert failed(S.eb_recount_checks(DEFAULT, raw, record, s), "Engine B: every stored senator nominate_dim1")


@pytest.mark.parametrize("path,check", [
    (("pillar5", "plain_center"), "Engine B: Pillar 5 Senate mean"),
    (("pillar5", "population_weighted_center"), "Engine B: Pillar 5 population-weighted Senate mean"),
    (("pillar5", "population_weighting_difference"), "Engine B: Pillar 5 population weighting difference"),
    (("pillar5", "details", "chamber_median"), "Engine B: Pillar 5 details: Senate median"),
    (("pillar5", "details", "methods", "population_weighted_median_v1", "population_weighted_center"),
     "Engine B: Pillar 5 details: population-weighted median"),
])
def test_a_wrong_pillar5_number_is_caught(raw, record, senators, path, check):
    r = copy.deepcopy(record)
    node = r["results"]
    for k in path:
        node = node[k]
    node["value"] += 1e-4
    assert failed(S.eb_recount_checks(DEFAULT, raw, r, senators), check)


def test_a_wrong_committee_median_or_drift_is_caught(raw, record, senators):
    r = copy.deepcopy(record)
    r["results"]["pillar6"]["SSAP"]["committee_median"]["value"] += 0.01
    assert failed(S.eb_recount_checks(DEFAULT, raw, r, senators), "Engine B: every committee median recomputed")
    r = copy.deepcopy(record)
    r["results"]["pillar6"]["SSGA"]["committee_senate_drift"]["value"] = -r["results"]["pillar6"]["SSGA"]["committee_senate_drift"]["value"]
    assert failed(S.eb_recount_checks(DEFAULT, raw, r, senators), "Engine B: every committee-to-Senate drift recomputed")


# ---- anchors and committee names against their sources -------------------------------------------------

def test_a_wrong_anchor_is_caught(raw, anchors, page_data):
    a = copy.deepcopy(anchors)
    a[1]["nominate_dim1"] = -0.32                     # Biden's presidential estimate, not his Senate record
    assert failed(S.eb_anchor_checks(DEFAULT, raw, a, page_data), "Engine B: three anchors match the Voteview source")
    assert failed(S.eb_anchor_checks(DEFAULT, raw, a[:2], page_data), "Engine B: three anchors match the Voteview source")
    p = copy.deepcopy(page_data)
    p["p5"]["extra_anchor"] = p["p4"]["anchors"][0]["score"]
    assert failed(S.eb_anchor_checks(DEFAULT, raw, anchors, p), "Engine B: page shows exactly the stored anchors")


def test_a_wrong_committee_name_is_caught(raw, names, record, page_data):
    n = copy.deepcopy(names)
    n[0]["display_name"] = "Invented"
    assert failed(S.eb_name_checks(raw, n, record, page_data), "Engine B: committee names match the official list")
    assert failed(S.eb_name_checks(raw, names[1:], record, page_data), "Engine B: committee names match the official list")
    p = copy.deepcopy(page_data)
    p["p6"]["committees"][0]["name"] = "Agriculture"
    assert failed(S.eb_name_checks(raw, names, record, p), "Engine B: page committee names are the official names")


# ---- gating: nothing that needs the bridge or a national estimate may appear ----------------------------

def test_a_distance_while_the_bridge_is_none_is_caught(record, page_data):
    r = copy.deepcopy(record)
    r["results"]["pillar4"][3]["distance"] = {"value": 0.1, "status": "AVAILABLE", "units": "x", "reason": None}
    assert failed(S.eb_gating_checks(r, "NONE", page_data), "Engine B: no senator-to-state distance")


def test_a_public_gap_or_committee_public_drift_is_caught(record, page_data):
    r = copy.deepcopy(record)
    r["results"]["pillar5"]["chamber_public_gap"]["value"] = 0.2
    assert failed(S.eb_gating_checks(r, "NONE", page_data), "Engine B: no Senate-to-public gap")
    r = copy.deepcopy(record)
    r["results"]["pillar6"]["SSFI"]["committee_public_drift"].update(value=0.1, status="PROVISIONAL")
    assert failed(S.eb_gating_checks(r, "NONE", page_data), "Engine B: no committee-to-public drift")
    p = copy.deepcopy(page_data)
    p["p5"]["national"].update(v=0.0, d="0.000", s="AVAILABLE")
    assert failed(S.eb_gating_checks(record, "NONE", p), "Engine B: the page shows those as not available")


# ---- methodology and the page ---------------------------------------------------------------------------

def test_a_page_number_without_methodology_or_not_equal_to_the_record_is_caught(record, anchors, page_data):
    meth = (ROOT / "demo" / "methodology.html").read_text()
    assert not failed(S.eb_methodology_checks(record, anchors, page_data, meth), "Engine B:")
    for mutate in (lambda p: p["p5"]["weighted"].update(m="p5.unregistered"),
                   lambda p: p["p5"]["weighted"].update(v=0.09),
                   lambda p: p["p6"]["committees"][2]["committee_median"].update(d="0.99"),
                   lambda p: p["p4"]["states"][0]["senators"][0]["senator_score"].update(p="pillar4.999.senator_score")):
        p = copy.deepcopy(page_data); mutate(p)
        assert failed(S.eb_methodology_checks(record, anchors, p, meth), "Engine B: every displayed number has methodology")
    assert failed(S.eb_methodology_checks(record, anchors, page_data, meth.replace('id="p5.weighted_mean"', 'id="x"')),
                  "Engine B: every registry entry is on the page and in the methodology page")


def test_a_hand_edited_published_page_is_caught(tmp_path):
    for n in ("senator-check.html", "methodology.html"):
        shutil.copy(ROOT / "demo" / n, tmp_path / n)
    assert not failed(S.eb_page_current_checks(DEFAULT, tmp_path), "Engine B:")
    (tmp_path / "senator-check.html").write_text((tmp_path / "senator-check.html").read_text().replace("Senate average", "Senate avg", 1))
    assert failed(S.eb_page_current_checks(DEFAULT, tmp_path), "Engine B: published pages are the builder's output")


# ---- the stored records: valid, chained and append-only --------------------------------------------------

def _copy_store(tmp_path):
    cfg = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "ideology")
    shutil.copytree(DEFAULT.ideology_dir, cfg.ideology_dir)
    return cfg


def test_an_edited_stored_record_is_caught(tmp_path):
    cfg = _copy_store(tmp_path)
    f = cfg.ideology_dir / "state_population.jsonl"
    lines = f.read_text().splitlines()
    lines[5] = lines[5].replace('"population":', '"population":1', 1)
    f.write_text("\n".join(lines) + "\n")
    assert failed(S.eb_store_checks(cfg), "Engine B: every stored record valid and hash-chained")


def test_a_rewritten_committed_record_is_caught(tmp_path, monkeypatch):
    cfg = _copy_store(tmp_path)
    assert not failed(S.eb_store_checks(cfg), "Engine B: stored records append-only")   # a copy outside git: nothing to compare
    # pretend the last commit had one more line than the file now has: a deletion
    monkeypatch.setattr(S, "_eb_git_head", lambda f: f.read_text() + '{"deleted": true}\n' if f.name == "committee_names.jsonl" else None)
    assert failed(S.eb_store_checks(cfg), "Engine B: stored records append-only against the last commit")


# ---- Pillar 1: unchanged ------------------------------------------------------------------------------------

def test_pillar1_checks_are_part_of_every_run():
    assert [c.name for c in S.pillar1_checks(DEFAULT)] == [c.name for c in S.checks(DEFAULT) if c.name.startswith("Pillar 1")]


def _copy_of_bindings(tmp_path):
    """A Config whose Pillar 1 records are a scratch copy, so they can be sabotaged."""
    import dataclasses
    import shutil
    from civicalign.config import Config
    dst = tmp_path / "119"
    shutil.copytree(DEFAULT.bindings_dir, dst)

    class Scratch(Config):
        @property
        def bindings_dir(self):
            return dst
    return Scratch(**{f.name: getattr(DEFAULT, f.name) for f in dataclasses.fields(DEFAULT)}), dst


def _edit(path, fn):
    import json
    doc = json.loads(path.read_text()); fn(doc); path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def test_supervisor_catches_a_wrong_next_step(tmp_path):
    from civicalign.agents.supervisor import _binding_checks
    cfg, d = _copy_of_bindings(tmp_path)
    assert _binding_checks(cfg, {}, {})[0].ok
    # S.2 is a Senate bill: it goes to the House, never "back"
    _edit(d / "vote_119_2_00163.json", lambda b: b["receipt"]["next_step"].update(
        actual="Because the Senate changed the text, the amended bill goes back to the House."))
    c = _binding_checks(cfg, {}, {})[0]
    assert not c.ok and "vote_119_2_00163" in c.detail


def test_supervisor_catches_a_failed_vote_described_as_advancing(tmp_path):
    from civicalign.agents.supervisor import _binding_checks
    cfg, d = _copy_of_bindings(tmp_path)
    _edit(d / "vote_119_1_00225.json", lambda b: b["receipt"]["next_step"].update(actual="The joint resolution next goes to the House."))
    c = _binding_checks(cfg, {}, {})[0]
    assert not c.ok and "advancing" in c.detail


def test_supervisor_catches_content_on_a_tracked_reference_and_wrong_metrics(tmp_path):
    from civicalign.agents.supervisor import _context_checks
    cfg, d = _copy_of_bindings(tmp_path)
    assert _context_checks(cfg)[0].ok
    _edit(d / "packets" / "vote_119_1_00095.packet.json", lambda p: p["tracked_references"][0].update(content="<section>…</section>"))
    c = _context_checks(cfg)[0]
    assert not c.ok and "tracked reference" in c.detail
    cfg, d = _copy_of_bindings(tmp_path / "second")
    _edit(d / "packets" / "vote_119_1_00160.packet.json", lambda p: p["metrics"].update(total_source_chars=1))
    c = _context_checks(cfg)[0]
    assert not c.ok and "metrics" in c.detail


# ---- Pillar 5 legislative-outcome counts --------------------------------------------------------------------

def test_a_wrong_outcome_count_on_the_page_is_caught(raw, page_data):
    assert not failed(S.eb_outcome_checks(DEFAULT, raw, page_data), "Engine B:")
    p = copy.deepcopy(page_data)
    ids = p["p5"]["outcomes"]["passed_senate"]["LIBERAL_SPONSOR"]["ids"]
    p["p5"]["outcomes"]["passed_senate"]["CONSERVATIVE_SPONSOR"]["ids"].append(ids.pop())
    assert failed(S.eb_outcome_checks(DEFAULT, raw, p), "Engine B: Pillar 5 outcome counts")
    p = copy.deepcopy(page_data)
    p["p5"]["outcomes"]["enacted"]["public_law_number_pending"]["ids"] = []
    assert failed(S.eb_outcome_checks(DEFAULT, raw, p), "Engine B: Pillar 5 outcome counts")


def test_a_scorecard_built_from_old_bill_tables_is_caught(raw, page_data):
    p = copy.deepcopy(page_data)
    p["p5"]["outcomes"]["meta"]["table_fingerprints"]["senate_bill_outcomes"] = "0" * 64
    assert failed(S.eb_outcome_checks(DEFAULT, raw, p), "Engine B: scorecard uses the current, verified bill-table versions")
