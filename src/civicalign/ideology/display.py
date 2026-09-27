"""Presentation rules for the Pillars 4-6 page: the display position and the plain-language wording.

Nothing here is a calculation input. Every Pillars 4-6 number is calculated and
stored on Voteview's own scale (nominate_dim1, -1 to +1); this module only turns
a stored value into what the page shows, by fixed arithmetic:

display_position_v1
    display position = (nominate_dim1 + 1) x 50, so -1 -> 0, 0 -> 50, +1 -> 100.
    Shown as a whole number on a marker, or with one decimal in details, rounded
    half-up from the exact decimal value. It is a POSITION on a line, never a
    score, grade, rating, rank or alignment; higher is not better; it is never
    shown as "/100"; and survey estimates of the public are never translated
    onto it. 50 is Voteview's zero point, nothing more.

side_label_v1
    from the SIGN of the raw value: below zero "Liberal side of the voting
    scale", above zero "Conservative side of the voting scale", exactly zero
    "At Voteview's zero point". The same sign rule as the bill sponsor groups.

senate_position_wording_v1
    from the plain Senate mean: within 2 display points of 50 (|mean| x 50 < 2)
    "The Senate sits close to Voteview's zero point."; otherwise "The Senate sits
    on the <side> side of the voting scale."

population_shift_wording_v1
    shift = |plain mean - population-weighted mean| x 50 display points; the side
    is liberal when plain - weighted > 0 and conservative when < 0. Exactly 0:
    "Weighting senators by state population does not move it."; under 5 points:
    "... moves it slightly toward the <side> side."; 5 points or more: "... moves
    it toward the <side> side."

committee_comparison_wording_v1
    from |committee median - Senate median| x 50 display points: under 2 points
    "close to the Senate midpoint"; otherwise the side of the Senate midpoint the
    committee median falls on.

Every threshold is compared on the exact decimal of the raw value (never on a
rounded display number), so the words cannot disagree with the stored numbers.
"""
from decimal import ROUND_HALF_UP, Decimal

POSITION_RULE = "display_position_v1"
SIDE_RULE = "side_label_v1"
SENATE_RULE = "senate_position_wording_v1"
SHIFT_RULE = "population_shift_wording_v1"
COMMITTEE_RULE = "committee_comparison_wording_v1"
CLOSE_POINTS = Decimal(2)        # senate_position_wording_v1, committee_comparison_wording_v1
SLIGHT_POINTS = Decimal(5)       # population_shift_wording_v1

RULES = (
    (POSITION_RULE, "Display position",
     "display position = (nominate_dim1 + 1) × 50, so −1 is 0, 0 is 50 and +1 is 100. Shown as a whole number on a marker "
     "and with one decimal in details, rounded half-up. Presentation only: every calculation uses nominate_dim1 itself.",
     ("A position on a line, not a score, grade, rating, rank or alignment. Higher is not better.",
      "50 on the line is Voteview’s zero point, nothing more.",
      "Survey estimates of the public are never shown on this line.")),
    (SIDE_RULE, "Side label",
     "From the sign of the raw nominate_dim1: below 0 “Liberal side of the voting scale”; above 0 “Conservative side of the "
     "voting scale”; exactly 0 “At Voteview’s zero point”.",
     ("The same sign rule as the bill sponsor groups (sponsor_nominate_dim1_sign_v1).",)),
    (SENATE_RULE, "Where the Senate sits (wording)",
     "From the plain Senate mean: if |mean| × 50 is under 2 display points, “The Senate sits close to Voteview’s zero "
     "point.”; otherwise “The Senate sits on the liberal (or conservative) side of the voting scale.”",
     ("Compared on the exact raw value, not the rounded display number.",)),
    (SHIFT_RULE, "What changes with population (wording)",
     "shift = |plain mean − population-weighted mean| × 50 display points, toward the liberal side when plain − weighted is "
     "positive and the conservative side when negative. Exactly 0: “Weighting senators by state population does not move "
     "it.”; under 5 points: “… moves it slightly toward the <side> side.”; 5 points or more: “… moves it toward the <side> side.”",
     ("Compared on the exact raw values, not the rounded display numbers.",)),
    (COMMITTEE_RULE, "Committee compared with the Senate (wording)",
     "From |committee median − Senate median| × 50 display points: under 2 points, “This committee sits close to the Senate "
     "midpoint.”; otherwise “This committee sits to the liberal (or conservative) side of the Senate midpoint.”",
     ("Descriptive only: it says nothing about what the committee did or why.",
      "Compared on the exact raw values, not the rounded display numbers.")),
)


def _dec(v) -> Decimal:
    return Decimal(repr(v)) if isinstance(v, float) else Decimal(v)


def position(v) -> Decimal:
    """The exact display position of a raw nominate_dim1 value."""
    return (_dec(v) + 1) * 50


def position_text(v, decimals: int = 0) -> str:
    """The display position rounded half-up to 0 or 1 decimals (never a minus sign: the line runs 0 to 100)."""
    return f"{position(v).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP):.{decimals}f}"


def points_text(diff) -> str:
    """A raw difference as display points, one decimal, no sign (the words carry the direction)."""
    return f"{(abs(_dec(diff)) * 50).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.1f}"


def side(v) -> str | None:
    if v is None:
        return None
    d = _dec(v)
    return "liberal" if d < 0 else "conservative" if d > 0 else "zero"


def side_label(v) -> str | None:
    s = side(v)
    return None if s is None else "At Voteview’s zero point" if s == "zero" else f"{s.capitalize()} side of the voting scale"


def senate_position_sentence(plain_mean) -> str:
    if abs(_dec(plain_mean)) * 50 < CLOSE_POINTS:
        return "The Senate sits close to Voteview’s zero point."
    return f"The Senate sits on the {side(plain_mean)} side of the voting scale."


def shift_words(difference) -> str | None:
    """The population_shift_wording_v1 phrase: "slightly toward the liberal side", "toward the conservative side",
    or None when weighting does not move the Senate at all. difference = plain mean - population-weighted mean."""
    d = _dec(difference)
    if d == 0:
        return None
    where = "liberal" if d > 0 else "conservative"
    return ("slightly toward the " if abs(d) * 50 < SLIGHT_POINTS else "toward the ") + f"{where} side"


def population_shift_sentence(difference) -> str:
    """The default sentence: "Weighting senators by state population moves it slightly toward the liberal side." """
    w = shift_words(difference)
    return "Weighting senators by state population does not move it." if w is None else \
        f"Weighting senators by state population moves it {w}."


def shift_detail_sentence(difference) -> str:
    """The same rule, in details: "In plain terms, population weighting moves the Senate average ... of the voting scale." """
    w = shift_words(difference)
    return "In plain terms, population weighting does not move the Senate average." if w is None else \
        f"In plain terms, population weighting moves the Senate average {w} of the voting scale."


def committee_sentence(drift) -> str | None:
    """drift = committee median - Senate median; None when the committee has no median."""
    if drift is None:
        return None
    d = _dec(drift)
    if abs(d) * 50 < CLOSE_POINTS:
        return "This committee sits close to the Senate midpoint."
    return f"This committee sits to the {'liberal' if d < 0 else 'conservative'} side of the Senate midpoint."


PARTY_ABBREVIATIONS = {"Republican": "R", "Democrat": "D", "Independent": "I"}


def party_abbreviation(party: str | None) -> str | None:
    """The roster's current-term party, as the page shows it (R, D, I); anything else is shown in full."""
    if not party:
        return None
    return PARTY_ABBREVIATIONS.get(party, party)
