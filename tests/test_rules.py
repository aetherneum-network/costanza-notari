"""Every rule carries id, rationale and its own tests (L7) - and those tests pass."""
import datetime as dt
import json
import unittest

from tests._util import ROOT
from pipeline import amounts, attribution, deadlines, entities, termclauses, typeagree, urgency
from pipeline.rules_engine import RuleFile
from pipeline.s6_consolidate import classify_dissent

RULES = ROOT / "rules"
CONFIG = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((RULES / name).read_text(encoding="utf-8"))


class RuleFileStructure(unittest.TestCase):
    def test_every_rule_has_id_rationale_tests_and_ids_are_unique(self):
        seen = set()
        for name, key in (("doc_type.json", "rules"), ("area.json", "rules"), ("deadline_nature.json", "rules"),
                          ("urgency.json", "rules"), ("amounts.json", "rules"), ("term_clauses.json", "rules"),
                          ("doc_type.json", "title_families"), ("deadline_nature.json", "vetoes"),
                          ("doc_type.json", "title_merge"), ("amounts.json", "agreement"),
                          ("attribution.json", "channel_sender_side")):
            for r in load(name)[key]:
                for k in ("id", "rationale", "tests"):
                    self.assertIn(k, r, f"{name}:{r.get('id')}")
                self.assertTrue(r["tests"], f"{name}:{r['id']} has no tests")
                self.assertNotIn((name, r["id"]), seen)
                seen.add((name, r["id"]))
        for sc in load("sender_class.json")["short_circuits"]:
            self.assertTrue(sc["tests"] and sc["rationale"])

    def test_every_rule_file_is_versioned(self):
        for p in sorted(RULES.glob("*.json")):
            self.assertIn("version", load(p.name), p.name)


class InlineRuleTests(unittest.TestCase):
    def test_doc_type_and_area_rules(self):
        for name in ("doc_type.json", "area.json"):
            self.assertEqual(RuleFile.load(name).run_inline_tests(), [], name)

    def test_sender_class_rules(self):
        cfg = load("sender_class.json")
        debtor = entities.Debtor(CONFIG["debtor"])
        cases = [t for sc in cfg["short_circuits"] for t in sc["tests"]] + cfg["tests"]
        for t in cases:
            got = attribution.classify_sender(t["input"]["addr"], t["input"]["display"], t["input"]["content"], debtor)
            self.assertEqual(got["class"], t["expect"]["class"], (t["id"], got))

    def test_channel_sender_side_rules(self):
        self.assertEqual(attribution.run_sender_side_tests(entities.Debtor(CONFIG["debtor"])), [])

    def test_deadline_nature_rules(self):
        data = load("deadline_nature.json")
        for r in data["rules"] + data["vetoes"]:   # a veto's own tests expect the veto id unless they say otherwise
            for t in r["tests"]:
                i = t["input"]
                nature, rid = deadlines.classify_nature(i.get("before", ""), i.get("after", ""),
                                                        i.get("date", "2026-12-01"), i.get("reference"),
                                                        i.get("before_local"))
                self.assertEqual((nature, rid), (t["expect"]["nature"], t.get("expect_rule", r["id"])), t["id"])

    def test_term_clause_rules(self):
        self.assertEqual(termclauses.run_inline_tests(), [])
        slots = {r["slot"] for r in load("term_clauses.json")["rules"]}
        self.assertEqual(slots, {"lead_in", "unit", "qualifier", "anchor", "complement", "mood"})

    def test_title_family_rules(self):
        self.assertEqual(typeagree.run_inline_tests(load("doc_type.json"), load("terms.json")), [])

    def test_title_merge_rules(self):
        self.assertEqual(typeagree.run_merge_tests(RuleFile.load("doc_type.json"), load("doc_type.json"),
                                                   load("terms.json")), [])

    def test_urgency_rules(self):
        as_of = dt.date(2026, 10, 21)
        for r in load("urgency.json")["rules"]:
            for t in r["tests"]:
                i = t["input"]
                drv = None
                if "days_left" in i:
                    d = as_of + dt.timedelta(days=i["days_left"])
                    drv = {"date": d.isoformat(), "nature": "computed", "status": "open" if i["days_left"] >= 0 else "expired"}
                level, rid, _ = urgency.compute(i["doc_type"], drv, i.get("deadline") == "RECUPERARE", as_of)
                self.assertEqual((level, rid), (t["expect"]["urgency"], r["id"]), t["id"])

    def test_amount_rules(self):
        for r in load("amounts.json")["rules"]:
            for t in r["tests"]:
                v, rid = amounts.extract_amount(t["input"]["text"], t["input"]["doc_type"])
                want_rule = t["expect_rule"] if "expect_rule" in t else r["id"]
                self.assertEqual((v, rid), (t["expect"]["amount_due"], want_rule), t["id"])

    def test_amount_agreement_rules(self):
        """Each test of a row must be decided by that row; 'expect_rule' is the rule id left in the trace."""
        for r in load("amounts.json")["agreement"]:
            for t in r["tests"]:
                got = amounts.read_amount(t["input"]["text"], t["input"]["doc_type"])
                self.assertEqual((got.value, got.rule, got.agreement),
                                 (t["expect"]["amount_due"], t["expect_rule"], r["id"]), t["id"])

    def test_dissent_natures(self):
        self.assertEqual(classify_dissent("none")[0], "none")
        self.assertEqual(classify_dissent("No dissent.")[0], "none")
        self.assertEqual(classify_dissent("No dissent on the merits, however the deadline is RECUPERARE")[0], "note")
        self.assertEqual(classify_dissent("The amount is 12,830.00, not 12,380.00")[0], "dissent")


class RuleChangeDiff(unittest.TestCase):
    def test_changing_one_rule_changes_exactly_its_records(self):
        """L7 in miniature (S07 is the full scenario)."""
        base = RuleFile.load("area.json")
        data = load("area.json")
        for r in data["rules"]:
            if r["id"] == "R-014":
                r["then"] = {"area": "tax"}
        changed = RuleFile(data, "area.json (patched)")
        recs = [{"doc_type": "cartella_pagamento"}, {"doc_type": "intimazione_pagamento"},
                {"doc_type": "avviso_addebito"}]
        diff = [(r["doc_type"], base.apply(r)[0]["area"], changed.apply(r)[0]["area"]) for r in recs
                if base.apply(r) != changed.apply(r)]
        self.assertEqual(diff, [("cartella_pagamento", "collection", "tax")])


if __name__ == "__main__":
    unittest.main()
