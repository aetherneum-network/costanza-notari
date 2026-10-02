"""S06 - Recital dates vs actionable deadlines (Cantine Belvedere S.p.A.). Pass: urgency from 6 of 20 dates (L6)."""
import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import ensure_corpus, load, main, report, run_pipeline, workdir  # noqa: E402
from pipeline import urgency  # noqa: E402


def check():
    ensure_corpus()
    w = workdir("S06")
    code, _ = run_pipeline(HERE / "input" / "corpus", w, config=HERE / "input" / "config.json",
                           as_of="2026-10-21T09:40:00+02:00")
    exp = load(HERE / "expected" / "expected.json")
    recs = {r["envelope"]: r for r in load(w / "work" / "state" / "06_consolidation.json")["records"]}
    items, eligible, problems, naive = 0, 0, [], {}
    as_of = dt.date.fromisoformat(exp["as_of"])
    for env, e in exp["notices"].items():
        r = recs[env]
        written = [[d["date"], d["nature"]] for d in r["dates"]]
        computed = [d["date"] for d in r["deadlines"] if d["nature"] == "computed"]
        items += len(written) + len(computed)
        eligible += sum(1 for _, n in written if n == "actionable") + len(computed)
        if written != e["written"]:
            problems.append((env, "written", written))
        if computed != e["computed"]:
            problems.append((env, "computed", computed))
        if (r["deadline"], r["urgency"]) != (e["driving"], e["urgency"]):
            problems.append((env, "driving", r["deadline"], r["urgency"]))
        drivers = {d for d, n in e["written"] if n == "actionable"} | set(e["computed"])
        if r["deadline"] not in drivers:
            problems.append((env, "urgency driven by a non-eligible date", r["deadline"]))
        # what a naive "every future date is a deadline" reading would have shown
        fut = sorted(d for d, _ in e["written"] if d >= exp["as_of"]) + sorted(e["computed"])
        nd = min(fut) if fut else None
        naive[env[-6:-4]] = urgency.compute("x", {"date": nd, "status": "open"} if nd else None, False, as_of)[0]
    ok = code == 0 and not problems and items == exp["total_items"] and eligible == exp["driving_eligible"]
    got = {env[-6:-4]: recs[env]["urgency"] for env in exp["notices"]}
    return report("S06", ok, f"{items} date items, {eligible} actionable/computed drive urgency: {got} "
                  f"(a naive every-future-date reading would give {naive}); problems {len(problems)}",
                  {"problems": problems, "urgency": got, "naive": naive})


if __name__ == "__main__":
    main(check)
