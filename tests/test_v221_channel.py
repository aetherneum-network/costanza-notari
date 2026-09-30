"""v2.2.1 - a third party's address is never the counterparty channel (CHANGELOG 2.2.1).

Inherited from v2.0: the sender's own PEC was always a channel candidate and a third-party sender (a garnishee
bank, a lawyer, a gateway, a court registry) only lost 30 points for it. When a token of the counterparty's
name happened to sit inside the sender's domain, the sender's PEC reached the accept threshold and was
committed as the counterparty's channel - a never-event. Found by the evaluator on blind seeds 20261006 and
20261007; the pack's own suites never held the triggering combination.

The fix is the ordered table ``channel_sender_side`` in ``rules/attribution.json`` (first match wins, the
exception on top), read by ``attribution.sender_side_rule`` and applied in ``attribution.contact_channel``:

  1. the table itself: inline tests, order, cross-check with the other sender lists  SenderSideTable
  2. third-party senders, on wording written here                                    ThirdPartySender
  3. ordinary senders (the counterparty itself) are unchanged                         OrdinarySender
  4. a missing or broken table abstains, for every sender class                       FailClosed
  5. never-event: adversarial attempts to commit a third party's address              NeverEvent
  6. end to end through classify_record                                               EndToEnd

Every name and address below is fictitious and written for these tests (``.example`` domains).
"""
import copy
import json
import unittest
from unittest import mock

from tests._records import record
from tests._util import ROOT
from pipeline import attribution as attr, entities as ent

CONFIG = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))
DEBTOR = ent.Debtor(CONFIG["debtor"])
RULES = json.loads((ROOT / "rules" / "attribution.json").read_text(encoding="utf-8"))
SENDER_CLASSES = json.loads((ROOT / "rules" / "sender_class.json").read_text(encoding="utf-8"))

# Every class the pipeline can assign (short-circuits, scored classes, the corporate fallback, no class) ...
PIPELINE_CLASSES = ({sc["then"]["class"] for sc in SENDER_CLASSES["short_circuits"]}
                    | set(SENDER_CLASSES["classes"]) | {"CORPORATE_PEC", "RECUPERARE"})
# ... and every class the generator writes in its gold (corpus/templates.py: lawyer_act via _lawyer_bodies,
# bank_third_party, bank_corporate, court_act, public_act, company_act, target_forward).
GENERATOR_CLASSES = {"LAWYER", "TRANSMIT", "BANK_THIRD_PARTY", "BANK_CORPORATE", "COURT", "CORPORATE_PEC", "TARGET"}
SELF_SENDERS = {"CORPORATE_PEC", "BANK_CORPORATE"}
THIRD_PARTY = sorted((PIPELINE_CLASSES | GENERATOR_CLASSES) - SELF_SENDERS) + ["NOTARY_NOT_YET_KNOWN"]

BANK = "segreteria@pec.bancavalmarina.example"          # the garnishee: 'marina' sits inside its domain
PARTY = "ALFA MARINA S.R.L."                             # the attaching creditor
PARTY_PEC = "crediti@pec.alfamarina.example"


def channel(sender_class, sender=BANK, text="", party=PARTY, rules=None, from_addr=None, reply_to=None, body=""):
    cands = attr.collect_candidates(sender, from_addr or sender, reply_to, body, text)
    return attr.contact_channel(party, cands, sender, sender_class, DEBTOR, rules)


def org(addr):
    return attr._org_domain(addr.partition("@")[2], RULES["channel"]["sender_side_domain_strip_regex"])


class SenderSideTable(unittest.TestCase):
    def test_inline_rules_pass(self):
        self.assertEqual(attr.run_sender_side_tests(DEBTOR), [])

    def test_order_exception_on_top_catch_all_last(self):
        rows = RULES["channel_sender_side"]
        self.assertEqual([r["id"] for r in rows], ["CS-001", "CS-002", "CS-003"])
        self.assertEqual(rows[0]["then"]["sender_side"], "admit")
        self.assertEqual(rows[-1]["when"], {"any": True})
        self.assertEqual(rows[-1]["then"]["sender_side"], "exclude")
        for r in rows:
            self.assertTrue(r["rationale"] and r["tests"], r["id"])

    def test_the_three_lists_of_self_senders_agree(self):
        self.assertEqual(set(RULES["channel_sender_side"][0]["when"]["sender_class_in"]), SELF_SENDERS)
        self.assertEqual(set(RULES["channel"]["party_sends_itself_for"]), SELF_SENDERS)
        self.assertEqual(set(RULES["party_is_sender_for"]), SELF_SENDERS)

    def test_every_sender_class_is_decided_and_only_self_senders_are_admitted(self):
        self.assertEqual(GENERATOR_CLASSES - PIPELINE_CLASSES, set(), "a generator class the pipeline never assigns")
        for sc in sorted(PIPELINE_CLASSES | GENERATOR_CLASSES) + ["NOTARY_NOT_YET_KNOWN"]:
            row = attr.sender_side_rule(sc)
            self.assertIsNotNone(row, sc)
            self.assertEqual(row["then"]["sender_side"], "admit" if sc in SELF_SENDERS else "exclude", sc)
        self.assertEqual(attr.sender_side_rule("BANK_THIRD_PARTY")["id"], "CS-002")
        self.assertEqual(attr.sender_side_rule("RECUPERARE")["id"], "CS-003")

    def test_organisational_domain(self):
        s = RULES["channel"]["sender_side_domain_strip_regex"]
        self.assertEqual(attr._org_domain("pec.bancavalmarina.example", s), "bancavalmarina.example")
        self.assertEqual(attr._org_domain("bancavalmarina.example", s), "bancavalmarina.example")
        self.assertEqual(attr._org_domain("pec.it", s), "pec.it")          # never reduced to a bare TLD
        self.assertTrue(attr._same_org("filiale.bancavalmarina.example", "bancavalmarina.example"))
        self.assertFalse(attr._same_org("alfamarina.example", "bancavalmarina.example"))
        self.assertFalse(attr._same_org("", "bancavalmarina.example"))


