"""Regression tests for the safety nets added after the stress suites (see CHANGELOG 2.0.0).

Each one turns a would-be WRONG committed deadline into an honest RECUPERARE."""
import datetime as dt
import json
import unittest

from tests._util import ROOT
from pipeline import classify, deadlines as dl

CONFIG = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))
CTX = classify.build_context(CONFIG, dt.datetime.fromisoformat("2026-10-21T09:40:00+02:00"))


def record(text, subject="Comunicazione", sender="amministrazione@pec.officinelagorai.example",
           when="2026-10-06T10:00:00+02:00", transport="ok"):
    env = {"record_id": "ARC-T", "envelope": "t.eml", "sha256": "0" * 64,
           "daticert": {"mittente": sender, "data": when, "oggetto": subject},
           "inner": {"from_display": "Officine Lagorai S.r.l.", "from_addr": sender, "body": "", "subject": subject}}
    sig = {"transport": {"signature_integrity": transport},
           "documents": [{"name": "a.pdf", "signature_integrity": "not_signed"}]}
    txt = {"documents": [{"name": "a.pdf", "text": text, "status": "OK"}], "principal": "a.pdf", "text_status": "OK"}
    return classify.classify_record(env, sig, txt, CTX)


class SafetyNets(unittest.TestCase):
    def test_unknown_act_type_never_computes_a_term(self):
        """Blind stress ARC-0115: unknown type + '10 giorni' computed without the 21:00 rule -> 1 day off."""
        r = record("OFFICINE LAGORAI S.R.L.\nATTO NON RICONOSCIUTO\nSi intima di pagare entro il termine di dieci "
                   "giorni dalla notifica la somma di € 1.000,00.", when="2026-08-07T22:19:41+02:00")
        self.assertEqual(r["doc_type"], "RECUPERARE")
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("legal policy", r["recuperare_reasons"]["deadline"])

    def test_unparsed_term_phrase(self):
        r = record("OFFICINE LAGORAI S.R.L.\nDIFFIDA E MESSA IN MORA\nPagare entro e non oltre quindici giorni dal "
                   "ricevimento della presente la somma di € 1.000,00.")
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("could not be parsed", r["recuperare_reasons"]["deadline"])

    def test_date_in_unsupported_format_inside_a_term_clause(self):
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nSi comunica che il Giudice ha rinviato "
                   "l'udienza al 28-12-2026.", sender="contenzioso@civile.tribunale.example")
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("28-12-2026", r["recuperare_reasons"]["deadline"])

    def test_unreadable_invoice_date_does_not_raise_the_flag(self):
        self.assertEqual(dl.unparsed_date_like("fattura n. 208 del 14-04-2026, scaduta il 13-06-2026, insoluta."), [])

    def test_future_date_without_cue(self):
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nL'udienza si terrà il 12/11/2026 alle 9:30.",
                   sender="contenzioso@civile.tribunale.example")
        self.assertEqual(r["deadline"], "RECUPERARE")

    def test_nature_reference_survives_a_broken_transport_signature(self):
        r = record("TRIBUNALE DI ESEMPIO\nSENTENZA DI APERTURA DELLA LIQUIDAZIONE GIUDIZIALE\nIl Tribunale, udite le "
                   "parti all'udienza del 17/06/2026; dichiara aperta la liquidazione giudiziale.",
                   sender="crisi.impresa@civile.tribunale.example", when="2026-07-01T10:00:00+02:00", transport="failed")
        self.assertEqual([d["nature"] for d in r["dates"]], ["historical"])  # a past hearing is not actionable
        self.assertEqual(r["deadline"], "RECUPERARE")  # computed term: timestamp untrusted

    def test_edition_ref_does_not_depend_on_its_date_format(self):
        r = record("AGENZIA ESEMPIO RISCOSSIONE\nPIANO DI RATEIZZAZIONE\nRif. atto: EX-2163 del 02-10-2026\n"
                   "Importo della rata: € 1.020,00.\nLa prima rata scade il 30/11/2026.",
                   sender="notifica.cartelle@pec.agenzia-riscossione.example")
        self.assertEqual((r["edition_ref"], r["edition_date"]), ("EX-2163", None))


if __name__ == "__main__":
    unittest.main()
