"""Shared helpers for the offline test-suite (stdlib unittest; no network, no API)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus" / "out"
AS_OF = "2026-10-21T09:40:00+02:00"
TMP = ROOT / "build" / "test-tmp"


def ensure_corpus() -> Path:
    if not (CORPUS / "manifest.json").exists():
        subprocess.run([sys.executable, str(ROOT / "corpus" / "generate.py")], check=True, cwd=ROOT)
    return CORPUS


def tmpdir(name: str) -> Path:
    """Fresh directory inside the repository's build/ (never outside the repo)."""
    p = TMP / name
    if p.exists():
        shutil.rmtree(_ext(p))
    p.mkdir(parents=True)
    return p


def _ext(p: Path) -> str:
    s = os.path.abspath(str(p))
    return "\\\\?\\" + s if os.name == "nt" and not s.startswith("\\\\?\\") else s


def openssl() -> str | None:
    for cand in (shutil.which("openssl"), r"C:\Program Files\Git\mingw64\bin\openssl.exe",
                 r"C:\Program Files\Git\usr\bin\openssl.exe"):
        if cand and Path(cand).exists():
            return cand
    return None


def run_pipeline(name: str, *extra: str, as_of: str = AS_OF, fresh: bool = True) -> tuple[int, Path]:
    from pipeline import run as runner
    ensure_corpus()
    base = TMP / "runs" / name
    if fresh and base.exists():
        shutil.rmtree(_ext(base))
    args = ["--input", str(CORPUS), "--work", str(base / "work"), "--ledger", str(base / "ledger"),
            "--store", str(base / "store"), "--as-of", as_of, *extra]
    code = runner.main(args)
    return code, base


@lru_cache(maxsize=None)
def main_run() -> Path:
    """One cached full run of the main corpus shared by several test modules."""
    code, base = run_pipeline("main")
    assert code == 0, f"main pipeline run failed with exit code {code}"
    return base
