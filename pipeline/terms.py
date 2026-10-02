"""Italian procedural-term arithmetic. Rule implemented (see docs/TERMS.md).

All legal parameters live in ``rules/terms.json`` and ``rules/holidays.json``;
every one of them is an assumption marked ``[TO CONFIRM with counsel]``.
This module is *arithmetic only*; it is cross-checked in the test-suite
against an independent day-by-day reference in ``corpus/reference_terms.py``.

Algorithm (forward terms counted in days):

1. Start date S = the day the notification is perfected for the recipient.
   (Optional PEC 21:00 rule: delivered at/after 21:00 -> next day; before
   07:00 -> same day, both at 07:00. Applied only where the rule says so.)
2. *Dies a quo non computatur* (art. 155 c.1 c.p.c.): day 1 is S + 1.
3. If ``feriale_suspension``: days 1-31 August do not count (L. 742/1969
   art. 1 as amended by D.L. 132/2014). A term that would begin inside the
   period begins on 1 September (day 1).
4. The term expires on the day the count reaches N.
5. Roll-forward: if that day is a Sunday or a public holiday -> next day
   (art. 155 c.4 c.p.c.; art. 2963 c.c. for substantive terms); if
   ``saturday_rollover`` and it is a Saturday -> next Monday (art. 155 c.5
   c.p.c.). Repeated until a working day is reached.
"""
from __future__ import annotations

import datetime as _dt
from functools import lru_cache

from .lib import tzrome

D = _dt.date


def easter_sunday(year: int) -> D:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return D(year, month, day + 1)


@lru_cache(maxsize=None)
def _holidays(year: int, spec_key: str) -> frozenset:
    import json
    spec = json.loads(spec_key)
    out = set()
    for h in spec["fixed"]:
        since = h.get("since_year", 0)
        if year >= since:
            m, d = (int(x) for x in h["mm_dd"].split("-"))
            out.add(D(year, m, d))
    if spec.get("easter_monday", True):
        out.add(easter_sunday(year) + _dt.timedelta(days=1))
    return frozenset(out)


class Calendar:
    def __init__(self, holiday_spec: dict):
        import json
        self._key = json.dumps({"fixed": holiday_spec["fixed"],
                                "easter_monday": holiday_spec.get("easter_monday", True)}, sort_keys=True)

    def is_holiday(self, d: D) -> bool:
        return d.weekday() == 6 or d in _holidays(d.year, self._key)

    def roll_forward(self, d: D, saturday_rollover: bool) -> D:
        while self.is_holiday(d) or (saturday_rollover and d.weekday() == 5):
            d += _dt.timedelta(days=1)
        return d


def in_feriale(d: D) -> bool:
    return d.month == 8


def notification_date(pec_time: _dt.datetime, after_21_rule: bool) -> D:
    local = tzrome.to_rome(pec_time)
    if after_21_rule:
        if local.hour >= 21:
            return local.date() + _dt.timedelta(days=1)
    return local.date()


def add_days(cal: Calendar, start: D, days: int, *, feriale_suspension: bool,
             saturday_rollover: bool) -> D:
    """Arithmetic implementation (segment jumping, not a day walker)."""
    day1 = start + _dt.timedelta(days=1)
    if feriale_suspension and in_feriale(day1):
        day1 = D(day1.year, 9, 1)
    end = day1 + _dt.timedelta(days=days - 1)
    if feriale_suspension:
        # every 1-31 August crossed between day1 and end adds 31 days
        y = day1.year
        while True:
            aug1 = D(y, 8, 1)
            if aug1 > end:
                break
            if aug1 >= day1:
                end += _dt.timedelta(days=31)
            y += 1
    return cal.roll_forward(end, saturday_rollover)


def compute(cal: Calendar, term: dict, pec_time: _dt.datetime, days: int | None = None) -> dict:
    """Apply one ``rules/terms.json`` entry. Returns a deadline record."""
    n = days if days is not None else term["days"]
    start = notification_date(pec_time, term.get("pec_after_21_rule", False))
    due = add_days(cal, start, n, feriale_suspension=term.get("feriale_suspension", False),
                   saturday_rollover=term.get("saturday_rollover", False))
    return {"date": due.isoformat(), "nature": "computed", "days": n, "from": start.isoformat(),
            "rule_id": term["id"], "legal_basis": term.get("legal_basis"),
            "assumption": term.get("to_confirm", "[TO CONFIRM with counsel]")}
