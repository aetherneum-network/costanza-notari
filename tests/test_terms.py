import datetime as dt
import json
import unittest

from tests._util import ROOT
from corpus import reference_terms as ref
from pipeline import terms
from pipeline.lib import tzrome

CAL = terms.Calendar(json.loads((ROOT / "rules" / "holidays.json").read_text(encoding="utf-8")))
TERMS = {t["doc_type"]: t for t in json.loads((ROOT / "rules" / "terms.json").read_text(encoding="utf-8"))["terms"]}


def rome(y, m, d, hh, mm):
    return tzrome.to_rome(tzrome.rome_local_to_utc(dt.datetime(y, m, d, hh, mm)))


class HandWorkedExamples(unittest.TestCase):
    """docs/TERMS.md - each line is an example worked by hand."""

    def due(self, doc_type, when, days=None):
        return terms.compute(CAL, TERMS[doc_type], when, days)["date"]

    def test_e1_precetto(self):
        self.assertEqual(self.due("atto_precetto", rome(2026, 10, 5, 10, 15)), "2026-10-15")

    def test_e2_decreto_crossing_august(self):
        self.assertEqual(self.due("decreto_ingiuntivo", rome(2026, 7, 20, 11, 0)), "2026-09-29")

    def test_e3_decreto_notified_in_august_then_saturday(self):
        self.assertEqual(self.due("decreto_ingiuntivo", rome(2026, 8, 10, 9, 0)), "2026-10-12")

    def test_e4_accertamento_60_with_suspension(self):
        self.assertEqual(self.due("avviso_accertamento", rome(2026, 6, 30, 16, 0)), "2026-09-29")

    def test_e5_e6_cartella_saturday_not_rolled_but_procedural_is(self):
        self.assertEqual(self.due("cartella_pagamento", rome(2026, 10, 6, 10, 0)), "2026-12-05")
        proc = {**TERMS["cartella_pagamento"], "saturday_rollover": True}
        self.assertEqual(terms.compute(CAL, proc, rome(2026, 10, 6, 10, 0))["date"], "2026-12-07")

    def test_e7_intimazione_immacolata(self):
        self.assertEqual(self.due("intimazione_pagamento", rome(2026, 12, 3, 10, 0)), "2026-12-09")

    def test_e8_pec_after_21(self):
        self.assertEqual(self.due("atto_precetto", rome(2026, 10, 9, 21, 30)), "2026-10-20")
        self.assertEqual(self.due("atto_precetto", rome(2026, 10, 9, 20, 59)), "2026-10-19")

    def test_e9_4_october_from_2026(self):
        self.assertEqual(self.due("cartella_pagamento", rome(2027, 8, 5, 10, 0)), "2027-10-05")

    def test_easter(self):
        self.assertEqual(terms.easter_sunday(2026), dt.date(2026, 4, 5))
        self.assertEqual(terms.easter_sunday(2027), dt.date(2027, 3, 28))
        self.assertTrue(CAL.is_holiday(dt.date(2027, 3, 29)))


class IndependentCrossCheck(unittest.TestCase):
    def test_arithmetic_equals_day_walker(self):
        """Every notification day Jun 2026 - Jun 2027 x every policy x several term lengths."""
        n = 0
        d = dt.date(2026, 6, 1)
        while d <= dt.date(2027, 6, 1):
            for days in (5, 10, 15, 20, 30, 40, 60, 90):
                for susp in (False, True):
                    for sat in (False, True):
                        a = terms.add_days(CAL, d, days, feriale_suspension=susp, saturday_rollover=sat)
                        b = ref.walk(d, days, susp, sat)
                        self.assertEqual(a, b, (d, days, susp, sat))
                        n += 1
            d += dt.timedelta(days=1)
        self.assertGreater(n, 11000)

    def test_holiday_tables_agree(self):
        d = dt.date(2025, 1, 1)
        while d <= dt.date(2028, 12, 31):
            self.assertEqual(CAL.is_holiday(d), ref.is_non_working(d), d)
            d += dt.timedelta(days=1)


if __name__ == "__main__":
    unittest.main()
