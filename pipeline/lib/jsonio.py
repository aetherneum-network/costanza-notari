r"""JSON I/O: UTF-8 always, deterministic key order, loud repairs (L8).

A handoff that does not parse is invisible - exactly the failure L1 exists to
prevent. So ``load_lenient`` repairs single backslashes in Windows paths, and
*logs every repair* instead of silently fixing it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Consumes escapes pairwise, so an already-valid double backslash is never split.
_ESCAPE = re.compile(r'\\(u[0-9a-fA-F]{4}|["\\/bfnrt])?')


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write(path: os.PathLike | str, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps(obj))
    os.replace(tmp, p)


def read(path: os.PathLike | str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def repair_backslashes(text: str) -> tuple[str, int]:
    r"""Double every backslash that does not start a valid JSON escape.

    A path written by a careless tool as ``"C:\Users\x"`` contains ``\U``,
    which is not a JSON escape, so that backslash is doubled. Valid escapes
    (``\\``, ``\n``, ``\u00e8`` ...) are kept. Known limit: ``C:\new`` is a
    *valid* escape (newline) and cannot be told apart - hence the log.
    Returns (repaired_text, number_of_repairs).
    """
    count = 0

    def fix(m):
        nonlocal count
        if m.group(1) is not None:
            return m.group(0)
        count += 1
        return "\\\\"

    return _ESCAPE.sub(fix, text), count


def load_lenient(path: os.PathLike | str, repair_log: list | None = None):
    raw = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        fixed, n = repair_backslashes(raw)
        obj = json.loads(fixed)  # raises if still broken: loud, never swallowed
        if repair_log is not None:
            repair_log.append({"file": str(Path(path).name), "repairs": n,
                               "reason": f"invalid escape(s) repaired after: {first_err.msg}"})
        return obj


def append_jsonl(path: os.PathLike | str, obj) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: os.PathLike | str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
