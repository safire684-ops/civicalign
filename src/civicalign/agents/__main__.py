"""python -m civicalign.agents  --  refresh every source as one snapshot, or not at all."""
import sys

from ..config import DEFAULT
from .base import add_source, run_snapshot
from .sources import all_agents


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--add":
        # python -m civicalign.agents --add "<source name>": add one NEW source to
        # the accepted snapshot without refreshing the others (base.add_source)
        agent = next((a for a in all_agents() if a.name == sys.argv[2]), None)
        if agent is None:
            print(f"no source named {sys.argv[2]!r}"); return 1
        try:
            r = add_source(agent, DEFAULT.raw_dir)
        except ValueError as e:
            print(f"NOT ADDED: {e}"); return 1
        print(r.line())
        return 0 if r.ok else 1
    agents = all_agents()
    snap = run_snapshot(agents, DEFAULT.raw_dir)
    print(f"CivicAlign update run  {snap.run_utc}\n")
    for r in snap.results:
        print(r.line())
    print(f"\n  {snap.summary()}")
    if not snap.accepted:
        print("\n  The site is not rebuilt from a partial refresh. Fix the failing source")
        print("  and re-run; until then the previously verified site stays live.")
        return 1
    if snap.changed:
        print("\n  Data changed. The tests, rebuild and supervisor decide whether it publishes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
