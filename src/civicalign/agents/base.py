"""The contract every update agent follows."""
import hashlib
import shutil
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Result:
    name: str
    ok: bool
    message: str
    changed: bool = False
    bytes_fetched: int = 0
    sha256: str = ""
    seconds: float = 0.0

    def line(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        state = "updated" if self.changed else ("unchanged" if self.ok else "kept previous")
        return f"  {mark}  {self.name:22s} {state:14s} {self.message}"


@dataclass
class Agent:
    """One source, one file, one validation rule.

    `validate` receives the freshly downloaded path and must raise or return a
    reason string if the data is not usable. Only a clean result replaces the
    live file.
    """
    name: str
    url: str
    target: Path
    validate: callable
    min_bytes: int = 1024
    timeout: int = 180
    headers: dict = field(default_factory=lambda: {"User-Agent": "CivicAlign/0.1"})

    def run(self) -> Result:
        started = time.time()
        tmp = Path(tempfile.mkdtemp()) / self.target.name
        try:
            req = urllib.request.Request(self.url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as r, tmp.open("wb") as out:
                shutil.copyfileobj(r, out)
        except Exception as exc:
            return Result(self.name, False, f"fetch failed: {exc}",
                          seconds=time.time() - started)

        size = tmp.stat().st_size
        if size < self.min_bytes:
            return Result(self.name, False,
                          f"suspiciously small ({size} bytes); previous file kept",
                          seconds=time.time() - started)

        try:
            problem = self.validate(tmp)
        except Exception as exc:
            problem = f"{type(exc).__name__}: {exc}"
        if problem:
            return Result(self.name, False, f"rejected: {problem}",
                          bytes_fetched=size, seconds=time.time() - started)

        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        changed = True
        if self.target.exists():
            changed = hashlib.sha256(self.target.read_bytes()).hexdigest() != digest

        if changed:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp), str(self.target))

        return Result(self.name, True, f"{size:,} bytes", changed=changed,
                      bytes_fetched=size, sha256=digest,
                      seconds=time.time() - started)


def run_all(agents: list[Agent]) -> list[Result]:
    """Run every agent. One failure never stops the others."""
    return [a.run() for a in agents]
