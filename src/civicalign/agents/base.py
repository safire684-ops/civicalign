"""The contract every update agent follows, and the all-or-nothing snapshot.

THE RULE
--------
The public site must always come from ONE internally consistent, verified set of
source files. So a weekly run never replaces files one at a time. Every source is
downloaded and validated into a staging folder first; only when every critical
source has succeeded is the whole set moved into place, together. If any
critical source fails, nothing is replaced and the run fails: the previously
verified snapshot stays exactly as it was, and nothing new is published.

CHANGE DETECTION
----------------
A download counts as changed only when its CONTENT changed, not its timestamp.
For zip archives (GovInfo republishes them daily with fresh timestamps even when
the bills inside are identical) the content key hashes the members, not the
archive bytes.
"""
import hashlib
import json
import shutil
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_content_key(path: Path) -> str:
    """Hash of a zip's members (name + bytes), ignoring archive timestamps."""
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            h.update(name.encode())
            h.update(hashlib.sha256(z.read(name)).digest())
    return h.hexdigest()


@dataclass
class Result:
    name: str
    ok: bool
    message: str
    changed: bool = False
    bytes_fetched: int = 0
    sha256: str = ""
    seconds: float = 0.0
    critical: bool = True

    def line(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        state = "updated" if self.changed else ("unchanged" if self.ok else "kept previous")
        crit = "" if self.critical else "  (non-critical)"
        return f"  {mark}  {self.name:22s} {state:14s} {self.message}{crit}"


@dataclass
class Fetched:
    """One source, downloaded and validated into staging. Nothing installed yet."""
    name: str
    ok: bool
    message: str
    staged: Path | None = None
    bytes: int = 0
    sha256: str = ""
    content_key: str = ""
    seconds: float = 0.0


@dataclass
class Agent:
    """One source, one file, one validation rule.

    `validate` receives the freshly downloaded path and must raise or return a
    reason string if the data is not usable. `content_key` turns a file into a
    string that changes only when the substantive content changes.
    """
    name: str
    url: str
    target: Path
    validate: callable
    min_bytes: int = 1024
    timeout: int = 180
    headers: dict = field(default_factory=lambda: {"User-Agent": "CivicAlign/0.1"})
    critical: bool = True
    vintage: str = ""          # what the data itself represents, e.g. "2020 wave"
    content_key: callable = sha256_file

    def fetch(self, staging: Path) -> Fetched:
        started = time.time()
        staging.mkdir(parents=True, exist_ok=True)
        tmp = staging / self.target.name
        try:
            req = urllib.request.Request(self.url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as r, tmp.open("wb") as out:
                shutil.copyfileobj(r, out)
        except Exception as exc:
            return Fetched(self.name, False, f"fetch failed: {exc}", seconds=time.time() - started)

        size = tmp.stat().st_size
        if size < self.min_bytes:
            return Fetched(self.name, False, f"suspiciously small ({size} bytes)", seconds=time.time() - started)
        try:
            problem = self.validate(tmp)
        except Exception as exc:
            problem = f"{type(exc).__name__}: {exc}"
        if problem:
            return Fetched(self.name, False, f"rejected: {problem}", bytes=size, seconds=time.time() - started)
        try:
            key = self.content_key(tmp)
        except Exception as exc:
            return Fetched(self.name, False, f"content key failed: {exc}", bytes=size, seconds=time.time() - started)
        return Fetched(self.name, True, f"{size:,} bytes", staged=tmp, bytes=size,
                       sha256=sha256_file(tmp), content_key=key, seconds=time.time() - started)

    def run(self) -> Result:
        """Fetch and install this one source on its own. Kept for ad-hoc use;
        the weekly job uses run_snapshot so sources move together."""
        import tempfile
        f = self.fetch(Path(tempfile.mkdtemp()))
        if not f.ok:
            return Result(self.name, False, f.message, seconds=f.seconds, critical=self.critical)
        changed = not self.target.exists() or self.content_key(self.target) != f.content_key
        if changed:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f.staged), str(self.target))
        return Result(self.name, True, f.message, changed=changed, bytes_fetched=f.bytes,
                      sha256=f.sha256, seconds=f.seconds, critical=self.critical)


