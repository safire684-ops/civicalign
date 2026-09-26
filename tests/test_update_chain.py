"""The update is one verified snapshot or nothing.

These tests pin the architecture: a critical source that fails to refresh leaves
every file untouched; change detection looks at content, not timestamps; a new
source can be added to the accepted snapshot without refreshing the others; the
workflow gates publication on every check; and the snapshot records what a
reader needs to know about each source.

Since Step 5C the update runs daily on the Engine B pipeline: fetch -> verify ->
(Pillar 1 bind and context, unchanged) -> ingest -> bridge -> anchors -> compute
-> build pages -> tests -> supervisor -> commit. The old page builder and its
tests are gone from the automation.
"""
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from civicalign.agents import sources
from civicalign.agents.base import Agent, add_source, run_snapshot, zip_content_key, load_snapshot
from civicalign.agents.verify import checks as verify_checks
from civicalign.config import DEFAULT

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update.yml"
UPDATE_SH = ROOT / "scripts" / "update.sh"
REBUILD = __import__("re").compile(r"civicalign\.build_pages")                # the page build step
# the Engine B steps, in the order both the workflow and update.sh must run them
ENGINE_B_ORDER = ["-m civicalign.agents", "civicalign.agents.verify", "civicalign.ideology.ingest",
                  "civicalign.ideology.bridge", "civicalign.ideology.anchors", "-m civicalign.ideology.bills",
                  "-m civicalign.ideology.bill_outcomes", "bill_outcomes --verify",
                  "civicalign.ideology.compute", "civicalign.build_pages", "-m pytest -q", "civicalign.agents.supervisor"]


def _agent(name, src: Path, raw: Path, ok=True, critical=True, key=None):
    return Agent(name=name, url=src.as_uri(), target=raw / src.name,
                 validate=(lambda p: None) if ok else (lambda p: "rejected on purpose"),
                 min_bytes=1, critical=critical, vintage=f"{name} vintage",
                 content_key=key or (lambda p: p.read_bytes().hex()))


def test_a_failed_critical_source_replaces_nothing(tmp_path):
    src, raw = tmp_path / "src", tmp_path / "raw"
    src.mkdir(); raw.mkdir()
    (src / "a.txt").write_text("new a"); (src / "b.txt").write_text("new b")
    (raw / "a.txt").write_text("old a"); (raw / "b.txt").write_text("old b")
    agents = [_agent("a", src / "a.txt", raw), _agent("b", src / "b.txt", raw, ok=False)]
    snap = run_snapshot(agents, raw)
    assert not snap.accepted and snap.failed_critical == ["b"]
    assert (raw / "a.txt").read_text() == "old a", "a good source must not be installed alongside a failed one"
    assert (raw / "b.txt").read_text() == "old b"
    assert not (raw / "SNAPSHOT.json").exists() and not (raw / ".staging").exists()


def test_a_missing_download_is_a_failure_not_a_silent_fallback(tmp_path):
    src, raw = tmp_path / "src", tmp_path / "raw"
    src.mkdir(); raw.mkdir()
    (src / "a.txt").write_text("new a"); (raw / "a.txt").write_text("old a"); (raw / "gone.txt").write_text("old")
    agents = [_agent("a", src / "a.txt", raw), _agent("gone", src / "gone.txt", raw)]  # gone.txt does not exist
    snap = run_snapshot(agents, raw)
    assert not snap.accepted and "gone" in snap.failed_critical
    assert (raw / "a.txt").read_text() == "old a"


def test_all_critical_sources_good_installs_the_whole_set_together(tmp_path):
    src, raw = tmp_path / "src", tmp_path / "raw"
    src.mkdir(); raw.mkdir()
    (src / "a.txt").write_text("new a"); (src / "b.txt").write_text("same b")
    (raw / "a.txt").write_text("old a"); (raw / "b.txt").write_text("same b")
    now = datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc)
    snap = run_snapshot([_agent("a", src / "a.txt", raw), _agent("b", src / "b.txt", raw)], raw, now=now)
    assert snap.accepted and snap.changed == ["a"]
    assert (raw / "a.txt").read_text() == "new a"
    rec = {s["name"]: s for s in load_snapshot(raw)["sources"]}
    for name in ("a", "b"):
        assert {"name", "url", "file", "bytes", "sha256", "content_key", "changed", "vintage",
                "critical", "content_changed_utc", "checked_utc"} <= set(rec[name])
    assert rec["a"]["changed"] is True and rec["a"]["content_changed_utc"] == "2026-09-28T11:00:00Z"
    assert rec["b"]["changed"] is False
    prov = (raw / "PROVENANCE.tsv").read_text().splitlines()
    assert any(ln.startswith("2026-09-28T11:00:00Z\ta.txt\t") for ln in prov)
    assert not any("\tb.txt\t" in ln for ln in prov), "unchanged content is not logged as a new download"


