"""Urgency mapping (5 levels) from ``rules/urgency.json``. Pure function of facts + as_of."""
from __future__ import annotations

import datetime as _dt
from functools import lru_cache

from .lib import jsonio
from .rules_engine import RULES_DIR

RECUPERARE = "RECUPERARE"


@lru_cache(maxsize=None)
def rules() -> dict:
    return jsonio.read(RULES_DIR / "urgency.json")


def compute(doc_type: str, driving: dict | None, deadline_recuperare: bool, as_of: _dt.date) -> tuple[str, str, int | None]:
    cfg = rules()
    levels = cfg["levels"]
    days = None
    if driving:
        days = (_dt.date.fromisoformat(driving["date"]) - as_of).days
    level, rid = "INFORMATIONAL", "U-007"
    for r in cfg["rules"]:
        w = r["when"]
        if w.get("doc_type_unknown") and doc_type in (None, RECUPERARE):
            level, rid = r["then"]["urgency"], r["id"]
            break
        if w.get("deadline_recuperare") and deadline_recuperare:
            level, rid = r["then"]["urgency"], r["id"]
            break
        if driving is None:
            if not w:
                level, rid = r["then"]["urgency"], r["id"]
                break
            continue
        if w.get("status") and driving.get("status") == w["status"]:
            lim = w.get("expired_within_days")
            if lim is None or (days is not None and -days <= lim):
                level, rid = r["then"]["urgency"], r["id"]
                break
            continue
        if "max_days" in w and days is not None and 0 <= days <= w["max_days"]:
            level, rid = r["then"]["urgency"], r["id"]
            break
        if w.get("has_deadline"):
            level, rid = r["then"]["urgency"], r["id"]
            break
    for f in cfg["floors"]:
        if doc_type in f["doc_type"] and levels.index(level) > levels.index(f["min"]):
            level, rid = f["min"], f["id"]
    return level, rid, days
