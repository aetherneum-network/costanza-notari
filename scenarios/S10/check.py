"""S10 - Host off overnight (Fornace Aurelia S.r.l.). Pass: the catch-up run recovers the window and says so (L9)."""
import datetime as dt
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import load, main, report, workdir  # noqa: E402
from pipeline import heartbeat as hb  # noqa: E402


def check():
    w = workdir("S10")
    shutil.copyfile(HERE / "input" / "heartbeat.json", w / "heartbeat.json")
    deliveries = load(HERE / "input" / "deliveries.json")["deliveries_utc"]
    tl = load(HERE / "input" / "timeline.json")
    exp = load(HERE / "expected" / "expected.json")

    def do_window(win):
        n = sum(1 for d in deliveries if d[:10] == win.isoformat())
        return [f"window {win.isoformat()} (UTC): {n} PEC deliveries classified and indexed"]

    refreshed = []

    def do_refresh():
        refreshed.append(True)
        return {"refreshed": "data only"}

    h = hb.Heartbeat(w)
    r1 = h.run(dt.datetime.fromisoformat(tl["first_run_after"]["now_utc"]), mode="light", do_window=do_window,
               do_refresh=do_refresh)
    r2 = hb.Heartbeat(w).run(dt.datetime.fromisoformat(tl["later_same_day"]["now_utc"]), mode="light",
                             do_window=do_window, do_refresh=do_refresh)
    r3 = hb.Heartbeat(w).run(dt.datetime.fromisoformat(tl["next_night"]["now_utc"]), mode="full",
                             do_window=do_window, do_refresh=do_refresh)
    j = load(w / "judgement" / "2026-10-20.json")
    trig = hb.should_run(dt.date(2026, 10, 21), "03:05") and not hb.should_run(dt.date(2026, 10, 21), "02:05")
    ok = (r1["message"] == exp["first_run"]["message"] and r1["windows"] == exp["first_run"]["windows"]
          and r1["catch_up"] and j["catch_up"] and j["judgement"] == exp["judgement_2026_10_20"]
          and r2["windows"] == [] and not r2["catch_up"]
          and [x["window"] for x in r3["windows"]] == ["2026-10-21"] and not r3["catch_up"]
          and load(w / "heartbeat.json")["last_full_window"] == "2026-10-21" and len(refreshed) == 2 and trig)
    return report("S10", ok, f"first run after the outage (light, 08:30 CEST): '{r1['message']}'; judgement "
                  f"2026-10-20 written with catch_up=true ({j['judgement'][0]}); later light run: no catch-up; next "
                  f"night: window 2026-10-21 only; missed trigger was 03:05 CEST = 01:05 UTC: {trig}",
                  {"r1": r1, "r2": r2, "r3": r3})


if __name__ == "__main__":
    main(check)
