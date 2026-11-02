"""Regression tests for legislative-export freshness reporting (no network)."""
import csv
import json
from datetime import date
from pathlib import Path

from scripts.check_legislative_freshness import audit


def _fixture(tmp_path: Path, *, generated: str = "2026-11-01", missing: bool = False):
    folder = tmp_path / "data" / "legislative" / "119" / generated
    folder.mkdir(parents=True)
    (folder / "MANIFEST.json").write_text("{}")
    (folder / "meta.json").write_text(json.dumps({"generated_at": generated + "T12:00:00+00:00"}))
    (folder / "votes.json").write_text(json.dumps([{"id":"119-2-1", "date":"2026-10-31"}]))
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    with (raw / "S119_rollcalls.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["congress","session","clerk_rollnumber"])
        w.writeheader()
        w.writerow({"congress":"119","session":"2","clerk_rollnumber":"1"})
        if missing:
            w.writerow({"congress":"119","session":"2","clerk_rollnumber":"2"})


def test_fresh_complete_drop(tmp_path):
    _fixture(tmp_path)
    report, attention = audit(tmp_path, date(2026, 11, 2))
    assert not attention
    assert "COVERAGE OK" in report
    assert "missing from export: 0" in report


def test_missing_rollcall_is_visible(tmp_path):
    _fixture(tmp_path, missing=True)
    report, attention = audit(tmp_path, date(2026, 11, 2))
    assert attention
    assert "119-2-2" in report
    assert "NEEDS ATTENTION" in report


def test_old_drop_is_visible(tmp_path):
    _fixture(tmp_path, generated="2026-10-01")
    report, attention = audit(tmp_path, date(2026, 11, 2))
    assert attention
    assert "32 days old" in report


def test_no_drop_is_not_silently_fresh(tmp_path):
    report, attention = audit(tmp_path, date(2026, 11, 2))
    assert attention
    assert "MISSING" in report
