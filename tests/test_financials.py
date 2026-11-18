"""Financial disclosures: source parsing, integrity, and fail-closed refresh tests."""
from datetime import datetime, timedelta, timezone
import json

from civicalign import financials as F

NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def index_page(count=80):
    rows = "".join(
        f'<tr><td><a href="/senator/A{i:06d}">Senator {i}</a> D</td>'
        '<td>2025</td><td>$1.5M – $3M</td><td>$10K – $20K</td>'
        '<td>$1.4M – $2.9M</td><td>3</td><td></td></tr>'
        for i in range(count)
    )
    return ('<table><thead><tr><th>Senator</th><th>Year</th><th>Assets</th>'
            '<th>Debts</th><th>Net worth</th><th>Lines</th><th>Paper years</th>'
            '</tr></thead><tbody>' + rows + '</tbody></table>')


def profile_page(stocks=True):
    rows = (
        '<tr><td>BLIND TRUST</td><td>Trust</td><td>Self</td><td>$1M – $5M</td><td></td></tr>'
        '<tr><td>Vanguard Retirement ETF</td><td>Mutual Funds</td><td>Spouse</td><td>$50K – $100K</td><td></td></tr>'
    )
    if stocks:
        rows += '<tr><td>Example, Inc. Common Stock</td><td>Stocks</td><td>Joint</td><td>$15K – $50K</td><td></td></tr>'
    return (
        '<table><tr><th>Asset</th><th>Kind</th><th>Owner</th><th>Value</th><th>Income</th></tr>'
        + rows + '</table><table><tr><th>Filed</th><th>Report</th><th>Entries</th></tr>'
        '<tr><td>Aug 13, 2026</td><td>Annual Report for Calendar 2025</td><td>3</td></tr></table>'
    )


def test_index_matches_by_bioguide_and_preserves_value_ranges():
    rows = F.parse_index(index_page())
    assert len(rows) == 80
    assert rows["A000000"]["year"] == 2025
    assert rows["A000001"]["net_worth"] == "$1.4M – $2.9M"
    assert rows["A000001"]["profile_url"] == F.BASE + "/senator/A000001"


def test_no_synthetic_zeros_if_stock_holdings_are_not_shown():
    result = F.parse_profile(profile_page(stocks=False), 2025)
    assert result["details_checked"] is True
    assert result["stocks"] == []
    assert result["other_holdings"][0]["kind"] == "Trust"
    assert result["holdings_source"] == "largest holdings shown"


def test_direct_stocks_are_distinguished_from_funds_and_blind_trusts():
    result = F.parse_profile(profile_page(), 2025)
    assert result["stocks"][0]["name"].startswith("Example")
    assert result["stocks"][0]["owner"] == "Joint"
    assert result["stock_rows_in_summary"] == 1
    assert result["filed"] == "Aug 13, 2026"
    assert all("Trust" not in x["kind"] for x in result["stocks"])


def test_malformed_or_low_coverage_source_cannot_overwrite_prior(tmp_path):
    target = tmp_path / "senate.json"
    old = {"schema": "civicalign.senate_financials/1", "entries": {"O000174": {"year": 2025}}}
    target.write_text(json.dumps(old))
    unchanged = target.read_bytes()
    assert F.refresh(target, fetch=lambda _: index_page(2), now=NOW, delay=0) == "source_unreachable"
    assert target.read_bytes() == unchanged
    assert F.refresh(target, fetch=lambda _: "<html>down</html>", now=NOW, delay=0) == "source_unreachable"
    assert target.read_bytes() == unchanged


def test_weekly_refresh_replaces_only_complete_source_checked_dataset(tmp_path):
    target = tmp_path / "senate.json"
    def fetch(url):
        return index_page() if url.endswith("/holdings") else profile_page(stocks=True)
    result = F.refresh(target, fetch=fetch, now=NOW, delay=0)
    assert result.startswith("updated 80")
    saved = json.loads(target.read_text())
    assert saved["entries"]["A000008"]["stocks"][0]["kind"] == "Stocks"
    assert saved["source"] == F.BASE
    assert saved["checked_utc"] == "2026-11-18T00:00:00Z"
    def forbidden(_):
        raise AssertionError("not due yet")
    assert F.refresh(target, fetch=forbidden, now=NOW + timedelta(days=1), delay=0) == "current"


def test_partial_profile_failure_preserves_previous_complete_snapshot(tmp_path):
    target = tmp_path / "senate.json"
    target.write_text(json.dumps({"schema": "civicalign.senate_financials/1",
                                  "entries": {"A000001": {"year": 2025}}}))
    before = target.read_bytes()
    def fetch(url):
        if url.endswith("/holdings"):
            return index_page()
        if url.endswith("/A000001"):
            return profile_page()
        raise TimeoutError("down")
    assert F.refresh(target, fetch=fetch, now=NOW, delay=0) == "low_coverage"
    assert target.read_bytes() == before


def test_schema_changes_are_rejected():
    try:
        F.parse_profile("<table><tr><th>Trades</th></tr></table>", 2025)
    except ValueError:
        pass
    else:
        assert False, "a missing holdings table must fail closed"


def test_no_private_account_or_paid_model_needed():
    code = __import__("inspect").getsource(F)
    assert "openai" not in code.lower()
    assert "anthropic" not in code.lower()
    assert "os.environ" not in code.lower()
    assert "api_key" not in code.lower()
