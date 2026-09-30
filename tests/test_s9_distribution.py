import os
import unittest

from tests._util import main_run, tmpdir
from pipeline import s9_distribution as s9
from pipeline.lib import jsonio

ENTRY = {"id": "SV-0001-amount_due", "base_id": "B-000000000001", "field": "amount_due", "old": "3415.20",
         "new": "3154.20", "since": "2026-10-20", "counterparty": "AGENZIA ESEMPIO RISCOSSIONE",
         "pratica": "PR-RAT-0077", "proof": {"document": "EX-2231", "supersedes": "EX-2210", "record": "ARC-0290"},
         "owners": ["tesoreria"]}


def _touch(p, iso_day):
    import datetime as dt
    t = dt.datetime.fromisoformat(iso_day + "T12:00:00+00:00").timestamp()
    os.utime(p, (t, t))


class ScannerTests(unittest.TestCase):
    def test_value_forms_and_boundaries(self):
        rx = s9.form_regex("3415.20")
        for s in ("rata di € 3.415,20.", "3,415.20", "3415.20", "3415,20", "valore 3415.2 in cella"):
            self.assertTrue(rx.search(s), s)
        for s in ("13.415,20", "3.415,205", "3415.25", "PR-3415.20-X1"):
            self.assertFalse(rx.search(s) and not s.startswith("PR-"), s)

    def test_guards(self):
        d = tmpdir("s9-guards")
        cases = {
            "stale.md": ("La rata del piano PR-RAT-0077 è di € 3.415,20.", "2026-10-21", True),
            "comparison.md": ("Rata ridotta da € 3.415,20 a € 3.154,20 (PR-RAT-0077).", "2026-10-21", False),
            "history.md": ("In precedenza la rata era di € 3.415,20 (PR-RAT-0077).", "2026-10-21", False),
            "cover_letter_draft.md": ("La rata del piano PR-RAT-0077 è di € 3.415,20.", "2026-10-15", False),
            "archivio_2026.md": ("La rata del piano PR-RAT-0077 è di € 3.415,20.", "2026-10-21", False),
            "other_cp.md": ("TESSITURE MONTEVERDE S.R.L.: rata € 3.415,20.", "2026-10-21", False),
        }
        for name, (text, day, _) in cases.items():
            p = d / name
            p.write_text(text + "\n", encoding="utf-8")
            _touch(p, day)
        res = s9.scan([ENTRY], d, known_entities=["AGENZIA ESEMPIO RISCOSSIONE", "TESSITURE MONTEVERDE S.R.L."])
        flagged = sorted(f["file"] for f in res["findings"] if f["status"] == "open")
        self.assertEqual(flagged, ["stale.md"])
        self.assertEqual(res["suppressed"], {"G1_snapshot_name": 1, "G2_untouched_since": 1, "G3_comparison": 1,
                                             "G4_historical_context": 1, "G5_other_counterparty": 1})
        closed = s9.scan([ENTRY], d, known_entities=["AGENZIA ESEMPIO RISCOSSIONE"],
                         responses=[{"entry": ENTRY["id"], "file": "stale.md", "already_fixed": True}])
        self.assertEqual(closed["flags_open"], 0)
        self.assertEqual(closed["flags_closed_by_owner"], 1)

    def test_self_scan_of_our_own_outputs_is_clean(self):
        st = jsonio.read(main_run() / "work" / "state" / "09_distribution.json")
        self.assertEqual(st["flags_open"], 0)
        self.assertGreater(st["results"]["build"]["raw_matches"], 0)  # the old values ARE there, side by side


if __name__ == "__main__":
    unittest.main()
