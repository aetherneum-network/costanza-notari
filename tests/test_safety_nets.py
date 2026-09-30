"""Regression tests for the safety nets added after the stress suites (see CHANGELOG 2.0.0).

Each one turns a would-be WRONG committed deadline into an honest RECUPERARE.

v2.1 note. Four of the inputs below were *unreadable for v2.0* and are *read* by v2.1 ("entro e non oltre N
giorni", dd-mm-yyyy, "l'udienza si terrà il"). Each net is still tested here, with an input that v2.1 cannot
read either; the old inputs moved to ``V21ReadsWhatV20AbstainedOn``, where they must now give the right date.
"""
import unittest

from tests._records import record
from pipeline import deadlines as dl

COURT = "contenzioso@civile.tribunale.example"
COLLECTION = "notifica.cartelle@pec.agenzia-riscossione.example"


class SafetyNets(unittest.TestCase):
    def test_unknown_act_type_never_computes_a_term(self):
        """Blind stress ARC-0115: unknown type + '10 giorni' computed without the 21:00 rule -> 1 day off."""
        r = record("OFFICINE LAGORAI S.R.L.\nATTO NON RICONOSCIUTO\nSi intima di pagare entro il termine di dieci "
                   "giorni dalla notifica la somma di € 1.000,00.", when="2026-08-07T22:19:41+02:00")
        self.assertEqual(r["doc_type"], "RECUPERARE")
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("legal policy", r["recuperare_reasons"]["deadline"])

    def test_unparsed_term_phrase(self):
        r = record("OFFICINE LAGORAI S.R.L.\nDIFFIDA E MESSA IN MORA\nPagare entro quindici giorni lavorativi dal "
                   "ricevimento della presente la somma di € 1.000,00.")
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("could not be parsed", r["recuperare_reasons"]["deadline"])
        self.assertIn("qualifier", r["recuperare_reasons"]["deadline"])  # v2.1 says which slot was not understood

    def test_date_in_unsupported_format_inside_a_term_clause(self):
        for raw in ("28-12-26", "28/12-2026", "31.11.2026"):  # two-digit year, mixed separators, impossible date
            r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nSi comunica che il Giudice ha rinviato "
                       f"l'udienza al {raw}.", sender=COURT)
            self.assertEqual(r["deadline"], "RECUPERARE", raw)
            self.assertIn(raw, r["recuperare_reasons"]["deadline"])

    def test_unreadable_invoice_date_does_not_raise_the_flag(self):
        self.assertEqual(dl.unparsed_date_like("fattura n. 208 del 14-04-2026, scaduta il 13-06-2026, insoluta."), [])
        self.assertEqual(dl.unparsed_date_like("fattura n. 208 del 14-04-26, scaduta il 13-06-26, insoluta."), [])

    def test_future_date_without_cue(self):
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nIl fascicolo sarà consultabile il 12/11/2026 "
                   "presso la cancelleria.", sender=COURT)
        self.assertEqual([d["nature"] for d in r["dates"]], ["RECUPERARE"])
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("without a recognisable cue", r["recuperare_reasons"]["deadline"])

    def test_nature_reference_survives_a_broken_transport_signature(self):
        r = record("TRIBUNALE DI ESEMPIO\nSENTENZA DI APERTURA DELLA LIQUIDAZIONE GIUDIZIALE\nIl Tribunale, udite le "
                   "parti all'udienza del 17/06/2026; dichiara aperta la liquidazione giudiziale.",
                   sender="crisi.impresa@civile.tribunale.example", when="2026-07-01T10:00:00+02:00", transport="failed")
        self.assertEqual([d["nature"] for d in r["dates"]], ["historical"])  # a past hearing is not actionable
        self.assertEqual(r["deadline"], "RECUPERARE")  # computed term: timestamp untrusted

    def test_edition_ref_does_not_depend_on_its_date_format(self):
        head = "AGENZIA ESEMPIO RISCOSSIONE\nPIANO DI RATEIZZAZIONE\nRif. atto: EX-2163 del "
        tail = "\nImporto della rata: € 1.020,00.\nLa prima rata scade il 30/11/2026."
        r = record(head + "02-10-26" + tail, sender=COLLECTION)
        self.assertEqual((r["edition_ref"], r["edition_date"]), ("EX-2163", None))
        r = record(head + "02-10-2026" + tail, sender=COLLECTION)  # v2.1 reads the dashed date
        self.assertEqual((r["edition_ref"], r["edition_date"]), ("EX-2163", "2026-10-02"))


class V21ReadsWhatV20AbstainedOn(unittest.TestCase):
    """The exact inputs of the v2.0 nets above. v2.1 must read them - and read them right."""

    def test_entro_e_non_oltre(self):
        r = record("OFFICINE LAGORAI S.R.L.\nDIFFIDA E MESSA IN MORA\nPagare entro e non oltre quindici giorni dal "
                   "ricevimento della presente la somma di € 1.000,00.")
        self.assertEqual((r["deadline"], r["deadline_nature"]), ("2026-10-21", "computed"))  # 6 Oct + 15 days
        self.assertNotIn("deadline", r["recuperare_fields"])

    def test_dashed_date(self):
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nSi comunica che il Giudice ha rinviato "
                   "l'udienza al 28-12-2026.", sender=COURT)
        self.assertEqual((r["deadline"], r["deadline_nature"]), ("2026-12-28", "actionable"))

    def test_hearing_that_will_be_held(self):
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nL'udienza si terrà il 12/11/2026 alle 9:30.",
                   sender=COURT)
        self.assertEqual((r["deadline"], r["rule_trace"]["deadline"]), ("2026-11-12", "N-008"))


if __name__ == "__main__":
    unittest.main()
