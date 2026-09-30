import json
import unittest

from tests._util import tmpdir
from pipeline import s6_consolidate as s6
from pipeline.lib import jsonio
from pipeline.s5_classify import anchors_of


def _fanout(name, n=3, bad_backslash=False):
    d = tmpdir(name)
    recs = [{"record_id": f"ARC-{i:04d}", "doc_type": "cartella_pagamento", "amount_due": f"{12380 + i}.00",
             "deadline": "2026-11-14", "party_entity": "AGENZIA ESEMPIO RISCOSSIONE", "recuperare_fields": []}
            for i in range(1, n + 1)]
    recs[-1]["recuperare_fields"] = ["counterparty_channel"]
    jsonio.write(d / "chunks" / "chunk-01.json", {"chunk": "chunk-01", "records": recs})
    for r in recs:
        jsonio.write(d / "handoffs" / f"handoff_{r['record_id']}.json",
                     {"id": r["record_id"], "from": "chunk-01", "to": "consolidator", "anchors": anchors_of(r),
                      "chunk_file": "chunks/chunk-01.json"})
    if bad_backslash:
        p = d / "handoffs" / "handoff_ARC-0001.json"
        obj = json.loads(p.read_text(encoding="utf-8"))
        text = json.dumps(obj).replace('"chunks/chunk-01.json"', '"C:\\\\Users\\\\x"').replace("\\\\", "\\")
        p.write_text(text, encoding="utf-8")
    return d, {"chunks": [{"chunk": "chunk-01", "records": n}]}


class SentinelTests(unittest.TestCase):
    def test_clean_handoffs_release(self):
        d, st = _fanout("s6-clean")
        out = s6.run(st, d, d / "06.json")
        self.assertEqual(out["sentinel"]["release"], "OK")
        self.assertEqual(out["sentinel"]["mismatches"], [])

    def test_transposed_amount_blocks_release_and_names_both_sides(self):
        d, st = _fanout("s6-transpose")
        out = s6.run(st, d, d / "06.json", fault_injection={"transpose": [{"record_id": "ARC-0002", "field": "amount_due"}]})
        s = out["sentinel"]
        self.assertEqual(s["release"], "BLOCKED")
        self.assertEqual(len(s["mismatches"]), 1)
        mm = s["mismatches"][0]
        self.assertEqual((mm["id"], mm["anchor"], mm["sent"], mm["understood"]), ("ARC-0002", "amount_due", "12382.00", "12832.00"))
        self.assertEqual((mm["handoff_file"], mm["handoff_from"], mm["receipt_file"], mm["receipt_by"]),
                         ("handoff_ARC-0002.json", "chunk-01", "receipt_ARC-0002.json", "consolidator"))
        rec = {r["record_id"]: r for r in out["records"]}
        self.assertEqual(rec["ARC-0002"]["amount_due"], "RECUPERARE")
        self.assertEqual(rec["ARC-0001"]["amount_due"], "12381.00")  # no false block

    def test_missing_receipt_is_a_mismatch(self):
        d, st = _fanout("s6-missing")
        out = s6.run(st, d, d / "06.json", fault_injection={"drop_receipt": ["ARC-0003"]})
        self.assertEqual(out["sentinel"]["release"], "BLOCKED")
        self.assertEqual(out["sentinel"]["mismatches"][0]["understood"], "(no receipt)")

    def test_single_backslashes_are_repaired_and_logged(self):
        d, st = _fanout("s6-backslash", bad_backslash=True)
        out = s6.run(st, d, d / "06.json")
        self.assertEqual(out["sentinel"]["release"], "OK")
        self.assertEqual(out["sentinel"]["json_repairs"][0]["file"], "handoff_ARC-0001.json")

    def test_dissent_nature_on_receipts(self):
        d, st = _fanout("s6-dissent")
        out = s6.run(st, d, d / "06.json", fault_injection={"dissent": [{"record_id": "ARC-0001",
                                                                         "text": "Amount read as 12,831.00 on page 2"}]})
        self.assertEqual(out["dissent_natures"], {"none": 1, "note": 1, "dissent": 1})
        self.assertEqual(out["disputes"], [{"id": "ARC-0001", "nature": "dissent", "status": "open"}])

    def test_authorship_from_fields_not_file_name(self):
        """L5: a receipt stored under the sender's prefix is still the receiver's."""
        d = tmpdir("s6-authorship")
        p = d / "RCPT_chunk-07_ARC-0231.json"
        jsonio.write(p, {"id": "ARC-0231", "by": "consolidator", "dissent": "none"})
        self.assertEqual(s6.resolve_author(jsonio.read(p)), "consolidator")


if __name__ == "__main__":
    unittest.main()
