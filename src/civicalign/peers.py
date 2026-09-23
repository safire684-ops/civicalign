"""Pillar 4 as published: a senator against senators in the same caucus group
from other states with a similar recent presidential vote.

WHY THIS, AND NOT THE REGRESSION
--------------------------------
An audit of the regression of senator position on state presidential vote
(representation.py, still used for diagnostics) found that its fitted line
mostly reflects the party split: within party the state's vote explains little
(Republicans: none), and in competitive states the line sits in a gap where no
senator of either party sits, so "outside the typical range" was the ordinary
condition there. The peer comparison replaces it on the page. It stays on the
Voteview scale throughout, needs no fitted line, and its reference group is
something a reader can see and check.

THE RULE, FIXED
---------------
Peers of a senator are senators who
  1. belong to the same caucus group (the Republican caucus; or the Democratic
     caucus, meaning Democrats plus the Independents whose roster entry records
     that they caucus with the Democrats), and
  2. represent a DIFFERENT state whose average two-party presidential vote over
     the configured elections is within WINDOW of the senator's state.
The senator's own state is excluded entirely, so the two senators from one
state never serve as each other's peers. A comparison is published only with at
least MIN_PEERS peers, and only if the conclusion (within the observed peer
range, or outside it on one side) is the same at every window in WINDOWS that
also meets the minimum. Otherwise the tool says so. Nothing widens the window
to find peers, and nothing here ranks anyone.

The window and minimum were chosen from a sensitivity run over ±2, ±3, ±4 and
±5 points and minimums of 5, 6 and 8 (see demo/methodology.html): ±4 is the
narrowest window at which almost every senator has six same-caucus peers from
other states, while peer states still span only about five points of vote
share; the cross-window check stops the choice of window from manufacturing a
result.
"""
import statistics as st
from dataclasses import dataclass

from .sources.elections import ElectionLean
from .sources.rosters import Senator

WINDOW = 0.04              # ± this share of the two-party vote
MIN_PEERS = 6
WINDOWS = (0.02, 0.03, 0.04, 0.05)   # the conclusion must agree across these

UNSUPPORTED = "unsupported"   # no verified caucus group: no comparison, and never a peer
WITHIN = "within"
OUTSIDE_LIBERAL = "outside_liberal"
OUTSIDE_CONSERVATIVE = "outside_conservative"
UNSTABLE = "unstable"
INSUFFICIENT = "insufficient"


# party -> caucus group, and the roster's caucus field -> caucus group for an
# Independent. Anything not listed here has NO group: such a senator gets the
# "unsupported" status and is never anyone's peer. Nothing is inferred.
PARTY_CAUCUS = {"Republican": "Republican", "Democrat": "Democratic"}
INDEPENDENT_CAUCUS = {"Democrat": "Democratic", "Republican": "Republican"}


def caucus_group(sen: Senator) -> str | None:
    """"Republican" / "Democratic" / None. An Independent is placed only by the
    caucus the current roster records for them (congress-legislators
    `terms[-1].caucus`); an unrecognised party or a missing caucus yields None."""
    if sen.party in PARTY_CAUCUS:
        return PARTY_CAUCUS[sen.party]
    if sen.party == "Independent":
        return INDEPENDENT_CAUCUS.get(sen.caucus or "")
    return None


@dataclass(frozen=True)
class Peer:
    bioguide: str
    name: str
    state: str
    score: float


@dataclass(frozen=True)
class PeerComparison:
    bioguide: str
    name: str
    state: str
    party: str
    group: str | None                # caucus group; None -> status "unsupported"
    score: float
    state_lean: float
    window: float
    min_peers: int
    peers: tuple[Peer, ...]          # at `window`, ordered by state then name: never by score
    sensitivity: dict[float, str]    # window -> raw conclusion at that window
    status: str                      # the one published classification

    @property
    def n(self) -> int:
        return len(self.peers)

    @property
    def peer_states(self) -> list[str]:
        return sorted({p.state for p in self.peers})

    @property
    def low(self) -> float | None:
        return min(p.score for p in self.peers) if self.peers else None

    @property
    def high(self) -> float | None:
        return max(p.score for p in self.peers) if self.peers else None

    @property
    def median(self) -> float | None:
        return st.median(p.score for p in self.peers) if self.peers else None


def conclusion(score: float, peer_scores: list[float], min_peers: int) -> str:
    if len(peer_scores) < min_peers:
        return INSUFFICIENT
    if score < min(peer_scores):
        return OUTSIDE_LIBERAL
    if score > max(peer_scores):
        return OUTSIDE_CONSERVATIVE
    return WITHIN


def status_from(sensitivity: dict[float, str], window: float) -> str:
    """Insufficient at the fixed window -> insufficient. Otherwise the conclusion
    at the fixed window, unless any other window with enough peers disagrees."""
    if sensitivity[window] == INSUFFICIENT:
        return INSUFFICIENT
    seen = {v for v in sensitivity.values() if v != INSUFFICIENT}
    return UNSTABLE if len(seen) > 1 else sensitivity[window]


def peer_comparisons(scores: dict[str, float], roster: dict[str, Senator],
                     lean: ElectionLean, window: float = WINDOW,
                     min_peers: int = MIN_PEERS, windows: tuple[float, ...] = WINDOWS,
                     ) -> list[PeerComparison]:
    people = [(b, roster[b], v, lean.lean(roster[b].state)) for b, v in scores.items()]
    people = [p for p in people if p[3] is not None]
    out = []
    for b, sen, score, x in people:
        g = caucus_group(sen)
        if g is None:
            out.append(PeerComparison(
                bioguide=b, name=sen.name, state=sen.state, party=sen.party, group=None,
                score=score, state_lean=x, window=window, min_peers=min_peers,
                peers=(), sensitivity={w: UNSUPPORTED for w in windows}, status=UNSUPPORTED))
            continue

        def peers_at(w):
            ps = [Peer(pb, ps_.name, ps_.state, pv) for pb, ps_, pv, px in people
                  if ps_.state != sen.state and caucus_group(ps_) == g and abs(px - x) <= w + 1e-12]
            return sorted(ps, key=lambda p: (p.state, p.name))

        sens = {w: conclusion(score, [p.score for p in peers_at(w)], min_peers) for w in windows}
        out.append(PeerComparison(
            bioguide=b, name=sen.name, state=sen.state, party=sen.party, group=g,
            score=score, state_lean=x, window=window, min_peers=min_peers,
            peers=tuple(peers_at(window)), sensitivity=sens,
            status=status_from(sens, window),
        ))
    out.sort(key=lambda c: (c.state, c.name))
    return out
