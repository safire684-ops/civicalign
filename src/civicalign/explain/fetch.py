"""Fetching first-party artefacts for the binding layer, with provenance.

Every fetched file lands under data/raw/explanations/ (ignored by git, like the
other raw sources) and is recorded in MANIFEST.json there with its URL, bytes,
SHA-256, first-retrieved and last-changed stamps. A re-fetch that yields the
same bytes changes nothing; different bytes are recorded as a content change.
Tracked bindings carry the hashes, so a source change is visible in the diff.
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..agents.base import sha256_bytes

UA = "CivicAlign/1.0 (+https://github.com/safire684-ops/civicalign; first-party legislative sources only)"


@dataclass(frozen=True)
class Fetched:
    ok: bool
    path: Path | None
    sha256: str
    size: int
    message: str
    changed: bool


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = root / "MANIFEST.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {}

    def fetch(self, url: str, rel: str, timeout: int = 60, min_bytes: int = 200, offline: bool = False) -> Fetched:
        path = self.root / rel
        rec = self.manifest.get(rel, {})
        if offline:
            if path.exists():
                return Fetched(True, path, rec.get("sha256", sha256_bytes(path.read_bytes())), path.stat().st_size, "cached", False)
            return Fetched(False, None, "", 0, "offline and not cached", False)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml,*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if path.exists():
                return Fetched(True, path, rec.get("sha256", sha256_bytes(path.read_bytes())), path.stat().st_size,
                               f"fetch failed ({e}); using cached copy", False)
            return Fetched(False, None, "", 0, f"fetch failed: {e}", False)
        if len(data) < min_bytes or b"<html" in data[:300].lower():
            if path.exists():
                return Fetched(True, path, rec.get("sha256", ""), path.stat().st_size, "unexpected response; using cached copy", False)
            return Fetched(False, None, "", len(data), "unexpected response (too small or HTML)", False)
        digest = sha256_bytes(data)
        changed = rec.get("sha256") != digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if changed or not path.exists():
            path.write_bytes(data)
        stamp = _now()
        self.manifest[rel] = {"url": url, "bytes": len(data), "sha256": digest,
                              "first_retrieved_utc": rec.get("first_retrieved_utc", stamp),
                              "content_changed_utc": stamp if changed else rec.get("content_changed_utc", stamp),
                              "checked_utc": stamp}
        return Fetched(True, path, digest, len(data), "changed" if changed else "unchanged", changed)

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")