def test_unchanged_content_keeps_its_earlier_change_date(tmp_path):
    src, raw = tmp_path / "src", tmp_path / "raw"
    src.mkdir(); raw.mkdir()
    (src / "a.txt").write_text("v1")
    first = run_snapshot([_agent("a", src / "a.txt", raw)], raw, now=datetime(2026, 9, 21, tzinfo=timezone.utc))
    second = run_snapshot([_agent("a", src / "a.txt", raw)], raw, now=datetime(2026, 9, 28, tzinfo=timezone.utc))
    assert first.changed == ["a"] and second.changed == []
    rec = load_snapshot(raw)["sources"][0]
    assert rec["content_changed_utc"].startswith("2026-09-21") and rec["checked_utc"].startswith("2026-09-28")


def test_zip_change_detection_ignores_archive_timestamps(tmp_path):
    def make(path, stamp):
        with zipfile.ZipFile(path, "w") as z:
            info = zipfile.ZipInfo("bill.xml", date_time=stamp)
            z.writestr(info, "<bill>same content</bill>")
    make(tmp_path / "one.zip", (2026, 9, 21, 0, 0, 0)); make(tmp_path / "two.zip", (2026, 9, 28, 0, 0, 0))
    assert (tmp_path / "one.zip").read_bytes() != (tmp_path / "two.zip").read_bytes()
    assert zip_content_key(tmp_path / "one.zip") == zip_content_key(tmp_path / "two.zip")


def test_every_headline_source_is_critical_and_labelled_with_its_vintage():
    agents = {a.name: a for a in sources.all_agents()}
    for name in ("senator scores", "seated senators", "committee rosters", "committee names", "state ideology",
                 "state populations", "bill flow", "bill flow (House bills)", "floor roll calls", "senator votes"):
        assert agents[name].critical, name
        assert agents[name].vintage, name
    assert "2020 wave" in agents["state ideology"].vintage
    assert agents["bill flow"].content_key is zip_content_key


def test_verify_passes_on_the_current_snapshot():
    results = verify_checks(DEFAULT)
    failed = [c.line() for c in results if not c.ok]
    assert len(results) >= 8 and not failed, "\n".join(failed)


def _order_is_kept(text: str, steps: list[str]) -> bool:
    pos = [text.index(s) for s in steps]
    return pos == sorted(pos)


def _steps(text: str) -> str:
    """The script body without its header comment."""
    return text[text.index("PYTHONPATH=src"):]


def test_workflow_gates_publication_on_every_check():
    y = WORKFLOW.read_text()
    assert "|| echo" not in y and "FETCH_FAILED" not in y, "a fetch failure must fail the job"
    body = _steps(y)
    order = ENGINE_B_ORDER + ["git add demo/senator-check.html demo/methodology.html data/ideology",
                              "upload-pages-artifact"]
    assert _order_is_kept(body, order), \
        "fetch -> verify -> ingest -> bridge -> anchors -> bills -> outcomes -> check -> compute -> build -> tests -> supervisor -> commit -> upload"
    assert "needs: update" in y and "needs.update.result == 'success'" in y
    assert "continue-on-error" not in y


def test_the_update_runs_daily():
    y = WORKFLOW.read_text()
    assert 'cron: "0 11 * * *"' in y and "name: Daily update" in y
    assert "Weekday" not in (ROOT / "scripts" / "install-schedule.sh").read_text(), "the local schedule is daily too"


@pytest.mark.parametrize("path", [WORKFLOW, UPDATE_SH], ids=["workflow", "update.sh"])
def test_the_engine_b_steps_run_in_order(path):
    assert _order_is_kept(_steps(path.read_text()), ENGINE_B_ORDER), path.name


@pytest.mark.parametrize("path", [WORKFLOW, UPDATE_SH], ids=["workflow", "update.sh"])
def test_no_test_runs_before_the_pages_are_rebuilt(path):
    """The invariant behind the 24 Sept CI failure: tests compare the pages with
    the raw files, so every test and the supervisor must run after the pages
    have been built from the snapshot just fetched, and the build must come
    after the Pillar 1 bindings and Stage 2.5 check and after the Pillars 4-6
    ingest, bridge, anchors and compute for that snapshot."""
    import re
    body = _steps(path.read_text())
    build = REBUILD.search(body).start()
    for probe in ("pytest", "civicalign.agents.supervisor"):
        first = min(m.start() for m in re.finditer(re.escape(probe), body))
        assert first > build, f"{probe} runs before the build in {path.name}"
    for before in ("civicalign.explain.bind", "--check-fresh", "civicalign.ideology.ingest", "civicalign.ideology.bridge",
                   "civicalign.ideology.anchors", "civicalign.ideology.bills", "civicalign.ideology.bill_outcomes",
                   "bill_outcomes --verify", "civicalign.ideology.compute"):
        assert body.index(before) < build, before
    if path == WORKFLOW:
        assert body.index("git commit") > body.index("civicalign.agents.supervisor"), "commit only after every gate"


