"""python -m civicalign.agents  --  run every update agent."""
import sys
from datetime import datetime, timezone

from ..config import DEFAULT
from .base import run_all
from .sources import all_agents


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"CivicAlign update run  {stamp}\n")

    results = run_all(all_agents())
    for r in results:
        print(r.line())

    prov = DEFAULT.raw_dir / "PROVENANCE.tsv"
    if not prov.exists():
        prov.write_text("fetched_utc\tfile\tsha256\turl\n")
    with prov.open("a") as fh:
        for r, a in zip(results, all_agents()):
            if r.ok and r.changed:
                fh.write(f"{stamp}\t{a.target.name}\t{r.sha256}\t{a.url}\n")

    failed = [r for r in results if not r.ok]
    changed = [r for r in results if r.changed]
    print(f"\n  {len(changed)} updated, {len(failed)} failed, "
          f"{len(results) - len(changed) - len(failed)} already current")

    if failed:
        print("\n  Failures kept the previous good data in place. The site is still")
        print("  serving correct figures; it is just not serving the newest ones.")
        return 1
    if changed:
        print("\n  Data changed. Re-run the tests before publishing:")
        print("    python3 -m pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
