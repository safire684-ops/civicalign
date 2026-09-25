"""An append-only, hash-chained store for the versioned tables.

One JSON Lines file per table. Each line is

    {"record_id", "prev_record_id", "content_sha256", "snapshot_run_utc", "content": {...}}

- content is one validated record (records.validate).
- content_sha256 is the SHA-256 of the content's canonical JSON.
- prev_record_id is the record_id of the previous version with the same key
  (None for a key's first version); record_id = SHA-256 of
  "<prev_record_id or empty>|<content_sha256>". Each key's versions form a
  chain, so an edited, deleted or reordered line is detectable (verify()).
- snapshot_run_utc names the source snapshot the ingest ran against.

A new version is appended only when its content differs from the key's
current version; an unchanged ingest writes nothing. Existing lines are never
rewritten: the file is opened for appending only.
"""
import hashlib
import json
from pathlib import Path

from . import records as R


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


class StoreError(ValueError):
    pass


class Table:
    def __init__(self, directory: Path, table: str):
        if table not in R.TABLES:
            raise StoreError(f"unknown table {table!r}")
        self.table = table
        self.path = Path(directory) / f"{table}.jsonl"

    # ---- reading ---------------------------------------------------------------
    def lines(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def latest(self) -> dict[tuple, dict]:
        """Current version of every key: {key: line}."""
        out: dict[tuple, dict] = {}
        for line in self.lines():
            out[R.key_of(self.table, line["content"])] = line
        return out

    def current(self) -> list[dict]:
        """Current content of every key, in first-appearance order."""
        return [line["content"] for line in self.latest().values()]

    def history(self, key: tuple) -> list[dict]:
        return [l for l in self.lines() if R.key_of(self.table, l["content"]) == key]

    # ---- writing ---------------------------------------------------------------
    def plan(self, contents: list[dict]) -> list[dict]:
        """The lines an append would write, without writing them. Validates every
        record; raises on any invalid record or a key given twice."""
        seen, out = set(), []
        latest = self.latest()
        heads = {k: l["record_id"] for k, l in latest.items()}
        for c in contents:
            errs = R.validate(self.table, c)
            if errs:
                raise StoreError(f"{self.table}: invalid record: {errs}")
            k = R.key_of(self.table, c)
            if k in seen:
                raise StoreError(f"{self.table}: key {k} supplied twice in one ingest")
            seen.add(k)
            csha = sha(canonical(c))
            if k in latest and latest[k]["content_sha256"] == csha:
                continue
            prev = heads.get(k)
            rid = sha(f"{prev or ''}|{csha}")
            out.append({"record_id": rid, "prev_record_id": prev, "content_sha256": csha, "content": c})
            heads[k] = rid
        return out

    def append(self, contents: list[dict], snapshot_run_utc: str) -> int:
        """Append the versions that differ from each key's current version.
        Returns how many lines were written."""
        new = self.plan(contents)
        if not new:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            for line in new:
                fh.write(canonical({**line, "snapshot_run_utc": snapshot_run_utc}) + "\n")
        return len(new)

    # ---- checking --------------------------------------------------------------
    def verify(self) -> list[str]:
        """Every line re-hashed, every chain re-walked, every record re-validated."""
        problems, heads = [], {}
        for i, line in enumerate(self.lines(), 1):
            c = line.get("content", {})
            errs = R.validate(self.table, c)
            if errs:
                problems.append(f"line {i}: invalid record {errs}")
                continue
            if sha(canonical(c)) != line["content_sha256"]:
                problems.append(f"line {i}: content does not match its content_sha256")
            k = R.key_of(self.table, c)
            if line["prev_record_id"] != heads.get(k):
                problems.append(f"line {i}: chain broken for {k}")
            if sha(f"{line['prev_record_id'] or ''}|{line['content_sha256']}") != line["record_id"]:
                problems.append(f"line {i}: record_id does not match")
            heads[k] = line["record_id"]
        return problems
