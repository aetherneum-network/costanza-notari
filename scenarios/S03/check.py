"""S03 - Queue changes between two status queries (Tessiture Monteverde S.r.l.).
Pass: second answer reflects the change and shows a later as_of (L3)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import load, main, report, workdir  # noqa: E402
from pipeline import status  # noqa: E402
from pipeline.lib import tzrome  # noqa: E402
from pipeline.s7_ledger import Ledger  # noqa: E402


def check():
    w = workdir("S03")
    ev = load(HERE / "input" / "events.json")
    led = Ledger(w / "ledger")
    for e in ev["at_0830"]:
        led.append(e)
    first = status.status(w / "ledger", lambda: tzrome.parse_iso(ev["query_1"]))
    remembered = dict(first)  # what an agent would "remember" from the earlier turn
    writer = Ledger(w / "ledger")  # someone else answers the three notices at 09:15
    for e in ev["at_0915"]:
        writer.append(e)
    second = status.status(w / "ledger", lambda: tzrome.parse_iso(ev["query_2"]))
    exp = load(HERE / "expected" / "expected.json")
    ok = (all(first[k] == v for k, v in exp["first"].items()) and all(second[k] == v for k, v in exp["second"].items())
          and second["as_of"] > first["as_of"] and remembered["pending_count"] != second["pending_count"]
          and second["ledger_sha256"] != first["ledger_sha256"])
    return report("S03", ok, f"query 1: '{first['answer']}'; query 2: '{second['answer']}' "
                  f"(ledger re-read: {first['ledger_events']} -> {second['ledger_events']} events)",
                  {"first": first, "second": second})


if __name__ == "__main__":
    main(check)
