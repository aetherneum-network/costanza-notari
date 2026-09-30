"""Publishing with optimistic concurrency (L4) and supersession instead of deletion (L10).

    store/
      version.json          {"version": n, "as_of": ..., "files": {name: sha256}}
      current/              exactly one current version
      _SUPERSEDED/v000n/    every previous version, moved - never deleted

``publish(..., if_version=v)`` refuses to write unless the store is still at
``v`` (read at the start of the run). A rejected write raises
``PublishConflict``: the run is FAILED, the red banner is written, no "OK".
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from .lib import jsonio


class PublishConflict(RuntimeError):
    pass


def reader_view(store: Path, now, max_age_hours: int | None = None) -> dict:
    """What a reader of the shared store sees, with staleness made explicit (L4)."""
    import datetime as _dt
    if max_age_hours is None:
        max_age_hours = jsonio.read(Path(__file__).resolve().parent.parent / "rules" / "misc.json")["staleness"]["max_age_hours"]
    p = Path(store) / "version.json"
    if not p.exists():
        return {"version": 0, "as_of": None, "stale": True, "banner": "NO DATA PUBLISHED"}
    v = jsonio.read(p)
    try:
        age_h = (now - _dt.datetime.fromisoformat(v["as_of"])).total_seconds() / 3600
    except (TypeError, ValueError):
        age_h = None
    stale = age_h is None or age_h > max_age_hours
    return {"version": v["version"], "as_of": v["as_of"], "age_hours": None if age_h is None else round(age_h, 1),
            "stale": stale, "banner": f"STALE DATA - as of {v['as_of']}" if stale else f"Data as of {v['as_of']}"}


def read_version(store: Path) -> int:
    p = Path(store) / "version.json"
    return jsonio.read(p)["version"] if p.exists() else 0


def publish(store: Path, files: dict[str, Path], *, if_version: int, as_of: str, run_id: str) -> dict:
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    current_v = read_version(store)
    if current_v != if_version:
        raise PublishConflict(f"version conflict: run read v{if_version}, store is at v{current_v}")
    cur = store / "current"
    if cur.exists() and any(cur.iterdir()):
        dest = store / "_SUPERSEDED" / f"v{current_v:04d}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(cur, dest)  # moved, not deleted
    cur.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, src in sorted(files.items()):
        shutil.copyfile(src, cur / name)
        manifest[name] = hashlib.sha256((cur / name).read_bytes()).hexdigest()
    new_v = current_v + 1
    jsonio.write(store / "version.json", {"version": new_v, "as_of": as_of, "run_id": run_id, "files": manifest})
    return {"version": new_v, "previous": current_v, "files": manifest}
