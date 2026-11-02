"""The health report, the live-site check and the alert issue. No network."""
import importlib.util
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from civicalign import health as H
from civicalign import legislative as L
from civicalign import record_votes as RV
from civicalign.config import DEFAULT
from civicalign.ideology import ingest as I

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("data_alert", ROOT / "scripts" / "data_alert.py")
ALERT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ALERT)
TODAY = date(2026, 11, 2)


@pytest.fixture
def world(tmp_path, monkeypatch):
    cfg = replace(DEFAULT, ideology_dir=tmp_path / "data" / "ideology", raw_dir=tmp_path / "data" / "raw")
    cfg.raw_dir.mkdir(parents=True)
    (cfg.explain_raw_dir / "senate").mkdir(parents=True)
    (cfg.explain_raw_dir / "senate" / "PROVENANCE.json").write_text(json.dumps({"records": {"a": {"checked_utc": "2026-10-09T00:00:00Z"}}}))
    state = {"snapshot": {"run_utc": "2026-11-02T00:00:00Z", "sources": [{"name": "x", "checked_utc": "2026-11-02T00:00:00Z"}]},
             "compare": {"votes": {"119-2-1": {"status": "verified"}}, "counts": {"verified": 1, "conflict": 0, "pending": 0}, "unread_changes": []}}
    monkeypatch.setattr(I, "snapshot", lambda c=DEFAULT: state["snapshot"])
    monkeypatch.setattr(RV, "compare", lambda c=DEFAULT: state["compare"])
    rolls(cfg, ["1"])
    return cfg, state


def rolls(cfg, numbers):
    cfg.rollcalls_csv.parent.mkdir(parents=True, exist_ok=True)
    cfg.rollcalls_csv.write_text("congress,session,clerk_rollnumber\n" + "".join(f"119,2,{n}\n" for n in numbers))


def drop(cfg, tmp, made="2026-11-01"):
    folder = tmp / "d"
    folder.mkdir(exist_ok=True)
    meta = {"congress": 119, "generated_at": made + "T12:00:00+00:00"}
    for n in L.FILES:
        (folder / n).write_text("[]" if n.endswith(".json") else "x")
    (folder / "meta.json").write_text(json.dumps(meta))
    (folder / "votes.json").write_text(json.dumps([{"id": "119-2-1", "date": "2026-10-31"}]))
    return L.import_drop(folder, cfg)


def item(result, code):
    return next(i for i in result["items"] if i["code"] == code)


def test_a_fresh_complete_drop_is_ok(world, tmp_path):
    cfg, _ = world
    drop(cfg, tmp_path)
    r = H.report(cfg, TODAY)
    assert item(r, "drop_age")["level"] == "ok" and item(r, "drop_coverage")["level"] == "ok"


def test_a_missing_roll_call_is_visible(world, tmp_path):
    cfg, _ = world
    drop(cfg, tmp_path)
    rolls(cfg, ["1", "2"])
    r = H.report(cfg, TODAY)
    assert item(r, "drop_coverage")["level"] == "warn" and "1 roll calls" in item(r, "drop_coverage")["text"]


def test_an_old_drop_is_visible(world, tmp_path):
    cfg, _ = world
    drop(cfg, tmp_path, made="2026-10-01")
    t = item(H.report(cfg, TODAY), "drop_age")
    assert t["level"] == "warn" and "32 days" in t["text"]


def test_no_drop_is_an_error_not_silently_fresh(world):
    cfg, _ = world
    r = H.report(cfg, TODAY)
    assert r["level"] == "error" and item(r, "drop_missing")


def test_a_conflict_with_the_record_is_an_error(world, tmp_path):
    cfg, state = world
    drop(cfg, tmp_path)
    state["compare"] = {"votes": {"119-2-1": {"status": "conflict"}}, "counts": {"verified": 0, "conflict": 1, "pending": 0}, "unread_changes": []}
    r = H.report(cfg, TODAY)
    assert r["level"] == "error" and "119-2-1" in item(r, "record_conflicts")["text"]


def test_a_vote_not_yet_in_the_record_is_a_warning(world, tmp_path):
    cfg, state = world
    drop(cfg, tmp_path)
    state["compare"] = {"votes": {"119-2-1": {"status": "pending"}}, "counts": {"verified": 0, "conflict": 0, "pending": 1}, "unread_changes": []}
    assert item(H.report(cfg, TODAY), "record_pending")["level"] == "warn"


def test_an_unread_change_of_vote_notice_is_an_error(world, tmp_path):
    cfg, state = world
    drop(cfg, tmp_path)
    state["compare"]["unread_changes"] = ["https://example/notice"]
    assert item(H.report(cfg, TODAY), "record_notices_unread")["level"] == "error"