class ThirdPartySender(unittest.TestCase):
    """For a sender that is not the counterparty the channel is read from the text, or RECUPERARE."""

    def test_no_counterparty_address_in_the_text_abstains_for_every_third_party_class(self):
        text = f"Procedura promossa da {PARTY}, con atto notificato alla scrivente."
        for sc in THIRD_PARTY:
            ch = channel(sc, text=text)
            self.assertEqual(ch["value"], "RECUPERARE", sc)
            self.assertIn(BANK, ch.get("excluded", []), sc)

    def test_the_counterparty_address_stated_in_the_text_is_read(self):
        text = f"Procedura promossa da {PARTY}, con sede in Esempio, PEC {PARTY_PEC}, contro il debitore."
        for sc in THIRD_PARTY:
            ch = channel(sc, text=text)
            self.assertEqual(ch["value"], PARTY_PEC, sc)
            self.assertEqual(ch["basis"].split(";")[0], "score", sc)

    def test_two_counterparty_like_addresses_within_the_margin_abstain(self):
        text = (f"Creditore procedente {PARTY}, PEC {PARTY_PEC}; "
                "sede secondaria: amministrazione@pec.alfamarina-nord.example")
        self.assertEqual(channel("BANK_THIRD_PARTY", text=text)["value"], "RECUPERARE")

    def test_an_address_without_the_party_name_is_never_committed_even_if_weights_change(self):
        rules = copy.deepcopy(RULES)
        rules["channel"]["weights"]["declared_contact"] = 200     # would lift any declared address over 75
        text = "Per le comunicazioni: ufficio.esecuzioni@pec.studioterzi.example"
        ch = channel("BANK_THIRD_PARTY", text=text, rules=rules)
        self.assertEqual(ch["value"], "RECUPERARE")
        self.assertGreaterEqual(ch["scored"][0]["score"], 75)     # it did score: the name net refused it
        admitted = channel("CORPORATE_PEC", sender="info@pec.ditta-terza.example", text=text, rules=rules)
        self.assertEqual(admitted["value"], "ufficio.esecuzioni@pec.studioterzi.example")  # CS-001 has no such net

    def test_from_and_reply_to_of_the_envelope_are_sender_side_too(self):
        ch = channel("TRANSMIT", sender="invii@pec.gatewaymarina.example",
                     from_addr="uscita@pec.gatewaymarina.example", reply_to="assistenza@alfamarina-servizi.example")
        self.assertEqual(ch["value"], "RECUPERARE")
        self.assertEqual(set(ch["excluded"]), {"invii@pec.gatewaymarina.example", "uscita@pec.gatewaymarina.example",
                                               "assistenza@alfamarina-servizi.example"})

    def test_a_subdomain_of_the_sender_is_the_sender(self):
        text = "Per le comunicazioni: segreteria@esecuzioni.bancavalmarina.example"
        self.assertEqual(channel("BANK_THIRD_PARTY", text=text)["value"], "RECUPERARE")

    def test_the_debtor_stays_excluded_first(self):
        pec = CONFIG["debtor"]["pec"]
        pec = (pec[0] if isinstance(pec, list) else pec).lower()
        text = f"Somme accantonate sui rapporti di Fornace Aurelia, PEC {pec}"
        ch = channel("BANK_THIRD_PARTY", text=text)
        self.assertEqual(ch["value"], "RECUPERARE")
        self.assertNotIn(pec, [x["addr"] for x in ch["scored"]])
        self.assertNotIn(pec, ch["excluded"])          # removed by the debtor exclusion, before the table


