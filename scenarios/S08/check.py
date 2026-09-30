"""S08 - 300-character paths and accented names (Società Agricola Valle dell'Èrto). Pass: counts reconcile; names intact (L8)."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import load, main, report, workdir  # noqa: E402
from pipeline import entities, s1_enumerate  # noqa: E402
from pipeline.lib import jsonio  # noqa: E402


def check():
    w = workdir("S08")
    spec = load(HERE / "input" / "tree_spec.json")
    tree = w / "tree"
    for rel in spec["paths"]:
        p = s1_enumerate.extended(os.path.join(str(tree), rel))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(rel.encode("utf-8"))
    manifest = w / "manifest.json"
    manifest.write_text(json.dumps({"expected_envelopes": len(spec["paths"]), "files": [{"path": p} for p in spec["paths"]]},
                                   ensure_ascii=False), encoding="utf-8")
    st = s1_enumerate.run(tree, w / "01_enumeration.json", manifest=manifest,
                          robocopy_log=(w / "robocopy.log") if os.name == "nt" else None)
    rec = st["reconciliation"]
    reread = jsonio.read(w / "01_enumeration.json")  # UTF-8 round trip
    names_intact = sorted(r["envelope"] for r in reread["records"]) == sorted(spec["paths"])
    longest = max(r["path_length"] for r in reread["records"])
    over_300 = sum(1 for r in reread["records"] if r["path_length"] > 300)
    d = entities.EntityDictionary()
    canon = {d.resolve(v) for v in spec["name_variants"]}
    (only,) = canon if len(canon) == 1 else (None,)
    repairs = []
    h = jsonio.load_lenient(HERE / "input" / "handoff_single_backslashes.json", repairs)
    rc = rec.get("robocopy_all_files")
    ok = (st["status"] == "OK" and rec["long_path_safe"] == rec["manifest"] == 40 and names_intact and longest > 300
          and only == "SOCIETÀ AGRICOLA VALLE DELL’ÈRTO S.S." and len(d.entries[only]["aliases_seen"]) == 3
          and repairs and h["source"] == "C:\\Users\\Archivio\\Èrto\\atto.eml" and (rc is None or rc == 40))
    return report("S08", ok, f"manifest {rec['manifest']}, long-path-safe {rec['long_path_safe']}, naive os.walk "
                  f"{rec['naive_os_walk']} (silently missed {rec['long_path_safe'] - rec['naive_os_walk']}), robocopy /L "
                  f"{rc if rc is not None else 'n/a'}; {over_300} paths > 300 chars (longest {longest}); names intact after "
                  f"UTF-8 round trip: {names_intact}; 4 name variants -> 1 canonical '{only}'; backslash repairs logged: "
                  f"{repairs[0]['repairs'] if repairs else 0}", {"reconciliation": rec, "repairs": repairs})


if __name__ == "__main__":
    main(check)
