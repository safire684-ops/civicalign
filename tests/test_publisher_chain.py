"""The whole receiving chain over a real HTTP connection, with the real October 29 export.

prepare_50degrees_publish.py packages a fresh copy -> a local web server publishes it the way GitHub Pages
would -> legislative_sync checks it (--check), imports it, sees it as current, and keeps it when a broken
newer drop arrives. Only the generator itself (the partner's `civicalign export 119`) is simulated, by
re-dating the committed export. No network beyond 127.0.0.1, no credentials, no AI.
"""
import hashlib
import importlib.util
import json
import shutil
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from civicalign import legislative as L
from civicalign import legislative_sync as S
from civicalign.config import DEFAULT

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("prepare_publish", ROOT / "scripts" / "prepare_50degrees_publish.py")
PREP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PREP)
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def fresh_export(dest: Path, made: datetime, drop_bill: bool = False) -> Path:
    """The committed export, re-dated as if the generator had just run (counts kept consistent)."""
    shutil.copytree(L.latest_dir(DEFAULT), dest, ignore=shutil.ignore_patterns("MANIFEST.json"))
    meta = json.loads((dest / "meta.json").read_text())
    meta["generated_at"] = made.isoformat(timespec="seconds")
    if drop_bill:                                   # a broken generator run: one bill missing
        bills = json.loads((dest / "bills.json").read_text())
        gone = bills.pop()
        votes = json.loads((dest / "votes.json").read_text())
        for v in votes:
            if v["bill"] == gone["id"]:
                v["bill"] = None
        (dest / "bills.json").write_text(json.dumps(bills))
        (dest / "votes.json").write_text(json.dumps(votes))
        meta["counts"]["bills"] = len(bills)
    (dest / "meta.json").write_text(json.dumps(meta, indent=1))
    return dest


@pytest.fixture
def publisher(tmp_path):
    """A local static web server, like GitHub Pages. Records each request's Authorization header."""
    site = tmp_path / "site"
    site.mkdir()
    seen = []

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(site), **k)

        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization")))
            super().do_GET()

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield site, f"http://127.0.0.1:{server.server_address[1]}/drops/119/", seen
    server.shutdown()


@pytest.fixture
def cfg(tmp_path):
    c = replace(DEFAULT, ideology_dir=tmp_path / "data" / "ideology", raw_dir=tmp_path / "data" / "raw")
    seed = tmp_path / "seed"
    shutil.copytree(L.latest_dir(DEFAULT), seed, ignore=shutil.ignore_patterns("MANIFEST.json"))
    L.import_drop(seed, c)                          # the drop CivicAlign has today
    return c


def publish(site: Path, prepared: Path):
    """What the partner's workflow does: replace drops/119/ in one deploy."""
    target = site / "drops" / "119"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(prepared, target)


def ids(cfg):
    return {s["id"] for s in L.load(cfg)["senators"]}


def test_a_fresh_export_travels_the_whole_chain(cfg, publisher, tmp_path):
    site, url, seen = publisher
    before = L.load(cfg)["manifest"]["generated_at"]
    made = NOW - timedelta(hours=2)
    manifest = PREP.prepare(fresh_export(tmp_path / "export", made), tmp_path / "prepared", now=NOW)
    publish(site, tmp_path / "prepared")

    checked = S.sync(cfg, url=url, token="example-token", engine_ids=ids(cfg), dry_run=True)
    assert checked["state"] == "would_import", checked
    assert L.load(cfg)["manifest"]["generated_at"] == before, "a check never imports"

    done = S.sync(cfg, url=url, token="example-token", engine_ids=ids(cfg))
    assert done["state"] == "imported", done
    now_have = L.load(cfg)
    assert now_have["manifest"]["generated_at"] == manifest["generated_at"] != before
    assert all(L.sha_file(L.latest_dir(cfg) / n) == h for n, h in manifest["files"].items())
    assert {p for p, _ in seen} >= {"/drops/119/manifest.json", "/drops/119/votes.json"}
    assert all(auth == "Bearer example-token" for _, auth in seen), "the token goes only in the header, to the publisher"

    assert S.sync(cfg, url=url, engine_ids=ids(cfg))["state"] == "current"


def test_a_broken_newer_drop_leaves_the_last_good_one(cfg, publisher, tmp_path):
    site, url, _ = publisher
    before = L.load(cfg)["manifest"]["generated_at"]
    broken = fresh_export(tmp_path / "export", NOW - timedelta(hours=1), drop_bill=True)
    PREP.prepare(broken, tmp_path / "prepared", now=NOW)                # internally consistent, so it packages
    publish(site, tmp_path / "prepared")
    r = S.sync(cfg, url=url, engine_ids=ids(cfg))
    assert r["state"] == "rejected" and "bills in the last drop are missing" in r["detail"], r
    assert L.load(cfg)["manifest"]["generated_at"] == before


def test_a_file_changed_after_the_manifest_is_rejected(cfg, publisher, tmp_path):
    site, url, _ = publisher
    PREP.prepare(fresh_export(tmp_path / "export", NOW - timedelta(hours=1)), tmp_path / "prepared", now=NOW)
    publish(site, tmp_path / "prepared")
    (site / "drops" / "119" / "bills.json").write_text("[]")           # a half-finished or tampered upload
    r = S.sync(cfg, url=url, engine_ids=ids(cfg), dry_run=True)
    assert r["state"] == "rejected" and "bills.json does not match" in r["detail"]


def test_an_address_with_nothing_published_is_unreachable(cfg, publisher):
    _, url, _ = publisher
    r = S.sync(cfg, url=url, engine_ids=ids(cfg), dry_run=True)
    assert r["state"] == "unreachable"


def test_the_october_export_is_too_old_to_package():
    """Why a fresh generator run is needed: the preparer refuses anything over 14 days old."""
    with pytest.raises(ValueError, match="stale"):
        PREP.verify_source(L.latest_dir(DEFAULT), 119, now=NOW)


def test_the_check_command_reports_and_never_imports(cfg, publisher, tmp_path, monkeypatch, capsys):
    site, url, _ = publisher
    PREP.prepare(fresh_export(tmp_path / "export", NOW - timedelta(hours=1)), tmp_path / "prepared", now=NOW)
    publish(site, tmp_path / "prepared")
    before = L.load(cfg)["manifest"]["generated_at"]
    monkeypatch.setattr(S, "DEFAULT", cfg)
    monkeypatch.setattr(S.BL, "current_sponsor_scores", lambda c: {i: None for i in ids(cfg)})
    monkeypatch.setattr("sys.argv", ["legislative_sync", "--check", url])
    assert S.main() == 0
    out = capsys.readouterr().out
    assert "publisher check: would_import" in out and "votes: " in out
    assert L.load(cfg)["manifest"]["generated_at"] == before
    assert not S.status_path(cfg).exists(), "a check writes no sync status"


def test_the_partner_workflow_template_reuses_the_existing_tools():
    t = (ROOT / "docs" / "partner" / "publish-50degrees.yml").read_text()
    assert "civicalign export 119" in t, "it runs the partner's existing generator, not a new one"
    assert "scripts/prepare_50degrees_publish.py" in t and "safire684-ops/civicalign" in t
    assert "schedule:" in t and "cron:" in t and "workflow_dispatch:" in t
    live = "\n".join(l for l in t.splitlines() if not l.strip().startswith("#"))
    assert "secrets." not in live, "no credentials are used; a partner's own AI key is only a commented example"
    assert "anthropic" not in t.lower() and "openai" not in t.lower()
