import datetime as dt
import json
import unittest

from tests._util import ROOT, ensure_corpus, main_run
from pipeline import attribution as attr, deadlines as dl, entities as ent
from pipeline.lib import jsonio

CONFIG = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))
DEBTOR = ent.Debtor(CONFIG["debtor"])


class Canonical(unittest.TestCase):
    def test_normalisation_and_aliases(self):
        self.assertEqual(ent.canonical("Officine Lagorai s.r.l."), "OFFICINE LAGORAI S.R.L.")
        self.assertEqual(ent.canonical("Avv. Ilaria Moscardini"), "ILARIA MOSCARDINI (AVV.)")
        self.assertEqual(ent.canonical("Società Agricola Valle dell'Èrto S.S."), "SOCIETÀ AGRICOLA VALLE DELL’ÈRTO S.S.")
        self.assertEqual(ent.canonical("Cooperativa Sentiero Verde soc. coop."), "COOPERATIVA SENTIERO VERDE SOC. COOP.")
        self.assertEqual(ent.match_key("ALFA S.R.L."), ent.match_key("Alfa Srl"))
        d = ent.EntityDictionary()
        a = d.resolve("OFFICINE LAGORAI S.R.L.")
        b = d.resolve("Officine Lagorai srl")
        self.assertEqual(a, b)
        self.assertEqual(d.entries[a]["aliases_seen"], ["Officine Lagorai srl"])


class AuthorTransmitterParty(unittest.TestCase):
    """L5: author, transmitter and party are distinct and never collapsed."""
    TEXT = ("STUDIO LEGALE MOSCARDINI\n\nATTO DI PRECETTO\nRif. pratica: PR-OL-0001\n"
            "Per conto e nell'interesse di OFFICINE LAGORAI S.R.L., con sede in Esempio, PEC "
            "crediti@pec.officinelagorai.example, rappresentata e difesa dall'Avv. Ilaria Moscardini,\n"
            "Esempio, 01/10/2026\nAvv. Ilaria Moscardini")
    BODY = ("Messaggio trasmesso tramite il servizio di notifica di Servizi Notifiche Digitali Esempio S.p.A. per "
            "conto dell'Avv. Ilaria Moscardini.")

    def test_gateway_lawyer_creditor(self):
        sc = attr.classify_sender("notifiche@pec.notifichedigitali.example", "Servizi Notifiche Digitali Esempio S.p.A.",
                                  self.BODY + self.TEXT, DEBTOR)
        self.assertEqual(sc["class"], "TRANSMIT")
        tr = attr.transmitter_entity(sc["class"], "Servizi Notifiche Digitali Esempio S.p.A.",
                                     "notifiche@pec.notifichedigitali.example", DEBTOR)
        au = attr.author_entity(self.TEXT, None, DEBTOR)
        pa = attr.party_entity(self.TEXT + self.BODY, sc["class"], au["value"], tr["value"], DEBTOR)
        self.assertEqual(tr["value"], "SERVIZI NOTIFICHE DIGITALI ESEMPIO S.P.A.")
        self.assertEqual(au["value"], "ILARIA MOSCARDINI (AVV.)")
        self.assertEqual(pa["value"], "OFFICINE LAGORAI S.R.L.")
        self.assertEqual(len({tr["value"], au["value"], pa["value"]}), 3)
        cands = attr.collect_candidates("notifiche@pec.notifichedigitali.example", None, None, self.BODY, self.TEXT)
        ch = attr.contact_channel(pa["value"], cands, "notifiche@pec.notifichedigitali.example", "TRANSMIT", DEBTOR)
        self.assertEqual(ch["value"], "crediti@pec.officinelagorai.example")
        scores = {x["addr"]: x["score"] for x in ch["scored"]}
        self.assertEqual(scores["crediti@pec.officinelagorai.example"], 60 + 15 + 30)   # domain + corporate + PEC
        # v2.2.1: the gateway is a third party (CS-002); until v2.2 its own address was scored 30 - 30 = 0.
        self.assertNotIn("notifiche@pec.notifichedigitali.example", scores)
        self.assertEqual(ch["excluded"], ["notifiche@pec.notifichedigitali.example"])
        self.assertEqual(ch["sender_rule"], "CS-002")