@pytest.mark.parametrize("state_name,level", [("not_configured", "warn"), ("current", "ok"), ("imported", "ok"), ("rejected", "error"), ("unreachable", "error")])
def test_each_import_outcome_has_a_level(world, tmp_path, state_name, level):
    cfg, _ = world
    drop(cfg, tmp_path)
    path = H.SYNC.status_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"state": state_name, "detail": "d"}))
    assert item(H.report(cfg, TODAY), f"drop_sync_{state_name}")["level"] == level


def test_a_source_not_refreshed_is_named(world, tmp_path):
    cfg, state = world
    drop(cfg, tmp_path)
    state["snapshot"]["sources"].append({"name": "bill flow", "checked_utc": "2026-10-20T00:00:00Z"})
    assert "bill flow" in item(H.report(cfg, TODAY), "sources_older")["text"]


def test_the_blocked_senate_site_stays_visible(world, tmp_path):
    cfg, _ = world
    drop(cfg, tmp_path)
    t = item(H.report(cfg, TODAY), "senate_blocked")
    assert t["level"] == "warn" and "stored copies from 2026-10-09" in t["text"]


def test_the_summary_lists_every_check(world, tmp_path):
    cfg, _ = world
    drop(cfg, tmp_path)
    r = H.report(cfg, TODAY)
    text = H.summary(r)
    assert "Data health" in text and all(i["text"] in text for i in r["items"])


GOOD = {"": "url=civicalign.html", "senator-check.html": "civicalign.html", "senator-check-original.html": "Where do your senators stand",
        "civicalign.html": 'id="data" {"dates":{"snapshot":"2026-11-02"}}'}


def fake(pages=GOOD, codes=None):
    return lambda url: ((codes or {}).get(url.removeprefix(H.LIVE_SITE), 200), pages.get(url.removeprefix(H.LIVE_SITE), ""))


def test_a_healthy_live_site_has_no_problems():
    assert H.watch(today=TODAY, get=fake()) == []


def test_a_down_page_is_a_problem():
    assert "/civicalign.html returned 500." in H.watch(today=TODAY, get=fake(codes={"civicalign.html": 500}))


def test_a_stale_live_site_is_a_problem():
    assert any("more than 3 days" in p for p in H.watch(today=date(2026, 11, 9), get=fake()))


def test_a_lost_redirect_is_a_problem():
    assert H.watch(today=TODAY, get=fake({**GOOD, "senator-check.html": "old page"}))


def test_a_lost_rollback_page_is_a_problem():
    assert H.watch(today=TODAY, get=fake(codes={"senator-check-original.html": 404}))


def calls_with(existing):
    log = []
    def call(path, method="GET", payload=None):
        log.append((path, method, payload))
        return existing if method == "GET" else {}
    return log, call


def test_a_problem_opens_one_alert():
    log, call = calls_with([])
    assert ALERT.apply(["bad"], "run", call) == "opened"
    assert log[-1][1] == "POST" and log[-1][2]["title"] == ALERT.TITLE and "bad" in log[-1][2]["body"] and "run" in log[-1][2]["body"]


def test_a_second_problem_updates_the_same_alert():
    log, call = calls_with([{"number": 7, "title": ALERT.TITLE}])
    assert ALERT.apply(["bad"], "", call) == "updated"
    assert log[-1][0] == "issues/7" and log[-1][1] == "PATCH"


def test_a_clean_run_closes_the_alert():
    log, call = calls_with([{"number": 7, "title": ALERT.TITLE}])
    assert ALERT.apply([], "", call) == "closed" and log[-1][2] == {"state": "closed"}


def test_other_issues_are_left_alone():
    log, call = calls_with([{"number": 5, "title": "Roadmap"}, {"number": 6, "title": ALERT.TITLE, "pull_request": {}}])
    assert ALERT.apply([], "", call) == "nothing" and len(log) == 1


def test_a_failed_job_and_health_errors_are_both_problems():
    found = ALERT.problems("failure", {"items": [{"level": "error", "text": "conflict"}, {"level": "warn", "text": "gap"}]})
    assert len(found) == 2 and "conflict" in found[1] and not any("gap" in f for f in found)
    assert ALERT.problems("success", {"items": [{"level": "warn", "text": "gap"}]}) == []


def test_the_alert_step_runs_even_after_a_failure_but_only_on_main():
    y = (ROOT / ".github" / "workflows" / "update.yml").read_text()
    step = y[y.index("Open, update or close the data alert"):y.index("Arrange the publish folder")]
    assert "always() && github.ref == 'refs/heads/main'" in step and "issues: write" in y


def test_the_live_check_runs_on_its_own_schedule_and_publishes_nothing():
    y = (ROOT / ".github" / "workflows" / "monitor.yml").read_text()
    assert "cron:" in y and "civicalign.health --watch" in y and "pages: write" not in y and "contents: write" not in y and "deploy-pages" not in y
