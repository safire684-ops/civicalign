"""The update is one verified snapshot or nothing.

These tests pin the architecture: a critical source that fails to refresh leaves
every file untouched; change detection looks at content, not timestamps; a new
source can be added to the accepted snapshot without refreshing the others; the
workflow gates publication on every check; and the snapshot records what a
reader needs to know about each source.

Step 5B removed the old page builder (build_demo) and the old page tests; the
GitHub workflow and scripts/update.sh are updated in Step 5C. Until then they
still name removed modules, which test_every_module_the_update_runs_exists
records as an expected failure.
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
REBUILD = __import__("re").compile(r"civicalign\.build_(?:pages|demo)")    # the page rebuild step, old or new name


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


def test_workflow_gates_publication_on_every_check():
    y = WORKFLOW.read_text()
    assert "|| echo" not in y and "FETCH_FAILED" not in y, "a fetch failure must fail the job"
    order = ["python -m civicalign.agents\n", "civicalign.agents.verify", "civicalign.explain.bind", "civicalign.explain.context --check-fresh",
             REBUILD.search(y).group(0), "python -m pytest", "civicalign.agents.supervisor",
             "git add demo/senator-check.html demo/methodology.html data/raw/PROVENANCE.tsv", "upload-pages-artifact"]
    assert _order_is_kept(y, order), \
        "fetch -> verify -> bind -> Stage 2.5 check -> rebuild -> tests -> supervisor -> commit -> upload"
    assert "needs: update" in y and "needs.update.result == 'success'" in y
    assert 'cron: "0 11 * * 1"' in y, "the weekly schedule stays"
    assert "continue-on-error" not in y


@pytest.mark.parametrize("path", [WORKFLOW, ROOT / "scripts" / "update.sh"], ids=["workflow", "update.sh"])
def test_no_test_runs_before_the_pages_are_rebuilt(path):
    """The invariant behind the 24 Sept CI failure: tests compare the pages with
    the raw files, so every test and the supervisor must run after the pages
    have been rebuilt from the snapshot just fetched, and the rebuild must come
    after the bindings and the Stage 2.5 check for that snapshot."""
    text = path.read_text()
    body = text[text.index("civicalign.agents") :]            # skip the header comment
    rebuild = REBUILD.search(body).start()
    for probe in ("pytest", "civicalign.agents.supervisor"):
        first = min(i for i in (m.start() for m in __import__("re").finditer(__import__("re").escape(probe), body)))
        assert first > rebuild, f"{probe} runs before the rebuild in {path.name}"
    assert body.index("civicalign.explain.bind") < rebuild and body.index("--check-fresh") < rebuild
    if path == WORKFLOW:
        assert body.index("git commit") > body.index("civicalign.agents.supervisor"), "commit only after every gate"


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


@pytest.mark.xfail(strict=True, reason="Step 5C: the workflow and update.sh still run the removed build_demo and "
                   "tests/test_published_pages.py. Remove this marker when they are updated.")
@pytest.mark.parametrize("path", [WORKFLOW, ROOT / "scripts" / "update.sh", ROOT / "scripts" / "build_demo.sh"],
                         ids=["workflow", "update.sh", "build_demo.sh"])
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