class DebtorExclusion(unittest.TestCase):
    def test_debtor_named_as_party_is_rejected_structurally(self):
        pa = attr.party_entity("Documento trasmesso nell'interesse di FORNACE AURELIA S.R.L., per la conservazione.",
                               "TARGET", "RECUPERARE", "@DEBTOR", DEBTOR)
        self.assertEqual(pa["value"], "RECUPERARE")
        self.assertEqual(pa["rejected"][0]["why"], "debtor exclusion")

    def test_debtor_channel_never_returned_even_if_it_scores(self):
        cands = [{"addr": "amministrazione@pec.fornaceaurelia.example", "context": "per le comunicazioni:", "source": "t"}]
        ch = attr.contact_channel("FORNACE AURELIA S.R.L. TRAP", cands, "x@pec.other.example", "CORPORATE_PEC", DEBTOR)
        self.assertEqual(ch["value"], "RECUPERARE")

    def test_debtor_transmitter_becomes_sentinel(self):
        tr = attr.transmitter_entity("TARGET", "Fornace Aurelia S.r.l. - Protocollo", "protocollo@pec.fornaceaurelia.example", DEBTOR)
        self.assertEqual(tr["value"], ent.DEBTOR_SENTINEL)

    def test_invariant_fails_the_run(self):
        with self.assertRaises(AssertionError):
            attr.assert_debtor_excluded([{"record_id": "X", "party_entity": "Fornace Aurelia srl"}], DEBTOR)


class DeadlineNatures(unittest.TestCase):
    def test_recital_vs_actionable(self):
        text = ("premesso che con decreto emesso il 12/03/2026 e il pagamento doveva avvenire entro il 30/06/2026; "
                "CITA a comparire all'udienza del 17/11/2026 ore 9:30. Il termine originariamente fissato al "
                "25/10/2026 deve intendersi superato. Qualora entro il 15/12/2026 non pervenga il pagamento, si procederà.")
        found = dl.find_dates(text)
        natures = [dl.classify_nature(f["before"], f["after"], f["date"], "2026-10-02")[0] for f in found]
        self.assertEqual(natures, ["historical", "historical", "actionable", "historical", "conditional"])

    def test_relative_terms(self):
        r = dl.relative_terms("Si intima di pagare entro il termine di dieci giorni dalla notifica. "
                              "Qualora entro 15 giorni dalla notifica non si provveda...")
        self.assertEqual([(x["days"], x["conditional"]) for x in r], [(10, False), (15, True)])

    def test_driving_deadline(self):
        dls = [{"date": "2026-10-01", "nature": "computed"}, {"date": "2026-11-17", "nature": "actionable"},
               {"date": "2026-12-01", "nature": "computed"}]
        self.assertEqual(dl.driving_deadline(dls, dt.date(2026, 10, 21))["date"], "2026-11-17")
        self.assertEqual(dl.driving_deadline(dls[:1], dt.date(2026, 10, 21))["status"], "expired")


class FanOutOnCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpus()
        cls.base = main_run()

    def test_chunks_of_forty_and_handoffs_with_anchors(self):
        st = jsonio.read(self.base / "work" / "state" / "05_classification.json")
        self.assertEqual([c["records"] for c in st["chunks"]], [40] * 7 + [20])
        h = jsonio.read(self.base / "work" / "fanout" / "handoffs" / "handoff_ARC-0001.json")
        self.assertEqual((h["from"], h["to"]), ("chunk-01", "consolidator"))
        self.assertTrue(1 <= len(h["anchors"]) <= 5)
        self.assertFalse(st["llm"]["enabled"])  # LLM disabled by default

    def test_no_record_has_the_debtor_as_party(self):
        st = jsonio.read(self.base / "work" / "state" / "06_consolidation.json")
        attr.assert_debtor_excluded(st["records"], DEBTOR)
        traps = [r for r in st["records"] if r["party_rejected"]]
        self.assertTrue(traps, "the corpus plants debtor-as-party traps")
        self.assertTrue(all(r["party_entity"] != "FORNACE AURELIA S.R.L." for r in traps))


if __name__ == "__main__":
    unittest.main()
