"""Independent reference for gold deadlines: a naive day-by-day walker.

Deliberately written differently from ``pipeline/terms.py`` (which jumps over
suspension segments arithmetically): here we walk one day at a time, count
only days that are not suspended, and hard-code the holiday table and the
Easter Mondays. The test-suite checks both agree on thousands of dates.
The legal parameters (days / suspension / roll-over / 21:00 rule) are the
generator's own table, asserted equal to ``rules/terms.json`` in a test.
"""
import datetime as dt

EASTER_MONDAY = {2025: dt.date(2025, 4, 21), 2026: dt.date(2026, 4, 6), 2027: dt.date(2027, 3, 29),
                 2028: dt.date(2028, 4, 17)}
FIXED = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)]
FIXED_SINCE = {(10, 4): 2026}

# doc_type: (days, feriale_suspension, saturday_rollover, pec_after_21_rule)
GOLD_TERMS = {
    "atto_precetto": (10, False, True, True),
    "decreto_ingiuntivo": (40, True, True, True),
    "pignoramento_mobiliare": (20, False, True, True),
    "sentenza_liquidazione_giudiziale": (30, False, True, True),
    "avviso_accertamento": (60, True, True, False),
    "cartella_pagamento": (60, False, False, False),
    "intimazione_pagamento": (5, False, False, False),
    "avviso_addebito": (40, False, True, False),
    "diffida_messa_in_mora": (None, False, False, False),
    "provvedimento_rateizzazione": (None, False, False, False),
}


def is_non_working(d: dt.date) -> bool:
    if d.weekday() == 6:
        return True
    if (d.month, d.day) in FIXED:
        return True
    if (d.month, d.day) in FIXED_SINCE and d.year >= FIXED_SINCE[(d.month, d.day)]:
        return True
    return EASTER_MONDAY.get(d.year) == d


def notification_day(local_dt: dt.datetime, after_21: bool) -> dt.date:
    """local_dt is the Europe/Rome wall-clock of the PEC delivery."""
    if after_21 and local_dt.hour >= 21:
        return local_dt.date() + dt.timedelta(days=1)
    return local_dt.date()


def walk(start: dt.date, days: int, suspension: bool, saturday: bool) -> dt.date:
    d, counted = start, 0
    while counted < days:
        d += dt.timedelta(days=1)
        if suspension and d.month == 8:
            continue
        counted += 1
    while is_non_working(d) or (saturday and d.weekday() == 5):
        d += dt.timedelta(days=1)
    return d
