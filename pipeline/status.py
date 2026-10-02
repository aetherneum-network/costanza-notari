"""L3 - remembered state is stale state.

``status()`` answers "what is pending / due" by re-reading the ledger file in
the same call and stamping the answer with ``as_of`` (from an injected clock).
There is no cache, by construction: nothing in this module keeps state.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path

from . import deadlines as dl
from .s7_ledger import Ledger, fold


def open_task(ledger: Ledger, task_id: str, *, what: str, ref: str, at: str, by: str) -> dict:
    return ledger.append({"op": "task_open", "task_id": task_id, "what": what, "ref": ref, "at": at, "by": by})


def close_task(ledger: Ledger, task_id: str, *, at: str, by: str, note: str = "") -> dict:
    return ledger.append({"op": "task_close", "task_id": task_id, "at": at, "by": by, "note": note})


def status(ledger_dir: Path, clock, *, due_within_days: int = 7) -> dict:
    as_of: _dt.datetime = clock()
    path = Path(ledger_dir) / "ledger.jsonl"
    led = Ledger(ledger_dir)  # re-read from disk, every call
    tasks = {}
    for ev in led.events:
        if ev.get("op") == "task_open":
            tasks[ev["task_id"]] = {"task_id": ev["task_id"], "what": ev["what"], "ref": ev["ref"], "opened": ev["at"],
                                    "status": "open"}
        elif ev.get("op") == "task_close" and ev["task_id"] in tasks:
            tasks[ev["task_id"]].update({"status": "closed", "closed": ev["at"], "closed_by": ev["by"]})
    due = []
    for unit in fold(led.events).values():
        f = unit["facts"]
        drv = dl.driving_deadline(f.get("deadlines") or [], as_of.date())
        if drv and drv["status"] == "open":
            days = (_dt.date.fromisoformat(drv["date"]) - as_of.date()).days
            if days <= due_within_days:
                due.append({"record": f["record_id"], "deadline": drv["date"], "days_left": days})
    pending = sorted((t for t in tasks.values() if t["status"] == "open"), key=lambda t: t["task_id"])
    return {"as_of": as_of.isoformat(), "source": "ledger.jsonl (re-read in this call)",
            "ledger_events": len(led.events),
            "ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            "pending_count": len(pending), "pending": pending,
            "due_within_days": due_within_days, "due": sorted(due, key=lambda d: (d["deadline"], d["record"])),
            "answer": f"{len(pending)} repl{'y' if len(pending) == 1 else 'ies'} pending (as of {as_of.isoformat()})"}