class OrdinarySender(unittest.TestCase):
    """The counterparty writing for itself: v2.2 behaviour, scores unchanged."""

    def test_own_pec_committed_with_the_v22_score(self):
        ch = channel("BANK_CORPORATE", sender="direzione.crediti@pec.bancaboreale.example", party="BANCA BOREALE S.P.A.")
        self.assertEqual(ch["value"], "direzione.crediti@pec.bancaboreale.example")
        self.assertEqual(ch["scored"][0]["score"], 60 + 15 + 30)   # domain + corporate local part + PEC
        self.assertEqual(ch["excluded"], [])
        self.assertEqual(ch["sender_rule"], "CS-001")
        self.assertEqual(ch["basis"], "score")

    def test_declared_contact_of_a_public_body_still_wins(self):
        ch = channel("CORPORATE_PEC", sender="notifiche@pec.mulinibrenta.example", party="MULINI BRENTA S.R.L.",
                     text="Per le comunicazioni: ufficio.legale@pec.mulinibrenta.example")
        self.assertEqual(ch["value"], "ufficio.legale@pec.mulinibrenta.example")
        self.assertEqual({x["addr"]: x["score"] for x in ch["scored"]},
                         {"ufficio.legale@pec.mulinibrenta.example": 60 + 15 + 30 + 20,
                          "notifiche@pec.mulinibrenta.example": 60 + 30})

    def test_party_unknown_is_still_decided_before_the_table(self):
        self.assertEqual(channel("CORPORATE_PEC", party="RECUPERARE")["basis"], "party unknown")


