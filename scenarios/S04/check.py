"""S04 - Version conflict on publish (Fornace Aurelia S.r.l.). Pass: run FAILED, banner visible, no OK (L4)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import ROOT, load, main, report, run_pipeline, subset_input, workdir  # noqa: E402
from pipeline import publish  # noqa: E402
from pipeline.lib import tzrome  # noqa: E402


def check():
    w = workdir("S04")
    sc = load(HERE / "input" / "scenario.json")
    gold = [json.loads(l) for l in (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    inp = subset_input(w / "input", [g["envelope"] for g in gold if not g["duplicate_of"]][:20])
    cfg = ROOT / "corpus" / "config.json"
    c0, _ = run_pipeline(inp, w / "yesterday", config=cfg, as_of=sc["yesterday_run_as_of"])
    # today's run shares yesterday's store and ledger
    for sub in ("store", "ledger"):
        (w / "today").mkdir(exist_ok=True)
        import shutil
        shutil.copytree(w / "yesterday" / sub, w / "today" / sub)
    code, out = run_pipeline(inp, w / "today", config=cfg, as_of=sc["today_run_as_of"],
                             extra=["--simulate-concurrent-publish"])
    rep = load(w / "today" / "work" / "run_report.json")
    md = (w / "today" / "work" / "run_report.md").read_text(encoding="utf-8")
    from openpyxl import load_workbook
    banner = load_workbook(w / "today" / "work" / "build" / "master_index.xlsx")["Index"]["A3"].value
    reader = publish.reader_view(w / "today" / "store", tzrome.parse_iso(sc["today_run_as_of"]))
    exp = load(HERE / "expected" / "expected.json")
    ok = (c0 == 0 and code == exp["exit_code"] and rep["status"] == exp["status"]
          and exp["failure_contains"] in rep.get("failure", "") and exp["run_report_banner"] in md
          and banner.startswith(exp["draft_index_banner_prefix"]) and exp["stdout_must_not_contain"] not in out
          and all(reader[k] == v for k, v in exp["reader"].items()))
    return report("S04", ok, f"exit {code}, status {rep['status']} ({rep.get('failure')}); run report banner "
                  f"{'visible' if exp['run_report_banner'] in md else 'MISSING'}; draft index banner '{banner[:40]}...'; "
                  f"readers see v{reader['version']} as of {reader['as_of']} -> {reader['banner'][:10]}; no 'RUN OK' printed: "
                  f"{exp['stdout_must_not_contain'] not in out}", {"report": rep, "reader": reader, "stdout": out})


if __name__ == "__main__":
    main(check)
