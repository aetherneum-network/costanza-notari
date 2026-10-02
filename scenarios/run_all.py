"""Run the ten scenario checks; print one PASS/FAIL line each and a total. Exit 1 if any fails."""
import importlib.util
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

IDS = [f"S{i:02d}" for i in range(1, 11)]


def load_check(sid):
    spec = importlib.util.spec_from_file_location(f"scenario_{sid}", HERE / sid / "check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check


def run_all(ids=IDS):
    results = []
    for sid in ids:
        t = time.time()
        try:
            ok, line, _ = load_check(sid)()
        except Exception as exc:  # a crashing check is a failing check
            ok, line = False, f"{sid} FAIL - {type(exc).__name__}: {exc}"
        results.append((sid, ok, line, round(time.time() - t, 1)))
        print(f"{line}  [{results[-1][3]}s]", flush=True)
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"\nScenarios: {passed}/{len(results)} PASS")
    return results


if __name__ == "__main__":
    res = run_all(sys.argv[1:] or IDS)
    sys.exit(0 if all(ok for _, ok, _, _ in res) else 1)
