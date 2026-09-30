"""S07 - One rule changed (Tessiture Monteverde S.r.l.). Pass: exactly the expected records change, the run reports the diff (L7)."""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import ROOT, ensure_corpus, load, main, report, workdir  # noqa: E402
from pipeline import s1_enumerate, s2_envelope, s3_signature, s4_text, s5_classify  # noqa: E402
from pipeline.lib import jsonio, tzrome  # noqa: E402
from pipeline.rules_engine import diff_classifications  # noqa: E402


def check():
    ensure_corpus()
    w = workdir("S07")
    inp, cfg = HERE / "input" / "corpus", load(HERE / "input" / "config.json")
    as_of = tzrome.parse_iso(cfg["as_of"])
    e1 = s1_enumerate.run(inp, w / "01.json", manifest=inp / "manifest.json")
    e2 = s2_envelope.run(inp, e1, w, w / "02.json")
    e3 = s3_signature.run(e2, w, ROOT / cfg["trust_anchors"], w / "03.json")
    e4 = s4_text.run(e3, w, w / "04.json")
    before = s5_classify.run(e2, e3, e4, cfg, as_of, w / "fan_before", w / "05_before.json")
    patched = w / "rules_patched"
    shutil.copytree(ROOT / "rules", patched)
    patch = load(HERE / "input" / "rule_patch.json")
    data = jsonio.read(patched / patch["file"])
    for r in data["rules"]:
        if r["id"] == patch["rule_id"]:
            r["then"] = patch["then"]
            r["tests"] = [t for t in r["tests"] if isinstance(t, str)]  # its own tests change with it
    data["version"] += "+S07"
    jsonio.write(patched / patch["file"], data)
    after = s5_classify.run(e2, e3, e4, cfg, as_of, w / "fan_after", w / "05_after.json", rules_dir=patched)
    env_of = {r["record_id"]: r["envelope"].rsplit("_", 1)[-1][:-4] for r in before["records"]}
    diff = diff_classifications(before["records"], after["records"])
    jsonio.write(w / "classification_diff.json", {"rule_changed": patch, "diff": diff})
    got = sorted((env_of[d["record_id"]], d["field"], d["before"], d["after"], d["rule_before"], d["rule_after"]) for d in diff)
    exp = [tuple(x) for x in load(HERE / "expected" / "expected.json")["diff"]]
    ok = got == exp and len(before["records"]) == 12
    return report("S07", ok, f"rule {patch['rule_id']} -> {patch['then']}: {len(got)} change(s), exactly "
                  f"{sorted({g[0] for g in got})} ({got[0][2]} -> {got[0][3]} via {got[0][4]}); the other "
                  f"{12 - len(got)} records unchanged; diff written to classification_diff.json",
                  {"diff": diff})


if __name__ == "__main__":
    main(check)