class FailClosed(unittest.TestCase):
    """A missing or broken table -> RECUPERARE for every class, the admitted ones included."""

    def _broken(self):
        variants = []
        r = copy.deepcopy(RULES); del r["channel_sender_side"]; variants.append(("missing table", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"] = []; variants.append(("empty table", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"] = {"CS-001": "admit"}; variants.append(("not a list", r))
        r = copy.deepcopy(RULES); del r["channel_sender_side"][1]["id"]; variants.append(("row without id", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"][2]["id"] = "CS-001"; variants.append(("duplicate id", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"][1]["when"] = {"doc_type_in": ["x"]}
        variants.append(("unknown condition", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"][2]["when"] = {"any": False}; variants.append(("any false", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"][0]["when"]["sender_class_in"] = "CORPORATE_PEC"
        variants.append(("class list not a list", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"][1]["then"]["sender_side"] = "penalise"
        variants.append(("unknown verdict", r))
        r = copy.deepcopy(RULES); r["channel_sender_side"][1]["then"]["body_address_needs_party_name"] = "yes"
        variants.append(("net flag not a bool", r))
        r = copy.deepcopy(RULES); del r["channel"]["sender_side_domain_strip_regex"]; variants.append(("no normaliser", r))
        r = copy.deepcopy(RULES); r["channel"]["sender_side_domain_strip_regex"] = "(pec"; variants.append(("bad regex", r))
        return variants

    def test_broken_table_abstains_for_every_class(self):
        text = f"Procedura promossa da {PARTY}, PEC {PARTY_PEC}."
        for why, rules in self._broken():
            for sc in sorted(PIPELINE_CLASSES | GENERATOR_CLASSES):
                ch = channel(sc, text=text, rules=rules)
                self.assertEqual(ch["value"], "RECUPERARE", (why, sc))
                self.assertIn("fail closed", ch["basis"], (why, sc))

    def test_no_matching_row_abstains(self):
        rules = copy.deepcopy(RULES)
        rules["channel_sender_side"] = rules["channel_sender_side"][:2]          # no catch-all
        self.assertEqual(channel("NOTARY_NOT_YET_KNOWN", text=f"PEC {PARTY_PEC}", rules=rules)["value"], "RECUPERARE")
        self.assertEqual(channel("BANK_THIRD_PARTY", text=f"PEC {PARTY_PEC}", rules=rules)["value"], PARTY_PEC)

    def test_default_rules_come_from_attribution_rules(self):
        with mock.patch.object(attr, "attribution_rules", return_value=self._broken()[0][1]):
            self.assertIsNone(attr.sender_side_rule("CORPORATE_PEC"))
            ch = attr.contact_channel(PARTY, attr.collect_candidates(BANK, BANK, None, "", ""), BANK,
                                      "CORPORATE_PEC", DEBTOR)
            self.assertEqual(ch["value"], "RECUPERARE")


class NeverEvent(unittest.TestCase):
    """Try hard to make the pack commit a third party's address as the counterparty channel."""

    SENDERS = ("segreteria@pec.bancavalmarina.example",            # corporate local part + party token in domain
               "marina@pec.bancavalmarina.example",                # party token in local part AND domain
               "alfa.marina@pec.alfamarina-legale.example",        # the party's whole name, but the lawyer's box
               "info@alfamarina.example",                          # looks exactly like the party's own address
               "crediti@pec.marinaservizi.example")
    TEXTS = ("",
             "Per le comunicazioni: {sibling}",
             "Rispondere esclusivamente a {sender}",
             "Indirizzo PEC dedicato: {sub}",
             "Per le comunicazioni: {sender} - {sibling} - {sub}")

    def test_no_third_party_address_is_ever_committed(self):
        for sc in THIRD_PARTY:
            for sender in self.SENDERS:
                lp, dom = sender.split("@")
                base = org(sender)
                for tpl in self.TEXTS:
                    text = tpl.format(sender=sender, sibling=f"ufficio.crediti@{dom}", sub=f"marina@uffici.{base}")
                    ch = channel(sc, sender=sender, text=text)
                    v = ch["value"]
                    self.assertTrue(v == "RECUPERARE" or not attr._same_org(org(v), base), (sc, sender, text, v))
                    self.assertEqual(v, "RECUPERARE", (sc, sender, text))   # nothing else is stated: abstain

    def test_the_old_penalty_alone_would_have_committed_these(self):
        """The shape of the evaluator's finding, re-built here: without the table the sender scores 75."""
        ch = channel("BANK_THIRD_PARTY")
        self.assertEqual(ch["value"], "RECUPERARE")
        w = RULES["channel"]["weights"]
        self.assertEqual(w["domain_keyword"] + w["corporate_localpart"] + w["corporate_pec"]
                         + w["same_domain_as_sender"], RULES["channel"]["thresholds"]["accept"])


GARNISHEE = ("BANCA VALMARINA S.P.A.\nUfficio Pignoramenti\n\n"
             "Oggetto: dichiarazione del terzo ai sensi dell'art. 547 c.p.c.\nRif. pratica: PR-AM-0007\n\n"
             "La scrivente Banca Valmarina S.p.A., in qualità di terzo pignorato nella procedura promossa da "
             "ALFA MARINA S.R.L.{stated}, con atto notificato alla scrivente in data 14/09/2026, comunica che sui "
             "rapporti intestati a FORNACE AURELIA S.R.L. sono state accantonate somme pari a € 2.480,00.\n"
             "Esempio, 22/09/2026\nBANCA VALMARINA S.P.A. - Ufficio Pignoramenti")


class EndToEnd(unittest.TestCase):
    """Through classify_record: sender class, party, author and channel together."""

    def _garnishee(self, stated=""):
        return record(GARNISHEE.format(stated=stated), subject="Dichiarazione del terzo - art. 547 c.p.c.",
                      sender=BANK, display="Banca Valmarina S.p.A.",
                      body="Si trasmette in allegato la comunicazione in oggetto.")

    def test_garnishee_bank_without_creditor_address(self):
        r = self._garnishee()
        self.assertEqual(r["sender_class"], "BANK_THIRD_PARTY")
        self.assertEqual(r["doc_type"], "pignoramento_presso_terzi")
        self.assertEqual(r["party_entity"], PARTY)
        self.assertEqual(r["author_entity"], "BANCA VALMARINA S.P.A.")
        self.assertEqual(r["counterparty_channel"], "RECUPERARE")
        self.assertIn("counterparty_channel", r["recuperare_fields"])
        self.assertIn("CS-002", r["rule_trace"]["counterparty_channel"])

    def test_garnishee_bank_stating_the_creditor_pec(self):
        r = self._garnishee(stated=f", con sede in Esempio, PEC {PARTY_PEC}")
        self.assertEqual(r["counterparty_channel"], PARTY_PEC)
        self.assertNotIn("counterparty_channel", r["recuperare_fields"])

    def test_bank_writing_for_itself_is_unchanged(self):
        text = ("BANCA VALMARINA S.P.A.\nDirezione Crediti\n\nSOLLECITO DI PAGAMENTO\nRif. pratica: PR-BV-0003\n\n"
                "Spett.le FORNACE AURELIA S.R.L.,\nVi ricordiamo che la rata del finanziamento n. SYN-FIN-0003, "
                "scaduta il 02/09/2026, per un importo di € 3.100,00, risulta ancora insoluta, con conseguente "
                "saldo debitore del conto di appoggio.\n"
                "Esempio, 22/09/2026\nBANCA VALMARINA S.P.A. - Direzione Crediti")
        r = record(text, subject="Sollecito di pagamento", sender=BANK, display="Banca Valmarina S.p.A.",
                   body="Si trasmette in allegato la comunicazione in oggetto.")
        self.assertEqual(r["sender_class"], "BANK_CORPORATE")
        self.assertEqual(r["party_entity"], "BANCA VALMARINA S.P.A.")
        self.assertEqual(r["counterparty_channel"], BANK)


if __name__ == "__main__":
    unittest.main()
