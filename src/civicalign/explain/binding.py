"""Deterministic classification, binding and text-version selection.

Everything here is a pure function of official records: Voteview's roll-call
row, the Senate's own vote XML, and the bill's BILLSTATUS record. There is no
model and no guess. When two sources disagree, or when more than one text
version could be the one voted on, the result says so and the vote is not
eligible for an explanation.

THE RECEIPT THIS SERVES
-----------------------
A voter-facing card must eventually answer: what was the Senate deciding, what
exact text was before it, what a Yea and a Nay would do, how this senator
voted, and where each statement can be checked. Every field produced here maps
to one of those lines; the wording that depends on the kind of vote (the
"if it succeeds / if it fails" headings and the procedural meaning of Yea and
Nay) is fixed per kind, so it can never be reversed by a summary.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..sources.billstatus import BillRecord, TextVersion
from ..sources.rollcalls import RollCall
from ..sources.senate_votes import SenateVote

# ---- vote kinds -----------------------------------------------------------------
PASSAGE = "PASSAGE"
PASSAGE_AS_AMENDED = "PASSAGE_AS_AMENDED"
JOINT_RESOLUTION_PASSAGE = "JOINT_RESOLUTION_PASSAGE"
MOTION_TO_PROCEED = "MOTION_TO_PROCEED"
CLOTURE = "CLOTURE"
AMENDMENT = "AMENDMENT"
MOTION_TO_TABLE = "MOTION_TO_TABLE"
POINT_OF_ORDER = "POINT_OF_ORDER"
CONFERENCE_REPORT = "CONFERENCE_REPORT"
VETO_OVERRIDE = "VETO_OVERRIDE"
NOMINATION = "NOMINATION"
OTHER = "OTHER"

SUPPORTED_KINDS = frozenset({PASSAGE, PASSAGE_AS_AMENDED, JOINT_RESOLUTION_PASSAGE})

# official question string -> kind. Anything not listed is OTHER.
QUESTION_KINDS = {
    "On Passage of the Bill": PASSAGE,            # refined to PASSAGE_AS_AMENDED by corroboration
    "On the Joint Resolution": JOINT_RESOLUTION_PASSAGE,
    "On the Motion to Proceed": MOTION_TO_PROCEED,
    "On the Cloture Motion": CLOTURE,
    "On Cloture on the Motion to Proceed": CLOTURE,
    "On the Amendment": AMENDMENT,
    "On the Motion to Table": MOTION_TO_TABLE,
    "On the Point of Order": POINT_OF_ORDER,
    "On the Conference Report": CONFERENCE_REPORT,
    "On Overriding the Veto": VETO_OVERRIDE,
    "On the Nomination": NOMINATION,
}

# The receipt's fixed, kind-specific wording. Never produced by a model.
HEADINGS = {
    PASSAGE: ("If the bill passes", "If the bill does not pass"),
    PASSAGE_AS_AMENDED: ("If the bill, as amended, passes", "If the bill does not pass"),
    JOINT_RESOLUTION_PASSAGE: ("If the resolution passes", "If the resolution does not pass"),
}
YEA_NAY = {
    PASSAGE: ("A Yea vote is a vote to pass the bill in the Senate.",
              "A Nay vote is a vote against passing the bill."),
    PASSAGE_AS_AMENDED: ("A Yea vote is a vote to pass the bill as the Senate amended it.",
                         "A Nay vote is a vote against passing the amended bill."),
    JOINT_RESOLUTION_PASSAGE: ("A Yea vote is a vote to pass the joint resolution in the Senate.",
                               "A Nay vote is a vote against passing the joint resolution."),
}
NEXT_STEP = {
    PASSAGE: "A bill the Senate passes goes to the House (or, if the House already passed the same text, to the President).",
    PASSAGE_AS_AMENDED: "Because the Senate changed the text, the amended bill goes back to the House, which must agree to the Senate's version before it can become law.",
    JOINT_RESOLUTION_PASSAGE: "A joint resolution has the force of a bill: after both chambers pass it, it goes to the President.",
}

MEASURE_TYPES = {"S": "bill", "HR": "bill", "SJRES": "joint_resolution", "HJRES": "joint_resolution"}

# ---- classification -------------------------------------------------------------

@dataclass(frozen=True)
class Classification:
    kind: str
    summary_eligible: bool       # kind is supported (verification/text may still withhold)
    basis: tuple[str, ...]       # which records corroborated the kind
    conflict: str = ""           # why it fell back to OTHER, if it did


def classify(rc: RollCall, senate: SenateVote | None, bill: BillRecord | None,
             passage_action_text: str = "") -> Classification:
    """Kind from the official question, refined only by corroborating fields:
    the Senate's own vote title ("…, As Amended") and the bill's action text for
    this vote ("Passed Senate with an amendment…"). Never from a bill number."""
    q = rc.question.strip()
    kind = QUESTION_KINDS.get(q, OTHER)
    basis = [f"voteview.question={q!r}"]
    if senate is not None:
        if senate.question.strip() != q:
            return Classification(OTHER, False, tuple(basis), conflict=f"senate question {senate.question!r} differs from Voteview {q!r}")
        basis.append(f"senate.question={senate.question!r}")
    if kind == PASSAGE:
        senate_amended = senate.as_amended if senate is not None else None
        action_amended = None
        if passage_action_text:
            action_amended = bool(re.search(r"\bwith (an )?amendments?\b", passage_action_text, re.I))
        if senate_amended is not None and action_amended is not None and senate_amended != action_amended:
            return Classification(OTHER, False, tuple(basis),
                                  conflict=f"senate title {senate.title!r} and bill action {passage_action_text!r} disagree on amendment")
        amended = senate_amended if senate_amended is not None else action_amended
        if amended:
            kind = PASSAGE_AS_AMENDED
            basis.append("senate.title=As Amended" if senate_amended else f"billstatus.action={passage_action_text!r}")
        elif senate is None and not passage_action_text:
            basis.append("no corroboration of amendment status available")
    return Classification(kind, kind in SUPPORTED_KINDS, tuple(basis))


# ---- CRA joint resolutions --------------------------------------------------------

# The two official title forms of a Congressional Review Act resolution:
#   "...providing for congressional disapproval under chapter 8 of title 5, United
#    States Code, of the rule submitted by the <Agency> relating to "<Rule>"."
#   "...disapproving the rule submitted by the <Agency> relating to "<Rule>"."
CRA_TITLE = re.compile(
    r"(?:congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by|"
    r"disapproving the rule submitted by) "
    r"(?:the )?(?P<agency>.+?) relating to (?:[\"\u201c](?P<rule>.+?)[\"\u201d]|(?P<rule_plain>[^\"\u201c].*?))\.?\s*$", re.I | re.S)


@dataclass(frozen=True)
class Cra:
    is_cra: bool
    agency: str | None = None
    rule_title: str | None = None
    consequence_ref: str | None = None
    title_form: str | None = None                # which official title form matched
    underlying_rule_source: str | None = None    # future: Federal Register / agency rule text
    underlying_rule_sha256: str | None = None


CRA_CONSEQUENCE = ("Congressional Review Act, 5 U.S.C. 801(b): a rule disapproved by an enacted joint "
                   "resolution shall not take effect (or shall not continue in effect) and may not be "
                   "reissued in substantially the same form without subsequent statutory authorization.")


def cra_from_title(title: str) -> Cra:
    m = CRA_TITLE.search(title or "")
    if not m:
        return Cra(False)
    form = "chapter 8 of title 5" if "chapter 8" in m.group(0).lower() else "disapproving the rule"
    rule = (m.group("rule") or m.group("rule_plain") or "").strip().rstrip(".")
    return Cra(True, agency=m.group("agency").strip().rstrip("."), rule_title=rule,
               consequence_ref=CRA_CONSEQUENCE, title_form=form)


# ---- text-version selection --------------------------------------------------------
TEXT_BOUND = "TEXT_BOUND"
TEXT_PENDING = "TEXT_PENDING"
TEXT_AMBIGUOUS = "TEXT_AMBIGUOUS"
TEXT_NOT_REQUIRED = "TEXT_NOT_REQUIRED"
TEXT_UNSUPPORTED = "UNSUPPORTED"

NEVER = {"enr", "pl", "pap", "ppl"}                       # enrolled / public law: never "as voted on"
AS_PASSED_SENATE = {"es", "cps"}                          # Senate-origin: the engrossed text as passed
SENATE_AMENDMENT = {"eas"}                                # House-origin passed with a Senate amendment
PRE_VOTE_HOUSE_ORIGIN = ["pcs", "rs", "rds", "rfs", "eh", "cph"]   # precedence: nearest the Senate floor first
PRE_VOTE_SENATE_ORIGIN = ["pcs", "rs", "is"]
PENDING_WINDOW_DAYS = 45


@dataclass(frozen=True)
class TextBinding:
    status: str
    version: TextVersion | None
    selection_reason: str
    candidates: tuple[str, ...] = ()      # "code@date" strings considered


def _d(s: str) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def floor_amendments_adopted(bill: BillRecord, vote_date: str) -> list[str]:
    """Senate floor amendments recorded as agreed to on or before the vote date.
    Their presence means the text before the Senate is the bill as amended on the
    floor, which only an engrossed version can represent."""
    vd = _d(vote_date)
    out = []
    for a in bill.actions:
        ad = _d(a.date)
        if vd and ad and ad <= vd and re.search(r"\bS\.?Amdt\.?\s*\d+|\bAmendment SA \d+", a.text) \
                and re.search(r"agreed to", a.text, re.I) and "Senate" in (a.text + a.source):
            out.append(f"{a.date}: {a.text[:80]}")
    return out


def select_text(kind: str, bill: BillRecord | None, vote_date: str, today: date | None = None) -> TextBinding:
    """The text as it stood at the vote. Fails closed on any plurality."""
    if kind not in SUPPORTED_KINDS:
        return TextBinding(TEXT_NOT_REQUIRED, None, "vote kind not supported for explanation")
    if bill is None:
        return TextBinding(TEXT_PENDING, None, "bill record not available yet")
    vd = _d(vote_date)
    if vd is None:
        return TextBinding(TEXT_AMBIGUOUS, None, "vote date unreadable")
    today = today or date.today()
    versions = [v for v in bill.text_versions if v.code and v.code not in NEVER]
    cands = tuple(f"{v.code}@{v.date or '-'}" for v in bill.text_versions)
    senate_origin = bill.origin_chamber.lower().startswith("senate") or bill.bill_type in ("S", "SJRES")
    late = vd + timedelta(days=3)

    def in_window(v: TextVersion) -> bool:
        d = _d(v.date)
        return d is not None and vd <= d <= late

    # 1. a Senate engrossment produced by this vote is the text as passed
    as_passed = [v for v in versions if v.code in (AS_PASSED_SENATE if senate_origin else SENATE_AMENDMENT) and in_window(v)]
    if len(as_passed) == 1:
        return TextBinding(TEXT_BOUND, as_passed[0], f"engrossed by the Senate on the vote date ({as_passed[0].code}): the measure as passed", cands)
    if len(as_passed) > 1:
        return TextBinding(TEXT_AMBIGUOUS, None, f"more than one Senate engrossment dated at the vote: {[v.code + '@' + v.date for v in as_passed]}", cands)

    amended = kind == PASSAGE_AS_AMENDED or floor_amendments_adopted(bill, vote_date)
    if amended:
        # the Senate changed the text and no engrossment is published (yet)
        if (today - vd).days <= PENDING_WINDOW_DAYS:
            return TextBinding(TEXT_PENDING, None, "Senate amended the measure; the engrossed text is not published yet", cands)
        return TextBinding(TEXT_AMBIGUOUS, None, "Senate amended the measure and no engrossed text exists to represent it", cands)

    # 2. otherwise the latest pre-vote version in the Senate's hands, by precedence
    order = PRE_VOTE_SENATE_ORIGIN if senate_origin else PRE_VOTE_HOUSE_ORIGIN
    pre = [v for v in versions if v.code in order and _d(v.date) is not None and _d(v.date) <= vd]
    if not pre:
        if (today - vd).days <= PENDING_WINDOW_DAYS:
            return TextBinding(TEXT_PENDING, None, "no pre-vote text version published yet", cands)
        return TextBinding(TEXT_AMBIGUOUS, None, "no pre-vote text version exists in the record", cands)
    latest = max(_d(v.date) for v in pre)
    on_latest = [v for v in pre if _d(v.date) == latest]
    on_latest.sort(key=lambda v: order.index(v.code))
    chosen = on_latest[0]
    reason = f"latest pre-vote version ({chosen.code}, {chosen.date}); no Senate amendment recorded"
    if len(on_latest) > 1:
        reason += f"; same-day versions {[v.code for v in on_latest]} resolved by precedence {order}"
    return TextBinding(TEXT_BOUND, chosen, reason, cands)


STAGE_NAMES = {"es": "Engrossed-in-Senate", "cps": "Considered-and-Passed-Senate", "eas": "Engrossed-Amendment-Senate",
               "eh": "Engrossed-in-House", "rfs": "Referred-in-Senate", "rds": "Received-in-Senate",
               "pcs": "Placed-on-Calendar-Senate", "rs": "Reported-in-Senate", "is": "Introduced-in-Senate",
               "cph": "Considered-and-Passed-House"}


def stage_matches(code: str, xml_head: bytes) -> bool | None:
    """The GovInfo bill XML root carries bill-stage="…"; it must agree with the
    selected version code. None when the attribute is absent."""
    m = re.search(rb'bill-stage="([^"]+)"', xml_head[:4000])
    if not m:
        return None
    return m.group(1).decode("ascii", "ignore").lower() == STAGE_NAMES.get(code, "").lower()
