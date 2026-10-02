"""Europe/Rome offsets without a tz database (Windows Python has no tzdata).

EU rule (Directive 2000/84/EC): summer time from the last Sunday of March at
01:00 UTC to the last Sunday of October at 01:00 UTC. CET = UTC+1, CEST = UTC+2.
"""
from __future__ import annotations

import datetime as _dt

UTC = _dt.timezone.utc
CET = _dt.timezone(_dt.timedelta(hours=1), "CET")
CEST = _dt.timezone(_dt.timedelta(hours=2), "CEST")


def _last_sunday(year: int, month: int) -> _dt.date:
    d = _dt.date(year, month + 1, 1) - _dt.timedelta(days=1) if month < 12 else _dt.date(year, 12, 31)
    return d - _dt.timedelta(days=(d.weekday() - 6) % 7)


def dst_bounds_utc(year: int) -> tuple[_dt.datetime, _dt.datetime]:
    start = _dt.datetime.combine(_last_sunday(year, 3), _dt.time(1, 0), UTC)
    end = _dt.datetime.combine(_last_sunday(year, 10), _dt.time(1, 0), UTC)
    return start, end


def offset_at_utc(t: _dt.datetime) -> _dt.timezone:
    t = t.astimezone(UTC)
    start, end = dst_bounds_utc(t.year)
    return CEST if start <= t < end else CET


def to_rome(t: _dt.datetime) -> _dt.datetime:
    if t.tzinfo is None:
        raise ValueError("naive datetime: refuse to guess its zone")
    return t.astimezone(offset_at_utc(t))


def rome_local_to_utc(local: _dt.datetime) -> _dt.datetime:
    """Interpret a naive wall-clock time in Rome. Ambiguous times (the repeated
    hour in October) resolve to the first occurrence (CEST); non-existent times
    (the skipped hour in March) raise."""
    if local.tzinfo is not None:
        raise ValueError("expected naive local time")
    for tz in (CEST, CET):
        cand = local.replace(tzinfo=tz)
        if offset_at_utc(cand) is tz:
            return cand.astimezone(UTC)
    raise ValueError(f"{local} does not exist in Europe/Rome (DST gap)")


def parse_iso(s: str) -> _dt.datetime:
    t = _dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise ValueError(f"timestamp without offset: {s!r}")
    return t
