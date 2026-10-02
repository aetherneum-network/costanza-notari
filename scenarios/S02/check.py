"""S02 - Revised instalment; stale figure in cover letter (Cantine Belvedere S.p.A.).
Pass: 5/5 stale values found, <= 1 false positive (L2)."""
import datetime as dt
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import load, main, report, workdir  # noqa: E402
from pipeline import s7_ledger, s9_distribution  # noqa: E402


def check():
    w = workdir("S02")
    led = s7_ledger.run(load(HERE / "input" / "notices.json"), w / "ledger", w / "07.json",
                        as_of="2026-10-21T09:40:00+02:00", release="OK")
    register = [e for e in led["superseded_values"] if e["field"] == "amount_due"]
    out = w / "outgoing"
    shutil.copytree(HERE / "input" / "outgoing", out)
    for rel, day in load(HERE / "input" / "file_dates.json").items():
        t = dt.datetime.fromisoformat(day + "T12:00:00+00:00").timestamp()
        os.utime(out / rel, (t, t))
    res = s9_distribution.scan(register, out, known_entities=["AGENZIA ESEMPIO RISCOSSIONE", "TESSITURE MONTEVERDE S.R.L.",
                                                              "CANTINE BELVEDERE S.P.A."],
                               responses=load(HERE / "input" / "owner_responses.json"))
    exp = load(HERE / "expected" / "expected.json")
    flagged = sorted({f["file"] for f in res["findings"] if f["status"] == "open"})
    tp = sorted(set(flagged) & set(exp["stale_files"]))
    fp = sorted(set(flagged) - set(exp["stale_files"]))
    closed = sorted({f["file"] for f in res["findings"] if f["status"] == "closed_by_owner"})
    ok = (len(tp) == 5 and len(fp) <= 1 and closed == exp["closed_by_owner"]
          and register[0]["old"] == "3415.20" and register[0]["new"] == "3154.20"
          and sorted(res["by_owner"]) == exp["owners"])
    precision = round(len(tp) / len(flagged), 3) if flagged else None
    return report("S02", ok, f"{len(tp)}/5 stale values found, {len(fp)} false positive(s), precision {precision}; "
                  f"{res['raw_matches']} raw matches, suppressed {res['suppressed']}; "
                  f"owners {sorted(res['by_owner'])}; closed by owner {closed}",
                  {"flagged": flagged, "fp": fp, "register": register, "scan": res})


if __name__ == "__main__":
    main(check)