def test_the_workflow_and_update_sh_run_the_same_chain():
    import re
    runs = [re.findall(r"-m (civicalign[\w.]*(?: --[\w-]+)?|pytest)", _steps(p.read_text())) for p in (WORKFLOW, UPDATE_SH)]
    assert runs[0] == runs[1], runs


def test_pillar1_steps_are_unchanged():
    for path in (WORKFLOW, UPDATE_SH):
        text = path.read_text()
        assert "civicalign.explain.bind" in text and "civicalign.explain.context --check-fresh" in text, path.name
        assert "civicalign.evaluation" not in text, "no generation step in the automation"


def test_the_anchor_refresh_is_visual_only():
    """The anchors step refreshes the three reference figures; compute never reads them."""
    y = WORKFLOW.read_text()
    assert "Refresh the three reference anchors from the verified Voteview file (visual only)" in y
    compute = (ROOT / "src" / "civicalign" / "ideology" / "compute.py").read_text()
    assert "reference_anchors" not in compute and "anchors" not in compute


def test_the_commit_keeps_the_versioned_records():
    y = WORKFLOW.read_text()
    add = next(l for l in y.splitlines() if "git add demo/" in l)
    for f in ("demo/senator-check.html", "demo/methodology.html", "data/ideology", "data/ideology/bill_sponsor_classifications.jsonl",
              "data/ideology/senate_bill_outcomes.jsonl", "data/raw/PROVENANCE.tsv", "data/explanations"):
        assert f in add, f


def test_fresh_checkout_compares_with_the_committed_snapshot_not_the_missing_file(tmp_path):
    """On CI the raw files are not in git; only SNAPSHOT.json is. Identical
    content re-downloaded there must count as unchanged, keeping its earlier
    content-changed date."""
    src, raw = tmp_path / "src", tmp_path / "raw"
    src.mkdir(); raw.mkdir()
    (src / "a.txt").write_text("v1")
    run_snapshot([_agent("a", src / "a.txt", raw)], raw, now=datetime(2026, 9, 21, tzinfo=timezone.utc))
    (raw / "a.txt").unlink()                     # fresh checkout: file gone, snapshot kept
    snap = run_snapshot([_agent("a", src / "a.txt", raw)], raw, now=datetime(2026, 9, 28, tzinfo=timezone.utc))
    assert snap.accepted and snap.changed == []
    rec = load_snapshot(raw)["sources"][0]
    assert rec["content_changed_utc"].startswith("2026-09-21") and rec["checked_utc"].startswith("2026-09-28")
    assert (raw / "a.txt").read_text() == "v1"


def test_a_no_change_week_commits_nothing():
    y = WORKFLOW.read_text()
    assert 'git checkout -- data/raw/SNAPSHOT.json' in y, "a check-stamp-only change is discarded, not committed"
    assert y.index("git diff --cached --quiet") < y.index("git add data/raw/SNAPSHOT.json")


AUTOMATION = [WORKFLOW, UPDATE_SH] + sorted((ROOT / "scripts").glob("*.sh"))


@pytest.mark.parametrize("path", AUTOMATION, ids=lambda p: p.name)
def test_every_module_the_update_runs_exists(path):
    import re
    text = path.read_text()
    mods = set(re.findall(r"-m (civicalign(?:\.[a-z_]+)*)", text))
    missing = [m for m in mods if not ((ROOT / "src" / Path(*m.split("."))).with_suffix(".py").exists()
                                       or (ROOT / "src" / Path(*m.split(".")) / "__main__.py").exists())]
    missing += [f for f in re.findall(r"tests/\w+\.py", text) if not (ROOT / f).exists()]
    assert not missing, missing


# ---- adding one new source to the accepted snapshot (Step 5A) ------------------------------------------

def _snapshot_with_one_source(tmp_path):
    src, raw = tmp_path / "src", tmp_path / "raw"
    src.mkdir(); raw.mkdir()
    (src / "a.txt").write_text("v1")
    run_snapshot([_agent("a", src / "a.txt", raw)], raw, now=datetime(2026, 9, 21, tzinfo=timezone.utc))
    return src, raw


