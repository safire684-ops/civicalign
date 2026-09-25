"""The bridge between public-opinion estimates and the legislator scale.

Senator scores (Voteview nominate_dim1) and state public estimates (American
Ideology Project) come from different measurement systems with different
zero points and units. Nothing may place a public estimate on the senator
scale except a recorded bridge: a stated method, its parameters, the two model
versions it links, and (to be VALIDATED) its validation results.

Status
  NONE         no bridge. Every quantity that needs one is NOT_AVAILABLE.
  PROVISIONAL  a stated method with parameters, not validated. May be shown
               only labelled provisional.
  VALIDATED    method, parameters and validation results recorded.

The active bridge is chosen by config.active_bridge_version. Today it is
"none-v0" (NONE). No transformation method is implemented: METHODS is empty,
and a PROVISIONAL or VALIDATED record naming a method that is not implemented
also yields NOT_AVAILABLE, never a guess.
"""
from ..config import DEFAULT, Config
from . import records as R
from .result import not_available
from .store import Table

NONE_V0 = {
    "bridge_version": "none-v0", "status": "NONE", "public_model_version": None, "legislator_model_version": None,
    "transformation_method": None, "transformation_parameters": None, "validation_metrics": None,
    "created_at": "2026-09-25T00:00:00Z",
    "notes": ("No validated method links American Ideology Project estimates to Voteview legislator scores. "
              "Quantities that need a common scale are not computed."),
}

# method name -> function(bridge_record, public_estimate, standard_error) -> (value, standard_error)
METHODS: dict = {}


class BridgeError(ValueError):
    pass


def register_defaults(cfg: Config = DEFAULT, snapshot_run_utc: str = "bridge-registry") -> int:
    """Write the none-v0 record if the store does not have it. Returns lines written."""
    return Table(cfg.ideology_dir, "ideology_bridge").append([NONE_V0], snapshot_run_utc)


def active(cfg: Config = DEFAULT, bridges: list[dict] | None = None) -> dict:
    """The bridge record named by config.active_bridge_version."""
    rows = bridges if bridges is not None else Table(cfg.ideology_dir, "ideology_bridge").current()
    rec = next((b for b in rows if b["bridge_version"] == cfg.active_bridge_version), None)
    if rec is None:
        raise BridgeError(f"active bridge {cfg.active_bridge_version!r} is not in the bridge table")
    errs = R.validate("ideology_bridge", rec)
    if errs:
        raise BridgeError(f"active bridge {rec['bridge_version']!r} is invalid: {errs}")
    return rec


def to_common(bridge: dict, estimate: float | None, standard_error: float | None) -> dict:
    """A public estimate on the legislator scale, or NOT_AVAILABLE with the reason."""
    if estimate is None:
        return not_available("no public estimate for this geography", "legislator scale")
    if bridge["status"] == "NONE":
        return not_available(f"bridge {bridge['bridge_version']} has status NONE: no validated method places public "
                             "estimates on the legislator scale", "legislator scale")
    fn = METHODS.get(bridge["transformation_method"])
    if fn is None:
        return not_available(f"bridge {bridge['bridge_version']} names method {bridge['transformation_method']!r}, "
                             "which is not implemented", "legislator scale")
    value, se = fn(bridge, estimate, standard_error)   # pragma: no cover - no method exists yet
    return {"value": value, "status": "AVAILABLE" if bridge["status"] == "VALIDATED" else "PROVISIONAL",
            "units": "legislator scale", "standard_error": se, "reason": None}


def main() -> int:
    """python -m civicalign.ideology.bridge: record the default bridges (none-v0)."""
    n = register_defaults(DEFAULT)
    print(f"bridge table: {n} new record(s); active bridge {active(DEFAULT)['bridge_version']} ({active(DEFAULT)['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
