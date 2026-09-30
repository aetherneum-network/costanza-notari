"""S01 - Transposed amount at handoff (Fornace Aurelia S.r.l.). Pass: release blocked; mismatch reported (L1)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import ROOT, load, report, run_pipeline, subset_input, workdir, main  # noqa: E402
from pipeline import s6_consolidate  # noqa: E402
from pipeline.lib import jsonio  # noqa: E402
from pipeline.s5_classify import anchors_of  # noqa: E402


def check():
    w = workdir("S01")
    recs = [json.loads(l) for l in (HERE / "input" / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    fan = w / "fanout"
    chunks = []
    for n, i in enumerate(range(0, len(recs), 40), start=1):
        cid = f"chunk-{n:02d}"
        part = recs[i:i + 40]
        jsonio.write(fan / "chunks" / f"{cid}.json", {"chunk": cid, "records": part})
        for r in part:
            jsonio.write(fan / "handoffs" / f"handoff_{r['record_id']}.json",
                         {"id": r["record_id"], "from": cid, "to": "consolidator", "anchors": anchors_of(r)})
        chunks.append({"chunk": cid, "records": len(part)})
    st = s6_consolidate.run({"chunks": chunks}, fan, w / "06.json", fault_injection=load(HERE / "input" / "fault_plan.json"))
    s = st["sentinel"]
    exp = load(HERE / "expected" / "expected.json")
    got_mm = [{k: m[k] for k in exp["mismatches"][0]} for m in s["mismatches"]]
    blocked_ids = {m["id"] for m in s["mismatches"]}
    false_blocks = len(blocked_ids - {"ARC-0412"})
    part1 = s["release"] == exp["release"] and got_mm == exp["mismatches"] and false_blocks == exp["false_blocks"]
    # end to end: the same fault in a real run -> exit code 2, nothing published, red banner on the draft
    gold = [json.loads(l) for l in (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    subset = [g["envelope"] for g in gold if not g["duplicate_of"]][:40]
    inp = subset_input(w / "e2e-input", subset)
    plan = w / "e2e_fault.json"
    target = next(i for i, g in enumerate(gold[:40], start=1) if g["amount_due"] and not g["duplicate_of"])
    plan.write_text(json.dumps({"transpose": [{"record_id": f"ARC-{target:04d}", "field": "amount_due"}]}), encoding="utf-8")
    code, out = run_pipeline(inp, w / "e2e", config=ROOT / "corpus" / "config.json", as_of="2026-10-21T09:40:00+02:00",
                             extra=["--fault-injection", str(plan)])
    rep = load(w / "e2e" / "work" / "run_report.json")
    from openpyxl import load_workbook
    banner = load_workbook(w / "e2e" / "work" / "build" / "master_index.xlsx")["Index"]["A3"].value
    ledger = w / "e2e" / "ledger" / "ledger.jsonl"
    part2 = (code == 2 and rep["status"] == "BLOCKED" and rep["published"] is None and "RUN OK" not in out
             and banner.startswith("RELEASE BLOCKED") and not ledger.exists())
    mm = s["mismatches"][0] if s["mismatches"] else {}
    return report("S01", part1 and part2,
                  f"release {s['release']}; {mm.get('id')} {mm.get('anchor')} sent {mm.get('sent')} by "
                  f"{mm.get('handoff_from')} ({mm.get('handoff_file')}) / understood {mm.get('understood')} by "
                  f"{mm.get('receipt_by')} ({mm.get('receipt_file')}); false blocks {false_blocks}/199; "
                  f"end-to-end exit {code}, published {rep['published']}, banner '{banner[:15]}...'",
                  {"sentinel": s, "e2e_exit": code, "e2e_banner": banner})


if __name__ == "__main__":
    main(check)