def test_add_source_adds_one_new_file_and_touches_nothing_else(tmp_path):
    src, raw = _snapshot_with_one_source(tmp_path)
    before = load_snapshot(raw)
    (src / "a.txt").write_text("v2")                      # upstream changed, but add_source must not refresh it
    (src / "b.txt").write_text("new")
    r = add_source(_agent("b", src / "b.txt", raw), raw, now=datetime(2026, 9, 26, tzinfo=timezone.utc))
    after = load_snapshot(raw)
    assert r.ok and r.changed
    assert after["run_utc"] == before["run_utc"] and after["sources"][0] == before["sources"][0]
    assert (raw / "a.txt").read_text() == "v1", "the other source keeps its accepted content"
    b = after["sources"][1]
    assert b["file"] == "b.txt" and b["content_changed_utc"].startswith("2026-09-26") and "without refreshing" in b["note"]
    assert [l.split("\t")[1] for l in (raw / "PROVENANCE.tsv").read_text().splitlines()[1:]] == ["a.txt", "b.txt"]


def test_add_source_refuses_a_refresh_or_an_unaccepted_snapshot(tmp_path):
    src, raw = _snapshot_with_one_source(tmp_path)
    with pytest.raises(ValueError, match="already has"):
        add_source(_agent("a", src / "a.txt", raw), raw)
    snap = load_snapshot(raw); snap["accepted"] = False
    (raw / "SNAPSHOT.json").write_text(json.dumps(snap))
    (src / "c.txt").write_text("c")
    with pytest.raises(ValueError, match="no accepted snapshot"):
        add_source(_agent("c", src / "c.txt", raw), raw)


def test_add_source_that_fails_changes_nothing(tmp_path):
    src, raw = _snapshot_with_one_source(tmp_path)
    before = (raw / "SNAPSHOT.json").read_text()
    (src / "d.txt").write_text("d")
    r = add_source(_agent("d", src / "d.txt", raw, ok=False), raw)
    assert not r.ok and (raw / "SNAPSHOT.json").read_text() == before and not (raw / "d.txt").exists()


def test_the_old_builder_and_its_tests_are_gone_from_the_automation():
    assert not (ROOT / "scripts" / "build_demo.sh").exists()
    assert (ROOT / "scripts" / "build_pages.sh").exists() and "civicalign.build_pages" in (ROOT / "scripts" / "build_pages.sh").read_text()
    for path in AUTOMATION:
        text = path.read_text()
        for gone in ("build_demo", "test_published_pages", "test_whitepaper", "WHITEPAPER", "mit_president"):
            assert gone not in text, (path.name, gone)
    for f in (ROOT / "src" / "civicalign").rglob("*.py"):
        assert "build_demo" not in f.read_text(), f.name


def test_the_election_results_source_is_removed():
    """Nothing in Pillar 1 or Pillars 4-6 reads presidential election results any more."""
    assert "election results" not in {a.name for a in sources.all_agents()}
    assert not hasattr(DEFAULT, "election_years")
    for f in (ROOT / "src" / "civicalign").rglob("*.py"):
        assert "mit_president" not in f.read_text(), f.name


def test_fetch_data_goes_through_the_verified_snapshot():
    text = _steps((ROOT / "scripts" / "fetch_data.sh").read_text())
    assert "-m civicalign.agents" in text and "curl" not in text


# ---- the two bill tables in the daily update ---------------------------------------------------------------

@pytest.mark.parametrize("path", [WORKFLOW, UPDATE_SH], ids=["workflow", "update.sh"])
def test_both_bill_table_refresh_steps_run_after_ingest_and_before_compute(path):
    body = _steps(path.read_text())
    ingest, anchors = body.index("civicalign.ideology.ingest"), body.index("civicalign.ideology.anchors")
    bills, outcomes = body.index("-m civicalign.ideology.bills"), body.index("-m civicalign.ideology.bill_outcomes")
    check, compute = body.index("bill_outcomes --verify"), body.index("civicalign.ideology.compute")
    build = REBUILD.search(body).start()
    assert ingest < anchors < bills < outcomes < check < compute < build, path.name
    assert body.count("-m civicalign.ideology.bills") == 1 and body.count("-m civicalign.ideology.bill_outcomes") == 2  # refresh, verify


def test_the_bill_steps_read_the_verified_snapshot_only():
    """No API call, network fetch or model in the bill steps: they are the two ideology modules
    (whose sources are checked for imports in tests/test_bills.py and test_bill_outcomes.py)."""
    import re
    for path in (WORKFLOW, UPDATE_SH):
        body = _steps(path.read_text())
        seg = body[body.index("-m civicalign.ideology.bills"):body.index("civicalign.ideology.compute")]
        assert set(re.findall(r"-m (civicalign[\w.]*)", seg)) == {"civicalign.ideology.bills", "civicalign.ideology.bill_outcomes"}
        assert not re.search(r"curl|wget|api\.|https?://|openai|anthropic|claude|gpt|llm", seg, re.I), path.name
    for f in ("bills.py", "bill_outcomes.py"):
        src = (ROOT / "src" / "civicalign" / "ideology" / f).read_text()
        assert "source_entry(cfg, snap, cfg.billflow_zip.name)" in src, "reads the archive only through the verified snapshot"