@dataclass
class Snapshot:
    accepted: bool
    run_utc: str
    results: list[Result]
    failed_critical: list[str]
    changed: list[str]

    def summary(self) -> str:
        if not self.accepted:
            return ("REJECTED: critical source(s) failed: " + ", ".join(self.failed_critical)
                    + ". No file was replaced; the previous verified snapshot is intact.")
        n = len(self.changed)
        return f"accepted: {n} source(s) changed" + (f" ({', '.join(self.changed)})" if n else "") + \
               f", {len(self.results) - n} unchanged"


SNAPSHOT_FILE = "SNAPSHOT.json"
PROVENANCE_FILE = "PROVENANCE.tsv"


def load_snapshot(raw_dir: Path) -> dict:
    p = raw_dir / SNAPSHOT_FILE
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def _last_provenance_stamp(raw_dir: Path, filename: str) -> str:
    prov = raw_dir / PROVENANCE_FILE
    stamp = ""
    if prov.exists():
        for line in prov.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == filename:
                stamp = parts[0]
    return stamp


def run_snapshot(agents: list[Agent], raw_dir: Path, now: datetime | None = None) -> Snapshot:
    """Fetch every source into staging; install all of them together, or none."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    staging = raw_dir / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    fetched = [(a, a.fetch(staging)) for a in agents]

    failed_critical = [a.name for a, f in fetched if not f.ok and a.critical]
    if failed_critical:
        shutil.rmtree(staging, ignore_errors=True)
        results = [Result(a.name, f.ok, f.message, seconds=f.seconds, critical=a.critical) for a, f in fetched]
        return Snapshot(False, stamp, results, failed_critical, [])

    previous = {s["name"]: s for s in load_snapshot(raw_dir).get("sources", [])}
    records, results, changed_names = [], [], []
    for a, f in fetched:
        prev = previous.get(a.name, {})
        if not f.ok:  # non-critical: keep the previous file, say so
            results.append(Result(a.name, False, f.message, seconds=f.seconds, critical=False))
            if prev:
                records.append({**prev, "checked_utc": stamp, "note": f"refresh failed this run: {f.message}"})
            continue
        # Compare with the last ACCEPTED snapshot's content key, which is committed
        # to the repo. On a fresh checkout the raw files are absent, and without
        # this a re-download of identical content would look like a change.
        old_key = prev.get("content_key", "")
        prev_bytes = int(prev.get("bytes") or 0)
        if not old_key and a.target.exists():
            try:
                old_key = a.content_key(a.target)
            except Exception:
                old_key = ""
            prev_bytes = a.target.stat().st_size
        changed = f.content_key != old_key
        a.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f.staged), str(a.target))   # install; every critical source reached this point
        content_changed = stamp if changed else (prev.get("content_changed_utc")
                                                 or _last_provenance_stamp(raw_dir, a.target.name) or stamp)
        records.append({
            "name": a.name, "url": a.url, "file": a.target.name, "critical": a.critical,
            "vintage": a.vintage, "bytes": f.bytes, "previous_bytes": prev_bytes,
            "sha256": f.sha256, "content_key": f.content_key, "changed": changed,
            "content_changed_utc": content_changed, "checked_utc": stamp,
        })
        results.append(Result(a.name, True, f.message, changed=changed, bytes_fetched=f.bytes,
                              sha256=f.sha256, seconds=f.seconds, critical=a.critical))
        if changed:
            changed_names.append(a.name)
    shutil.rmtree(staging, ignore_errors=True)

    (raw_dir / SNAPSHOT_FILE).write_text(json.dumps(
        {"run_utc": stamp, "accepted": True, "sources": records}, indent=1) + "\n")
    prov = raw_dir / PROVENANCE_FILE
    if not prov.exists():
        prov.write_text("fetched_utc\tfile\tsha256\turl\n")
    with prov.open("a") as fh:
        for rec in records:
            if rec.get("changed"):
                fh.write(f"{stamp}\t{rec['file']}\t{rec['sha256']}\t{rec['url']}\n")
    return Snapshot(True, stamp, results, [], changed_names)


def run_all(agents: list[Agent]) -> list[Result]:
    """Run every agent independently (legacy). Prefer run_snapshot."""
    return [a.run() for a in agents]
