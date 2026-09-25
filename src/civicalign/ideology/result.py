"""The shape of every Pillars 4-6 quantity.

    {"value": number or None, "status": AVAILABLE | PROVISIONAL | NOT_AVAILABLE,
     "units": what the number is measured in, "reason": why it is missing (or None), ...}

A quantity is never a bare number: its units travel with it, so a senator score
and a public estimate cannot be mistaken for the same scale, and a missing value
always says why.
"""
STATUSES = ("AVAILABLE", "PROVISIONAL", "NOT_AVAILABLE")


def available(value, units: str, **extra) -> dict:
    return {"value": value, "status": "AVAILABLE", "units": units, "reason": None, **extra}


def not_available(reason: str, units: str, **extra) -> dict:
    return {"value": None, "status": "NOT_AVAILABLE", "units": units, "reason": reason, **extra}
