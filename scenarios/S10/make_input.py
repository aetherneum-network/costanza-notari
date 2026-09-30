"""Generate S10 input (deterministic): heartbeat state before the outage and the PEC deliveries
(UTC timestamps) of the main synthetic corpus of Fornace Aurelia S.r.l. for 19-21 October 2026."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    gold = [json.loads(l) for l in (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    deliveries = sorted({g["notification_utc"] for g in gold if g["notification_utc"][:10] >= "2026-10-19"})
    inp = HERE / "input"
    inp.mkdir(exist_ok=True)
    (inp / "deliveries.json").write_text(json.dumps({"company": "Fornace Aurelia S.r.l. (synthetic)",
                                                    "deliveries_utc": deliveries}, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
    (inp / "heartbeat.json").write_text(json.dumps({
        "last_full_window": "2026-10-19",
        "runs": [{"now_utc": "2026-10-20T01:05:00+00:00", "mode": "full", "windows": ["2026-10-19"], "catch_up": False}]},
        indent=2) + "\n", encoding="utf-8", newline="\n")
    (inp / "timeline.json").write_text(json.dumps({
        "host_off_utc": ["2026-10-20T22:00:00+00:00", "2026-10-21T06:00:00+00:00"],
        "missed_trigger_local": "2026-10-21 03:05 Europe/Rome (CEST) = 01:05 UTC",
        "first_run_after": {"now_utc": "2026-10-21T06:30:00+00:00", "mode": "light", "local": "08:30 CEST"},
        "later_same_day": {"now_utc": "2026-10-21T12:00:00+00:00", "mode": "light"},
        "next_night": {"now_utc": "2026-10-22T01:05:00+00:00", "mode": "full"}}, indent=2) + "\n",
        encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
