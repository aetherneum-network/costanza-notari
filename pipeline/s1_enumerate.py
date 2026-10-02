"""Stage 1 - corpus enumeration, long-path-safe, with count reconciliation (L8).

On Windows, enumerators that do not use the extended-length prefix silently
skip paths longer than 260 characters (``os.walk`` swallows the error by
default). We enumerate through ``\\\\?\\`` and reconcile three counts before
anything is classified:

* ``long_path_safe``  - this enumerator (authoritative);
* ``naive_os_walk``   - what a standard ``os.walk`` returns (reported, never used);
* ``manifest``        - what the producer says it sent (``manifest.json``), if present;
* ``robocopy``        - optional independent count (``robocopy /L`` with a Unicode log).

A mismatch with the manifest is a FAILED stage: nothing downstream runs.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import unicodedata
from pathlib import Path

from .lib import jsonio

ENVELOPE_EXT = ".eml"


def extended(path: Path | str) -> str:
    """Absolute path with the Windows extended-length prefix (no-op elsewhere)."""
    p = os.path.abspath(str(path))
    if os.name != "nt" or p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def safe_walk(root: Path | str) -> list[str]:
    """Relative POSIX paths of every file under root, long paths included."""
    base = extended(root)
    out: list[str] = []
    stack = [base]
    while stack:
        cur = stack.pop()
        with os.scandir(cur) as it:  # errors propagate: a failed listing is loud
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    rel = os.path.relpath(e.path, base).replace("\\", "/")
                    out.append(rel)
    return sorted(out)


def naive_walk(root: Path | str) -> list[str]:
    """The failure mode, kept for comparison: plain os.walk, errors swallowed."""
    out = []
    for dirpath, _dirs, files in os.walk(str(root)):
        for f in files:
            full = os.path.join(dirpath, f)
            try:
                os.stat(full)
            except OSError:
                continue
            out.append(os.path.relpath(full, str(root)).replace("\\", "/"))
    return sorted(out)


def robocopy_count(root: Path | str, log_path: Path) -> int | None:
    """Independent count via ``robocopy /L`` (list only: copies nothing, creates nothing). Windows only.

    The destination is a path that does not exist and is never created (/L). /R:0 /W:0 matter:
    robocopy's defaults retry a failing item a million times, 30 s apart.
    """
    if os.name != "nt":
        return None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    target = log_path.parent / "_robocopy_list_only_target_never_created"
    cmd = ["robocopy", str(root), str(target), "/L", "/S", "/NJH", "/NJS", "/NDL", "/NC", "/NS", "/NP", "/FP",
           "/R:0", "/W:0", f"/UNILOG:{log_path}"]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        text = log_path.read_bytes().decode("utf-16", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return sum(1 for line in text.splitlines() if line.strip())


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(extended(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(input_root: Path, out_path: Path, *, manifest: Path | None = None, robocopy_log: Path | None = None) -> dict:
    files = safe_walk(input_root)
    envelopes = [f for f in files if f.lower().endswith(ENVELOPE_EXT)]
    naive = [f for f in naive_walk(input_root) if f.lower().endswith(ENVELOPE_EXT)]
    rec = {"long_path_safe": len(envelopes), "naive_os_walk": len(naive),
           "naive_missed": sorted(set(envelopes) - set(naive))[:50]}
    status, problems = "OK", []
    if manifest and Path(manifest).exists():
        m = jsonio.read(manifest)
        expected = sorted(x["path"] for x in m["files"] if x["path"].lower().endswith(ENVELOPE_EXT))
        rec["manifest"] = m.get("expected_envelopes", len(expected))
        exp_set = {unicodedata.normalize("NFC", p) for p in expected}
        got_set = {unicodedata.normalize("NFC", p) for p in envelopes}
        missing, extra = sorted(exp_set - got_set), sorted(got_set - exp_set)
        rec["missing_vs_manifest"], rec["unexpected_vs_manifest"] = missing[:50], extra[:50]
        if missing or extra or rec["manifest"] != len(envelopes):
            status = "FAILED"
            problems.append(f"count reconciliation failed: manifest {rec['manifest']}, found {len(envelopes)} "
                            f"({len(missing)} missing, {len(extra)} unexpected)")
    if robocopy_log is not None:
        rc = robocopy_count(input_root, robocopy_log)
        rec["robocopy_all_files"] = rc
    if rec["naive_os_walk"] != rec["long_path_safe"]:
        problems.append(f"WARNING: a naive enumerator would have silently missed "
                        f"{rec['long_path_safe'] - rec['naive_os_walk']} envelope(s)")
    records = []
    for i, rel in enumerate(envelopes, start=1):
        full = os.path.join(str(input_root), rel)
        records.append({"record_id": f"ARC-{i:04d}", "envelope": rel, "sha256": sha256_file(full),
                        "path_length": len(os.path.abspath(full))})
    state = {"stage": "s1_enumerate", "input_root_name": Path(input_root).name, "status": status,
             "reconciliation": rec, "problems": problems, "records": records}
    jsonio.write(out_path, state)
    return state
