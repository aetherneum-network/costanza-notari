import copy
import json
import unittest

from tests._util import ROOT, main_run, tmpdir
from pipeline import s7_ledger as s7
from pipeline.lib import jsonio

AS_OF = "2026-10-21T09:40:00+02:00"


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cons = jsonio.read(main_run() / "work" / "state" / "06_consolidation.json")
        cls.gold = [json.loads(l) for l in (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_counts_dedup_and_idempotency(self):
        d = tmpdir("s7-counts")
        st = s7.run(copy.deepcopy(self.cons), d / "ledger", d / "07.json", as_of=AS_OF, release="OK")
        self.assertEqual(st["counts"], {"insert": 286, "supersede": 6, "historical_edition": 0, "duplicate_ignored": 8})
        self.assertEqual(st["current_units"], 286)
        again = s7.run(copy.deepcopy(self.cons), d / "ledger", d / "07b.json", as_of=AS_OF, release="OK")
        self.assertEqual(again["appended"], 0)

    def test_superseded_register_matches_the_revised_notices(self):
        d = tmpdir("s7-register")
        st = s7.run(copy.deepcopy(self.cons), d / "ledger", d / "07.json", as_of=AS_OF, release="OK")
        by_env = {g["envelope"]: g for g in self.gold}
        expected = sorted((by_env[g["supersedes"]]["amount_due"], g["amount_due"]) for g in self.gold
                          if g["supersedes"] and not g["duplicate_of"])
        got = sorted((e["old"], e["new"]) for e in st["superseded_values"] if e["field"] == "amount_due")
        self.assertEqual(got, expected)
        e = next(x for x in st["superseded_values"] if x["field"] == "amount_due")
        for k in ("old", "new", "since", "proof", "owners"):
            self.assertIn(k, e)

    def test_edition_bound_label(self):
        self.assertEqual(s7.edition_label({"v": "3154.20", "per": "EX-2231", "edition_date": "2026-10-20"}),
                         "3,154.20 - per notice ref. EX-2231 of 2026-10-20")

    def test_history_rewrite_is_detected(self):
        d = tmpdir("s7-tamper")
        s7.run(copy.deepcopy(self.cons), d / "ledger", d / "07.json", as_of=AS_OF, release="OK")
        p = d / "ledger" / "ledger.jsonl"
        lines = p.read_bytes().splitlines()
        lines[3] = lines[3].replace(b'"insert"', b'"insert" ', 1)
        p.write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaises(s7.LedgerIntegrityError):
            s7.Ledger(d / "ledger")

    def test_blocked_run_does_not_advance_the_ledger(self):
        d = tmpdir("s7-blocked")
        st = s7.run(copy.deepcopy(self.cons), d / "ledger", d / "07.json", as_of=AS_OF, release="BLOCKED")
        self.assertEqual(st["appended"], 0)
        self.assertEqual(s7.Ledger(d / "ledger").events, [])
        self.assertEqual(len(jsonio.read(d / "07_pending_events.json")["events"]), 300)

    def test_older_edition_arriving_later_never_becomes_current(self):
        d = tmpdir("s7-order")
        revised = [g["envelope"] for g in self.gold if g["supersedes"] and not g["duplicate_of"]]
        first = {g["supersedes"] for g in self.gold if g["supersedes"] and not g["duplicate_of"]}
        late = [r for r in self.cons["records"] if r["envelope"] in first]
        early = [r for r in self.cons["records"] if r["envelope"] not in first]
        s7.run({"records": copy.deepcopy(early)}, d / "ledger", d / "07a.json", as_of=AS_OF, release="OK")
        st = s7.run({"records": copy.deepcopy(late)}, d / "ledger", d / "07b.json", as_of=AS_OF, release="OK")
        self.assertEqual(st["counts"]["historical_edition"], len(revised))
        self.assertEqual(st["counts"]["supersede"], 0)


if __name__ == "__main__":
    unittest.main()
