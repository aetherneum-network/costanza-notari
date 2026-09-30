"""L9 - heartbeats: order, time zone, two kinds of run, catch-up.

* Order: dependent steps are chained in ONE script (``pipeline.run``), never
  in two scheduled jobs that can run in the wrong order.
* UTC anchoring: two local triggers (02:05 and 03:05 Europe/Rome); only the
  one that falls in the target UTC hour (01:xx) does the work - 03:05 in
  summer (CEST), 02:05 in winter (CET). On the night summer time ends
  (2026-10-25) neither trigger falls in 01:xx UTC when the scheduler fires
  the first occurrence of the repeated hour; the next run catches up.
* Full run (nightly) writes data AND the judgement for its window.
  Light run (daytime) refreshes data only and can never write a judgement.
* Catch-up: the first run after downtime recovers every missed window and says so.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .lib import jsonio, tzrome

TARGET_UTC_HOUR = 1
LOCAL_TRIGGERS = ("02:05", "03:05")


class JudgementOverwriteError(RuntimeError):
    pass


def trigger_utc(day: _dt.date, hhmm: str) -> _dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return tzrome.rome_local_to_utc(_dt.datetime(day.year, day.month, day.day, h, m))


def should_run(day: _dt.date, hhmm: str, target_utc_hour: int = TARGET_UTC_HOUR) -> bool:
    return trigger_utc(day, hhmm).hour == target_utc_hour


def expected_window(now_utc: _dt.datetime) -> _dt.date:
    """The nightly run at date D (UTC) processes window D-1 once 01:00 UTC has passed."""
    d = now_utc.astimezone(tzrome.UTC)
    return d.date() - _dt.timedelta(days=1 if d.hour >= TARGET_UTC_HOUR else 2)


class Heartbeat:
    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir)
        self.path = self.dir / "heartbeat.json"
        self.state = jsonio.read(self.path) if self.path.exists() else {"last_full_window": None, "runs": []}

    def missed_windows(self, now_utc: _dt.datetime) -> list[_dt.date]:
        target = expected_window(now_utc)
        last = self.state.get("last_full_window")
        if last is None:
            return [target]
        d, out = _dt.date.fromisoformat(last) + _dt.timedelta(days=1), []
        while d <= target:
            out.append(d)
            d += _dt.timedelta(days=1)
        return out

    def write_judgement(self, window: _dt.date, lines: list[str], *, mode: str, catch_up: bool, as_of: str) -> Path:
        if mode != "full":
            raise JudgementOverwriteError("a light run must never write (or overwrite) the judgement")
        p = self.dir / "judgement" / f"{window.isoformat()}.json"
        jsonio.write(p, {"window": window.isoformat(), "written_by": "full run", "catch_up": catch_up,
                         "as_of": as_of, "judgement": lines})
        return p

    def run(self, now_utc: _dt.datetime, *, mode: str, do_window, do_refresh) -> dict:
        """do_window(window) -> judgement lines (full work for one window);
        do_refresh() -> data summary (light work)."""
        missed = self.missed_windows(now_utc)
        normal = [expected_window(now_utc)] if mode == "full" else []
        catch_up = [w for w in missed if w not in normal]
        report = {"mode": mode, "now_utc": now_utc.isoformat(), "windows": [], "catch_up": bool(catch_up),
                  "message": None}
        for w in missed:
            lines = do_window(w)
            is_cu = w in catch_up
            self.write_judgement(w, lines, mode="full", catch_up=is_cu, as_of=now_utc.isoformat())
            report["windows"].append({"window": w.isoformat(), "catch_up": is_cu})
            self.state["last_full_window"] = w.isoformat()
        if mode == "light":
            report["data"] = do_refresh()
        if catch_up:
            report["message"] = (f"CATCH-UP: host was off; recovered {len(catch_up)} missed window(s): "
                                 + ", ".join(w.isoformat() for w in catch_up))
        self.state.setdefault("runs", []).append({"now_utc": now_utc.isoformat(), "mode": mode,
                                                  "windows": [x["window"] for x in report["windows"]],
                                                  "catch_up": bool(catch_up)})
        jsonio.write(self.path, self.state)
        return report
