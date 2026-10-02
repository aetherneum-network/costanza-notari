"""Shared helpers for scenarios S01-S10 (synthetic; offline; deterministic)."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BUILD = ROOT / "build" / "scenarios"


def ensure_corpus() -> Path:
    out = ROOT / "corpus" / "out"
    if not (out / "manifest.json").exists():
        subprocess.run([sys.executable, str(ROOT / "corpus" / "generate.py")], check=True, cwd=ROOT)
    return out


def workdir(sid: str) -> Path:
    p = BUILD / sid
    if p.exists():
        shutil.rmtree("\\\\?\\" + str(p.resolve()) if os.name == "nt" else p)
    p.mkdir(parents=True)
    return p


def load(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def run_pipeline(input_dir: Path, work: Path, *, config: Path, as_of: str, extra: list[str] | None = None) -> tuple[int, str]:
    from pipeline import run as runner
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = runner.main(["--input", str(input_dir), "--config", str(config), "--work", str(work / "work"),
                            "--ledger", str(work / "ledger"), "--store", str(work / "store"), "--as-of", as_of,
                            *(extra or [])])
    return code, buf.getvalue()


def subset_input(dst: Path, envelopes: list[str]) -> Path:
    """Copy some envelopes of the main corpus into a scenario input dir with its own manifest."""
    src = ensure_corpus()
    files = []
    for rel in envelopes:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, dst / rel)
        files.append({"path": rel})
    (dst / "manifest.json").write_text(json.dumps({"expected_envelopes": len(files), "files": files}, indent=2),
                                       encoding="utf-8")
    return dst


def report(sid: str, ok: bool, summary: str, details: dict | None = None) -> tuple[bool, str, dict]:
    line = f"{sid} {'PASS' if ok else 'FAIL'} - {summary}"
    out = BUILD / sid / "result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"scenario": sid, "pass": ok, "summary": summary, "details": details or {}},
                              indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return ok, line, details or {}


def main(check) -> None:
    ok, line, _ = check()
    print(line)
    sys.exit(0 if ok else 1)
