"""The weekly update is one verified snapshot or nothing.

These tests pin the architecture: a critical source that fails to refresh leaves
every file untouched; change detection looks at content, not timestamps; the
workflow gates publication on every check; the snapshot records what a reader
needs to know about each source; and the guardrail tests stay in the weekly run.
"""
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from civicalign.agents import sources
from civicalign.agents.base import Agent, run_snapshot, zip_content_key, load_snapshot
from civicalign.agents.verify import checks as verify_checks
from civicalign.config import DEFAULT

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update.yml"


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
    for name in ("senator scores", "seated senators", "committee rosters", "state ideology",
                 "state populations", "bill flow", "bill flow (House bills)", "floor roll calls", "senator votes"):
        assert agents[name].critical, name
        assert agents[name].vintage, name
    assert "2020 wave" in agents["state ideology"].vintage
    assert agents["bill flow"].content_key is zip_content_key


def test_verify_passes_on_the_current_snapshot():
    results = verify_checks(DEFAULT)
    failed = [c.line() for c in results if not c.ok]
    assert len(results) >= 8 and not failed, "\n".join(failed)


def test_workflow_gates_publication_on_every_check():
    y = WORKFLOW.read_text()
    assert "|| echo" not in y and "FETCH_FAILED" not in y, "a fetch failure must fail the job"
    order = ["python -m civicalign.agents\n", "civicalign.agents.verify", "--ignore=tests/test_published_pages.py",
             "civicalign.build_demo", "pytest -q tests/test_published_pages.py", "civicalign.agents.supervisor",
             "git add demo/senator-check.html demo/methodology.html data/raw/PROVENANCE.tsv",
             "upload-pages-artifact"]
    pos = [y.index(s) for s in order]
    assert pos == sorted(pos), "steps must run fetch -> verify -> data tests -> rebuild -> page tests -> supervisor -> commit -> upload"
    assert "needs: update" in y and "needs.update.result == 'success'" in y
    assert 'cron: "0 11 * * 1"' in y, "the weekly schedule stays"
    assert "continue-on-error" not in y


def test_data_updated_line_distinguishes_retrieval_from_vintage():
    page = (ROOT / "demo" / "senator-check.html").read_text()
    assert "Senate data updated: '+esc(M.dataUpdated)" in page and "Voter estimate: '+M.ideologyYear+' wave" in page
    assert "the survey itself is not newer than that" in page
    assert "retrieved '+esc(t.asof)" in page and "data: '+esc(t.vintage)" in page


def test_guardrail_tests_are_permanent_and_run_every_week():
    y = WORKFLOW.read_text()
    assert "pytest -q tests/test_published_pages.py" in y
    t = (ROOT / "tests" / "test_published_pages.py").read_text()
    for name in ("test_no_user_facing_arithmetic_across_the_two_scales", "test_g1_", "test_g2_", "test_g3_",
                 "test_g4_", "test_g5_", "test_g6_", "test_2_never_calls_a_cutpoint_bill_ideology",
                 "test_5_sponsor_ideology_is_not_bill_ideology", "test_4_pending_bills_are_not_called_dead"):
        assert name in t, name


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
