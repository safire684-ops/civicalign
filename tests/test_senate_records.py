"""senate.gov refuses automated requests, so the bindings verify against stored official records.

Pins that a blocked fetch uses a stored copy's own hash, that a vote with no stored copy stays
UNAVAILABLE (never verified), and that a changed stored record is caught.
"""
import json
import urllib.error
from pathlib import Path

from civicalign.agents import supervisor as S
from civicalign.agents.base import sha256_bytes
from civicalign.config import DEFAULT
from civicalign.explain import bind as BD
from civicalign.explain.fetch import Store


def _blocked(*a, **k):
    raise urllib.error.HTTPError("https://www.senate.gov/x.xml", 403, "Forbidden", {}, None)


def test_a_blocked_fetch_uses_the_stored_copys_real_hash(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _blocked)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    store = Store(tmp_path)
    (tmp_path / "senate").mkdir()
    (tmp_path / "senate" / "v.xml").write_bytes(b"<vote/>" * 100)
    f = store.fetch("https://www.senate.gov/x.xml", "senate/v.xml")
    assert f.ok and "cached copy" in f.message and f.sha256 == sha256_bytes(b"<vote/>" * 100)
    assert store.manifest["senate/v.xml"]["sha256"] == f.sha256 and store.manifest["senate/v.xml"]["stored_copy"]


def test_a_blocked_fetch_with_no_stored_copy_is_not_verified(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _blocked)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert not Store(tmp_path).fetch("https://www.senate.gov/x.xml", "senate/v.xml").ok
    status, checks = BD.verify({}, None, None, {}, ({}, {}), False)
    assert status == "UNAVAILABLE" and checks[0]["check"] == "senate_record_exists" and not checks[0]["ok"]


def test_a_refusal_is_not_retried(tmp_path, monkeypatch):
    calls = []
    def refuse(*a, **k):
        calls.append(1)
        _blocked()
    monkeypatch.setattr("urllib.request.urlopen", refuse)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert not Store(tmp_path).fetch("https://www.senate.gov/x.xml", "senate/v.xml").ok
    assert len(calls) == 1


def test_the_run_records_that_it_used_stored_copies():
    src = (Path(BD.__file__)).read_text()
    assert '"senate_records": dict(senate_copies)' in src
    assert '"stored copy"' in src and '"retrieved" if f.message in ("changed", "unchanged")' in src


def test_stored_records_pass_the_checks():
    assert all(c.ok for c in S.senate_record_checks(DEFAULT))


def _copy(tmp_path):
    from dataclasses import replace
    raw, bindings = tmp_path / "raw", tmp_path / "bindings"
    (raw / "explanations" / "senate").mkdir(parents=True)
    bindings.mkdir()
    src = DEFAULT.explain_raw_dir / "senate"
    for f in src.iterdir():
        (raw / "explanations" / "senate" / f.name).write_bytes(f.read_bytes())
    for f in DEFAULT.bindings_dir.glob("vote_*.json"):
        (bindings / f.name).write_bytes(f.read_bytes())
    (bindings / "index.json").write_text(json.dumps({"senate_records": {"stored copy": 1}, "bound": [{"senate_record": "stored copy"}]}))
    return type("C", (), {"explain_raw_dir": raw / "explanations", "bindings_dir": bindings})()


def test_a_record_with_no_stored_or_retrieved_label_is_caught(tmp_path):
    cfg = _copy(tmp_path)
    (cfg.bindings_dir / "index.json").write_text(json.dumps({"senate_records": {"stored copy": 1}, "bound": [{}]}))
    assert any(not c.ok and "labelled stored or retrieved" in c.name for c in S.senate_record_checks(cfg))
    (cfg.bindings_dir / "index.json").write_text(json.dumps({"senate_records": {"retrieved": 1}, "bound": [{"senate_record": "stored copy"}]}))
    assert any(not c.ok and "labelled stored or retrieved" in c.name for c in S.senate_record_checks(cfg))


def test_a_changed_stored_record_is_caught(tmp_path):
    cfg = _copy(tmp_path)
    f = next((cfg.explain_raw_dir / "senate").glob("vote_*.xml"))
    f.write_bytes(f.read_bytes().replace(b"<yeas>", b"<yeas>1"))
    assert any(not c.ok and "unchanged" in c.name for c in S.senate_record_checks(cfg))


def test_a_binding_naming_another_record_is_caught(tmp_path):
    cfg = _copy(tmp_path)
    f = next(cfg.bindings_dir.glob("vote_*.json"))
    b = json.loads(f.read_text())
    b["vote"]["senate_sha256"] = "0" * 64
    f.write_text(json.dumps(b))
    assert any(not c.ok and "bindings name" in c.name for c in S.senate_record_checks(cfg))
