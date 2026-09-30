"""v2.2 - the merge (CHANGELOG 2.2.0): arm A is the base; the title reading and the amount reading of arm B
are ported into it as SECOND readers. Two readers that disagree abstain; one that commits while the other
has no opinion commits only under its own conditions. Null is honest; a guess is a defect.

  1. title-exclusive reader (arm B's DT-030..DT-032)        rules_engine title_* conditions, rules/doc_type.json
     - arm B's own tests, ported                            TitleExclusiveReader (first five tests)
     - the nets the merge adds (head position, inverting words, closed tail for a reminder)
  2. the two title readers side by side                     typeagree.resolve, rules/doc_type.json 'title_merge'
  3. the two amount readers side by side                    amounts.read_amount, rules/amounts.json 'agreement'
  4. end-to-end: a rewritten phrasing gives the SAME committed values as the canonical one (arm B's tests)

Everything below is wording written for these tests. The evaluation suites only hold the generator's own
eleven rewrites, which both arms already read: they cannot show that the port generalises. These tests can
show what the port reads and - more important - what it still refuses to read.
"""
import json
import unittest
from unittest import mock

from tests._records import CTX, record
from tests._util import ROOT
from pipeline import amounts, rules_engine, typeagree
from pipeline.rules_engine import RuleFile, title_lines

LAWYER = "avv.moscardini@pec.studiomoscardini.example"
AGENZIA = "notifica.cartelle@pec.agenzia-riscossione.example"
RULES = json.loads((ROOT / "rules" / "doc_type.json").read_text(encoding="utf-8"))
TITLE_RULES = ("DT-030", "DT-031", "DT-032")


class TitleExclusiveReader(unittest.TestCase):
    DT = RuleFile.load("doc_type.json")

    def apply(self, text, subject="Comunicazione"):
        then, rid = self.DT.apply({"text": text, "subject": subject, "body": "", "text_status": "OK"})
        return (then or {}).get("doc_type"), rid

    # --- arm B's tests (tests/test_v21_mechanisms.py, class TitleReading), ported ---------------------------
    def test_title_lines_are_the_all_caps_lines_of_the_heading(self):
        text = "STUDIO LEGALE\n\nATTO DI PRECETTO E INTIMAZIONE\nRif. pratica: PR-1\n\nPer conto di X\nINTIMA\nlettera di diffida"
        self.assertEqual(title_lines(text).splitlines(), ["STUDIO LEGALE", "ATTO DI PRECETTO E INTIMAZIONE", "INTIMA"])
        self.assertEqual(title_lines(""), "")
        self.assertEqual(title_lines("12345\n----"), "")  # no letter: not a title

    def test_wrapped_act_names(self):
        self.assertEqual(self.apply("STUDIO LEGALE\n\nATTO DI PRECETTO E INTIMAZIONE\nRif. pratica: PR-1", "Sollecito"),
                         ("atto_precetto", "DT-030"))
        self.assertEqual(self.apply("OFFICINE LAGORAI S.R.L.\n\nLETTERA DI DIFFIDA\nRif. pratica: PR-1", "Diffida e messa in mora"),
                         ("diffida_messa_in_mora", "DT-031"))
        self.assertEqual(self.apply("BANCA AURORA ESEMPIO S.P.A.\nDirezione Crediti\n\nATTO DI DIFFIDA E COSTITUZIONE IN MORA"),
                         ("diffida_messa_in_mora", "DT-031"))
        self.assertEqual(self.apply("CANTINE BELVEDERE S.P.A.\n\nLETTERA DI SOLLECITO\nRif. pratica: PR-1", "Sollecito"),
                         ("sollecito_pagamento", "DT-032"))

    def test_two_act_names_in_the_title_match_no_title_rule(self):
        for text in ("STUDIO LEGALE\n\nATTO DI PRECETTO E PIGNORAMENTO", "STUDIO LEGALE\n\nLETTERA DI DIFFIDA E PRECETTO",
                     "CANTINE BELVEDERE S.P.A.\n\nSOLLECITO E DIFFIDA", "STUDIO LEGALE\n\nATTO DI DIFFIDA E DI CITAZIONE"):
            doc, rid = self.apply(text)
            self.assertNotIn(rid, TITLE_RULES, text)
            self.assertIn(doc, (None, "RECUPERARE"), text)

    def test_act_name_in_running_text_or_lowercase_is_not_a_title(self):
        self.assertEqual(self.apply("STUDIO LEGALE\n\nSi trasmette l'atto di precetto e intimazione notificato ieri."), (None, None))
        self.assertEqual(self.apply("OFFICINE LAGORAI S.R.L.\n\nlettera di diffida\nRif. pratica: PR-1"), (None, None))

    def test_title_rules_do_not_pre_empt_the_exact_title_rules(self):
        self.assertEqual(self.apply("STUDIO LEGALE\n\nATTO DI PRECETTO\nRif. pratica: PR-1")[1], "DT-014")
        self.assertEqual(self.apply("OFFICINE LAGORAI S.R.L.\n\nDIFFIDA E MESSA IN MORA\nRif. pratica: PR-1")[1], "DT-022")

    # --- what the merge adds around the ported rules: all of it can only turn a reading into an abstention ---
    def test_the_rules_are_marked_as_a_reader_not_as_a_verdict(self):
        by_id = {r["id"]: r for r in RULES["rules"]}
        for rid in TITLE_RULES:
            self.assertEqual(by_id[rid]["then"]["basis"], "title_exclusive", rid)
        # nothing else may carry that basis: classify would treat it as a reader
        self.assertEqual([r["id"] for r in RULES["rules"] if r["then"].get("basis") == "title_exclusive"], list(TITLE_RULES))
        ids = [r["id"] for r in RULES["rules"]]
        self.assertLess(ids.index("DT-024"), ids.index("DT-030"))  # after every strict title rule
        self.assertLess(ids.index("DT-032"), ids.index("DT-050"))  # before the subject fallbacks

    def test_wording_of_my_own_that_is_read(self):
        for text, want in (
                ("STUDIO LEGALE MOSCARDINI\nNOTIFICAZIONE DI ATTO DI PRECETTO\nin forza", ("atto_precetto", "DT-030")),
                ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO IN RINNOVAZIONE\nin forza", ("atto_precetto", "DT-030")),
                ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO CAMBIARIO N. 3/2026\nin forza", ("atto_precetto", "DT-030")),
                ("OFFICINE LAGORAI S.R.L.\nATTO STRAGIUDIZIALE DI DIFFIDA\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nFORMALE MESSA IN MORA\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nOGGETTO: LETTERA DI DIFFIDA N. 44/2026\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nATTO DI DIFFIDA E CONTESTUALE MESSA IN MORA\nVi invitiamo",
                 ("diffida_messa_in_mora", "DT-031")),      # CONTESTUALE is not CONTESTAZIONE
                ("CANTINE BELVEDERE S.P.A.\nULTIMO SOLLECITO DI PAGAMENTO\nVi ricordiamo", ("sollecito_pagamento", "DT-032")),
                ("CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO PER FATTURE INSOLUTE\nVi ricordiamo",
                 ("sollecito_pagamento", "DT-032")),
                ("CANTINE BELVEDERE S.P.A.\nAVVISO DI SOLLECITO N. 2\nVi ricordiamo", ("sollecito_pagamento", "DT-032")),
                ("CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO - SALDO FATTURE\nVi ricordiamo",
                 ("sollecito_pagamento", "DT-032")),        # SALDO is not SALDATO
                ("OFFICINE LAGORAI S.R.L.\nRACCOMANDATA URGENTE DI DIFFIDA\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nINVITO E DIFFIDA\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nULTIMA DIFFIDA\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nULTIMO AVVISO E DIFFIDA\nVi invitiamo", ("diffida_messa_in_mora", "DT-031")),
                ("STUDIO LEGALE MOSCARDINI\nRINNOVAZIONE DELL'ATTO DI PRECETTO\nin forza", ("atto_precetto", "DT-030")),
                ("CANTINE BELVEDERE S.P.A.\nSECONDO SOLLECITO RATE ARRETRATE\nVi ricordiamo", ("sollecito_pagamento", "DT-032")),
                ("CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO - ULTIMO AVVISO PRIMA DELLE VIE LEGALI\nVi ricordiamo",
                 ("sollecito_pagamento", "DT-032")),
                ("OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA PER MANCATO PAGAMENTO\nVi invitiamo",
                 ("diffida_messa_in_mora", "DT-031")),      # PAGAMENTO is not PAGATO
                ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO NONCHE' INTIMAZIONE\nin forza",
                 ("atto_precetto", "DT-030"))):             # NONCHE' is not the negation NON
            self.assertEqual(self.apply(text), want, text)

    def test_the_act_must_be_the_head_of_its_title_line(self):
        for text in ("STUDIO LEGALE MOSCARDINI\nMEMORIA SULL'ATTO DI PRECETTO\nLa società",
                     "STUDIO LEGALE MOSCARDINI\nPARERE IN MERITO AD ATTO DI PRECETTO\nLa società",
                     "OFFICINE LAGORAI S.R.L.\nCHIARIMENTI SULLA MESSA IN MORA\nIn riferimento",
                     "OFFICINE LAGORAI S.R.L.\nSEGUITO DELLA NOSTRA DIFFIDA\nIn riferimento",
                     "OFFICINE LAGORAI S.R.L.\nPROPOSTA DI DEFINIZIONE DOPO LA COSTITUZIONE IN MORA\nIn riferimento",
                     "CANTINE BELVEDERE S.P.A.\nCHIARIMENTI SUL SOLLECITO\nIn riferimento",
                     # a noun naming another speech act is a head in its own right, not a frame word
                     "OFFICINE LAGORAI S.R.L.\nPROPOSTA E DIFFIDA\nVi invitiamo",
                     "OFFICINE LAGORAI S.R.L.\nRICHIESTA DI COSTITUZIONE IN MORA\nVi invitiamo",
                     "OFFICINE LAGORAI S.R.L.\nINVITO ALLA NEGOZIAZIONE ASSISTITA E DIFFIDA\nVi invitiamo",
                     "CANTINE BELVEDERE S.P.A.\nCOMUNICAZIONE PRIMA DEL SOLLECITO\nIn riferimento",  # PRIMA: tail word only
                     # the head is another family of arm A: left to the agreement reader
                     "AGENZIA ESEMPIO RISCOSSIONE\nINTIMAZIONE E DIFFIDA\nSi intima"):
            doc, rid = self.apply(text)
            self.assertNotIn(rid, TITLE_RULES, text)
            self.assertIsNone(doc, text)
        # the refusing line decides even if another title line names the act in head position
        doc, rid = self.apply("OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA\nSEGUITO DELLA NOSTRA DIFFIDA\nIn riferimento")
        self.assertNotIn(rid, TITLE_RULES)

    def test_an_inverting_word_anywhere_on_the_title_lines_is_a_veto(self):
        for text in ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO - RINUNCIA\nLa società",
                     "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO OPPOSTO\nLa società",
                     "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO N. 7/2026\nISTANZA DI SOSPENSIONE\nLa società",  # two lines
                     "STUDIO LEGALE MOSCARDINI\nRICORSO\nATTO DI PRECETTO N. 7/2026\nLa società",
                     "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA: REVOCA\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nATTO DI DIFFIDA (BOZZA)\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nATTO DI DIFFIDA - FAC-SIMILE\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nFORMALE MESSA IN MORA - RISCONTRO\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nATTO DI COSTITUZIONE IN MORA - CONTESTAZIONE\nCon la presente",
                     "CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO - ANNULLAMENTO\nCon la presente",
                     # the title says the thing demanded has been done, or denies / voids the act
                     "CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO - FATTURA SALDATA\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA - PAGAMENTO EFFETTUATO\nCon la presente",
                     "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO NULLO\nLa società",
                     "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO NON NOTIFICATO\nLa società"):
            doc, rid = self.apply(text)
            self.assertNotIn(rid, TITLE_RULES, text)
            self.assertIsNone(doc, text)

    def test_a_reminder_may_only_be_followed_by_payment_words(self):
        for text in ("CANTINE BELVEDERE S.P.A.\nSOLLECITO INVIO DOCUMENTAZIONE\nVi ricordiamo",
                     "CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO DI RISPOSTA\nVi ricordiamo",   # RISPOST: also inverting
                     "CANTINE BELVEDERE S.P.A.\nLETTERA DI SOLLECITO AD ADEMPIERE\nVi ricordiamo",
                     "CANTINE BELVEDERE S.P.A.\nSOLLECITO CONSEGNA MERCE\nVi ricordiamo"):
            doc, rid = self.apply(text)
            self.assertNotIn(rid, TITLE_RULES, text)
            self.assertIsNone(doc, text)

    def test_the_tail_of_a_precetto_or_diffida_line_may_not_describe_or_change_the_act(self):
        """ABOUT_TAIL / NOT_A_DEMAND_TAIL (rules/doc_type.json defs): looked for only after the act name, on its line."""
        for text in ("STUDIO LEGALE MOSCARDINI\nCOMUNICAZIONE ATTO DI PRECETTO PERVENUTO\nLa società",
                     "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO NOTIFICATO IL 3 OTTOBRE 2026 - DOMANDA DI RINVIO\nLa società",
                     "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO SCADUTO\nLa società",
                     "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA GIA' INVIATA - CHIARIMENTI\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA - RICHIESTA DI INCONTRO\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nATTO DI MESSA IN MORA DEL CREDITORE\nCon la presente",      # mora credendi
                     "ISPETTORATO ESEMPIO\nCOMUNICAZIONE DI DIFFIDA ACCERTATIVA\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA DAL PROSEGUIRE I LAVORI\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nATTO DI DIFFIDA E CONTESTUALE DISDETTA\nCon la presente",
                     "OFFICINE LAGORAI S.R.L.\nATTO DI DIFFIDA - RECESSO\nCon la presente"):
            doc, rid = self.apply(text)
            self.assertNotIn(rid, TITLE_RULES, text)
            self.assertIsNone(doc, text)
        for text, want in (
                # the same words on ANOTHER line (a letterhead) or before the act name do not count
                ("OFFICINE LAGORAI S.R.L.\nDIREZIONE AMMINISTRATIVA\nLETTERA DI DIFFIDA\nVi invitiamo",
                 ("diffida_messa_in_mora", "DT-031")),
                ("OFFICINE LAGORAI S.R.L.\nATTO DI DIFFIDA PER FATTURE SCADUTE\nVi invitiamo",
                 ("diffida_messa_in_mora", "DT-031")),      # SCADUT is a veto for the precetto only
                ("OFFICINE LAGORAI S.R.L.\nATTO DI COSTITUZIONE IN MORA EX ART. 1219 C.C.\nVi invitiamo",
                 ("diffida_messa_in_mora", "DT-031")),
                ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO IN RINNOVAZIONE\nin forza", ("atto_precetto", "DT-030")),
                ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO SU TITOLO ESECUTIVO GIUDIZIALE\nin forza",
                 ("atto_precetto", "DT-030"))):
            self.assertEqual(self.apply(text), want, text)

    def test_other_acts_under_the_names_arm_a_knows(self):
        for text in ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO E INGIUNZIONE DI PAGAMENTO\nin forza",
                     "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA E PROPOSTA DI DILAZIONE\nVi invitiamo",
                     "CANTINE BELVEDERE S.P.A.\nSOLLECITO E PIANO DI RATEAZIONE\nVi ricordiamo"):
            self.assertNotIn(self.apply(text)[1], TITLE_RULES, text)

    def test_the_frame_is_the_agreement_readers_frame_plus_a_few_words(self):
        """One list for both readers: the rule refers to it (@title_neutral_words), it does not copy it."""
        by_id = {r["id"]: r for r in self.DT.rules}
        for rid in TITLE_RULES:
            frame = set(by_id[rid]["when"]["title_before_words"])
            self.assertTrue(set(RULES["title_neutral_words"]) <= frame, rid)
            self.assertTrue(set(RULES["title_head_extra_words"]) <= frame, rid)
            self.assertNotIn("@title_neutral_words", frame)
            for p in by_id[rid]["when"]["title_not_matches"]:
                self.assertNotIn("{", p.replace("{0,", ""), rid)      # every {NAME} was resolved
        self.assertEqual(set(by_id["DT-032"]["when"]["title_after_words"]), set(RULES["title_sollecito_tail_words"]))
        # no act name and no inverting word may hide in a frame list
        inverting = rules_engine._rx(RULES["defs"]["INVERTING"])
        families = typeagree.compile_families(RULES)
        for key in ("title_neutral_words", "title_head_extra_words", "title_ordinal_words", "title_sollecito_tail_words"):
            for w in RULES[key]:
                self.assertIsNone(inverting.search(w), (key, w))
                self.assertFalse(any(f[2].search(w) for f in families.items), (key, w))


class RuleEngineTitleConditions(unittest.TestCase):
    def test_title_matches_and_not_matches(self):
        f = {"text": "STUDIO X\nATTO DI PRECETTO E PIGNORAMENTO\ntesto con diffida"}
        self.assertTrue(rules_engine.matches({"title_matches": r"\bPRECETTO\b"}, f))
        self.assertFalse(rules_engine.matches({"title_matches": r"\bDIFFIDA\b"}, f))           # running text
        self.assertFalse(rules_engine.matches({"title_matches": r"\bPRECETTO\b", "title_not_matches": r"\bPIGNORAMENTO\b"}, f))
        self.assertFalse(rules_engine.matches({"title_matches": r"\bPRECETTO\b",
                                               "title_not_matches": [r"\bCITAZIONE\b", r"\bPIGNORAMENTO\b"]}, f))
        self.assertTrue(rules_engine.matches({"title_matches": r"\bPRECETTO\b", "title_not_matches": [r"\bCITAZIONE\b"]}, f))

    def test_frame_words(self):
        when = {"title_matches": r"\bPRECETTO\b", "title_before_words": ["ATTO", "DI", "N"], "title_after_words": ["E", "INTIMAZIONE"]}
        ok = lambda line: rules_engine.matches(when, {"text": "STUDIO X\n" + line + "\ntesto"})
        self.assertTrue(ok("ATTO DI PRECETTO E INTIMAZIONE"))
        self.assertTrue(ok("ATTO N. 12/2026 DI PRECETTO"))            # a reference token is not a word
        self.assertFalse(ok("OPPOSIZIONE AD ATTO DI PRECETTO"))
        self.assertFalse(ok("ATTO DI PRECETTO E PIGNORAMENTO"))
        self.assertEqual(rules_engine.title_words("NOTIFICA DELL'ATTO N.12/2026 DI "), ["NOTIFICA", "DELL", "ATTO", "DI"])

    def test_frame_without_a_title_pattern_is_an_error_not_a_silent_pass(self):
        with self.assertRaises(KeyError):
            rules_engine.matches({"title_before_words": ["ATTO"]}, {"text": "ATTO DI PRECETTO"})

    def test_a_long_upper_case_line_is_a_paragraph_not_a_title(self):
        long_line = "ATTO DI PRECETTO " + "E ALTRE PAROLE " * 6                      # > 90 characters
        self.assertGreater(len(long_line.strip()), rules_engine.MAX_TITLE_LEN)
        self.assertEqual(title_lines("STUDIO X\n" + long_line), "STUDIO X")
        self.assertEqual(typeagree.title_lines("STUDIO X\n" + long_line), ["STUDIO X"])   # one definition for both readers

    def test_defs_and_list_references(self):
        data = {"defs": {"BAD": r"\bREVOC"}, "frame": ["ATTO", "DI"],
                "rules": [{"id": "X-1", "when": {"title_matches": r"\bPRECETTO\b", "title_not_matches": ["{BAD}", r"\bA{0,3}Z\b"],
                                                  "title_before_words": ["@frame", "N"]},
                           "then": {"doc_type": "atto_precetto"}, "rationale": "test", "tests": ["inline"]}]}
        rf = RuleFile(data, "t")
        self.assertEqual(rf.rules[0]["when"]["title_not_matches"], [r"\bREVOC", r"\bA{0,3}Z\b"])   # a quantifier is left alone
        self.assertEqual(rf.rules[0]["when"]["title_before_words"], ["ATTO", "DI", "N"])
        self.assertEqual(data["rules"][0]["when"]["title_before_words"], ["@frame", "N"])          # the source is not mutated
        self.assertEqual(rf.apply({"text": "ATTO DI PRECETTO"})[1], "X-1")
        self.assertEqual(rf.apply({"text": "ATTO DI PRECETTO REVOCATO"})[1], None)
        data["rules"][0]["when"]["title_before_words"] = ["@no_such_list"]
        with self.assertRaises(KeyError):
            RuleFile(data, "t")


class TitleMerge(unittest.TestCase):
    """The two title readers through the classifier, one test per row of 'title_merge'."""
    DIFFIDA = "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA\nVi invitiamo a corrispondere {} la somma di € 1.000,00."
    PRECETTO = ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO E INTIMAZIONE\nINTIMA a FORNACE AURELIA S.R.L. di pagare "
                "{} la somma di € 1.000,00.")

    def test_inline_tests_of_the_table(self):
        self.assertEqual(typeagree.run_merge_tests(RuleFile.load("doc_type.json"), RULES, CTX.terms_cfg), [])
        ids = [r["id"] for r in RULES["title_merge"]]
        self.assertEqual(len(ids), len(set(ids)))
        for r in RULES["title_merge"]:
            self.assertTrue(r["rationale"] and r["tests"], r["id"])

    def test_the_table_covers_every_pair_of_readings(self):
        fam = CTX.title_families
        seen = set()
        for exclusive in (None, "atto_precetto"):
            for state in typeagree.AGREEMENT_STATES:
                for a_type in (("atto_precetto", "intimazione_pagamento") if state == "committed" else (None,)):
                    rid, outcome = typeagree.merge_rule(exclusive, typeagree.Reading(state, a_type, "t"), fam)
                    self.assertIsNotNone(rid, (exclusive, state, a_type))
                    seen.add(rid)
                    if exclusive and state == "committed" and a_type != exclusive:
                        self.assertEqual(outcome, "RECUPERARE")               # disagreement
                    if exclusive and state == "conflict":
                        self.assertEqual(outcome, "RECUPERARE")
                    if not exclusive and state in ("conflict", "unconfirmed", "not_understood"):
                        self.assertEqual(outcome, "RECUPERARE")               # arm A's abstentions stand
        self.assertEqual(seen, {r["id"] for r in RULES["title_merge"]})       # and no row is dead

    def test_tm001_the_readers_commit_different_types(self):
        """DT-030 reads a precetto; the stated term is the one of an intimazione (5 days), which is also on the
        title: the agreement reader commits intimazione_pagamento. v2.1 committed that, arm B atto_precetto."""
        r = record(self.PRECETTO.format("entro cinque giorni dalla notifica"), subject="Sollecito", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"))
        self.assertIn("TM-001", r["recuperare_reasons"]["doc_type"])
        self.assertIn("disagree", r["recuperare_reasons"]["doc_type"])
        self.assertIn("DT-030", r["rule_trace"]["doc_type"])
        self.assertIn("TF-007", r["rule_trace"]["doc_type"])
        self.assertEqual(r["deadlines"], [])                                  # nothing computed, not even kept aside
        self.assertIn("legal policy", r["recuperare_reasons"]["deadline"])

    def test_tm002_the_rule_commits_but_two_families_are_confirmed(self):
        r = record(self.PRECETTO.format("entro cinque giorni dalla notifica"), subject="Atto di precetto", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"))
        self.assertIn("TM-002", r["recuperare_reasons"]["doc_type"])
        self.assertIn("more than one confirmed family", r["recuperare_reasons"]["doc_type"])
        self.assertEqual(r["deadlines"], [])

    def test_tm003_both_readers_agree(self):
        r = record(self.DIFFIDA.format("entro quindici giorni dal ricevimento della presente"))
        self.assertEqual((r["doc_type"], r["deadline"]), ("diffida_messa_in_mora", "2026-10-21"))
        for part in ("TF-011", "T-009", "DT-031"):
            self.assertIn(part, r["rule_trace"]["doc_type"])
        r = record(self.PRECETTO.format("nel termine di giorni dieci dalla notifica del presente atto"),
                   subject="Sollecito", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("atto_precetto", "2026-10-16"))
        for part in ("TF-003", "T-001", "DT-030"):
            self.assertIn(part, r["rule_trace"]["doc_type"])

    def test_tm004_the_title_alone_commits_under_the_rules_own_conditions(self):
        """The port. v2.1 abstained on each of these (agreement reader: unconfirmed / not understood)."""
        r = record(self.DIFFIDA.format("senza indugio"))
        self.assertEqual((r["doc_type"], r["deadline"]), ("diffida_messa_in_mora", "RECUPERARE"))   # no term: no deadline
        self.assertTrue(r["rule_trace"]["doc_type"].startswith("DT-031 "))
        self.assertIn("TM-004", r["rule_trace"]["doc_type"])
        self.assertIn("unconfirmed", r["rule_trace"]["doc_type"])
        self.assertNotIn("doc_type", r["recuperare_fields"])
        # the term clause is not read: the type is committed, the deadline is not (arm B's test, same values)
        r = record(self.DIFFIDA.format("entro quindici giorni lavorativi dal ricevimento della presente"))
        self.assertEqual((r["doc_type"], r["deadline"], r["amount_due"]), ("diffida_messa_in_mora", "RECUPERARE", "1000.00"))
        # misleading subject, silent text: the act's statutory term is computed, as for a plain 'ATTO DI PRECETTO'
        r = record(self.PRECETTO.format("senza indugio"), subject="Sollecito", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"], r["deadline_nature"]), ("atto_precetto", "2026-10-16", "computed"))
        self.assertTrue(r["rule_trace"]["doc_type"].startswith("DT-030 "))
        # a qualifier the agreement reader does not understand
        r = record("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO SU TITOLO GIUDIZIALE\nINTIMA a FORNACE AURELIA S.R.L. di pagare "
                   "entro dieci giorni dalla notifica la somma di € 1.000,00.", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("atto_precetto", "2026-10-16"))
        self.assertIn("not_understood", r["rule_trace"]["doc_type"])

    def test_tm004_a_subject_naming_another_act_confirms_nothing_and_vetoes_nothing(self):
        r = record(self.DIFFIDA.format("senza indugio"), subject="Notifica atto di precetto")
        self.assertEqual(r["doc_type"], "diffida_messa_in_mora")      # the title decides (as DT-014 since v2.0)
        self.assertNotIn("DT-050", r["rule_trace"]["doc_type"])

    def test_tm005_only_the_agreement_reader_reads_and_is_confirmed(self):
        r = record("AGENZIA ESEMPIO RISCOSSIONE\nAVVISO DI INTIMAZIONE\nrelativa alla cartella n. 1.", sender=AGENZIA,
                   subject="Notifica intimazione")
        self.assertEqual(r["doc_type"], "intimazione_pagamento")
        self.assertEqual(r["rule_trace"]["doc_type"], "TF-007 title family confirmed by subject")   # worded as in v2.1
        r = record("AGENZIA ESEMPIO RISCOSSIONE\nINTIMAZIONE E DIFFIDA\nSi intima il pagamento.", sender=AGENZIA,
                   subject="Notifica intimazione di pagamento")
        self.assertEqual(r["doc_type"], "intimazione_pagamento")

    def test_tm006_no_rule_applies_and_the_agreement_reader_abstains(self):
        for title, subject, why in (
                ("RISCONTRO A VOSTRA DIFFIDA", "Riscontro a diffida", "not understood"),
                ("INTIMAZIONE E DIFFIDA", "Comunicazione", "no independent reading"),
                ("CHIARIMENTI SULLA MESSA IN MORA", "Messa in mora", "not understood"),
                ("SOLLECITO INVIO DOCUMENTAZIONE", "Sollecito", "not understood"),
                ("ATTO DI PRECETTO - ISTANZA DI SOSPENSIONE", "Atto di precetto", "not understood"),
                # arm B fell back on the subject for these two (DT-053, DT-050): not ported, arm A's veto stands
                ("CARTELLA ESATTORIALE", "Notifica cartella di pagamento n. 1", "not understood"),
                ("MEMORIA SULL'ATTO DI PRECETTO", "Atto di precetto", "not understood")):
            r = record(f"OFFICINE LAGORAI S.R.L.\n{title}\nIn riferimento a quanto in oggetto si comunica quanto segue.",
                       subject=subject)
            self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"), title)
            self.assertIn(why, r["recuperare_reasons"]["doc_type"], title)
            self.assertEqual(r["deadlines"], [], title)

    def test_tm007_no_title_reader_has_anything_to_say(self):
        r = record("STUDIO LEGALE MOSCARDINI\nSi trasmette in allegato quanto in oggetto.", subject="Notifica cartella")
        self.assertEqual((r["doc_type"], r["rule_trace"]["doc_type"]), ("cartella_pagamento", "DT-053"))
        r = record("STUDIO LEGALE MOSCARDINI\nSi trasmette in allegato quanto in oggetto.")
        self.assertEqual((r["doc_type"], r["rule_trace"]["doc_type"]), ("RECUPERARE", "no rule matched"))
        r = record("", subject="Inoltro atto di precetto ricevuto a mezzo posta")          # no text layer at all
        self.assertEqual((r["doc_type"], r["rule_trace"]["doc_type"]), ("atto_precetto", "DT-050"))

    def test_a_missing_or_broken_table_never_commits(self):
        fam = CTX.title_families
        then, rule = {"doc_type": "atto_precetto", "basis": "title_exclusive"}, "DT-030"
        text = "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO E INTIMAZIONE\nin forza"
        args = (text, "Sollecito", [], )
        empty = typeagree.Families(fam.items, fam.neutral, ())
        self.assertEqual(typeagree.resolve(then, rule, *args, empty, CTX.terms_cfg)[0], "RECUPERARE")
        self.assertEqual(typeagree.resolve(None, None, "STUDIO X\nSi trasmette.", "x", [], empty, CTX.terms_cfg)[0], "RECUPERARE")
        # a table that would let the rule override a DIFFERENT confirmed family, or win over two confirmed ones
        override = typeagree.Families(fam.items, fam.neutral, (("TM-X", "committed", typeagree.AGREEMENT_STATES, None, "exclusive"),))
        five_days = [{"days": 5, "from_event": "notification", "conditional": False}]
        self.assertEqual(typeagree.resolve(then, rule, text, "Sollecito", five_days, override, CTX.terms_cfg)[0], "RECUPERARE")
        self.assertEqual(typeagree.resolve(then, rule, text, "Atto di precetto", five_days, override, CTX.terms_cfg)[0], "RECUPERARE")
        # a table that would commit the agreement reader where it abstains, or 'fall back' past a committing rule
        wrong = typeagree.Families(fam.items, fam.neutral, (("TM-Y", "committed", typeagree.AGREEMENT_STATES, None, "agreement"),))
        self.assertEqual(typeagree.resolve(then, rule, *args, wrong, CTX.terms_cfg)[0], "RECUPERARE")
        fallback = typeagree.Families(fam.items, fam.neutral, (("TM-Z", "committed", typeagree.AGREEMENT_STATES, None, "fallback"),
                                                                ("TM-W", "silent", typeagree.AGREEMENT_STATES, None, "fallback")))
        self.assertEqual(typeagree.resolve(then, rule, *args, fallback, CTX.terms_cfg)[0], "RECUPERARE")
        self.assertEqual(typeagree.resolve(None, None, "STUDIO X\nATTO DI OPPOSIZIONE A PRECETTO", "Precetto", [], fallback,
                                           CTX.terms_cfg)[0], "RECUPERARE")
        with self.assertRaises(ValueError):
            typeagree.compile_families({"title_merge": [{"id": "TM-Q", "when": {"exclusive": "committed", "agreement": ["maybe"]},
                                                         "then": {"outcome": "exclusive"}}]})

    def test_the_agreement_reader_alone_is_unchanged(self):
        """read() is the v2.1 function: the family tests of doc_type.json still describe it, without the merge."""
        fam = CTX.title_families
        text = "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA\nVi invitiamo"
        self.assertEqual(typeagree.read(text, "Comunicazione", [], fam, CTX.terms_cfg)[0], "RECUPERARE")
        self.assertEqual(typeagree.read_state(text, "Comunicazione", [], fam, CTX.terms_cfg).state, "unconfirmed")
        self.assertEqual(typeagree.read("STUDIO X\nSi trasmette.", "x", [], fam, CTX.terms_cfg)[0], None)
        self.assertEqual(typeagree.run_inline_tests(RULES, CTX.terms_cfg), [])


class AmountTwoReaders(unittest.TestCase):
    AMOUNTS = json.loads((ROOT / "rules" / "amounts.json").read_text(encoding="utf-8"))

    # --- arm B's tests (class AmountGrammar), ported: same values; the rule id says which reader committed ---
    def test_labels_read(self):
        for text, doc, val, rule in (("Totale a debito: Euro 4.210,50. Si intima", "cartella_pagamento", "4210.50", "A-003"),
                                     ("l'importo complessivo di Euro 12.380,00, oltre", "atto_precetto", "12380.00", "A-003"),
                                     ("Importo dovuto: € 9.870,00, comprensivo", "avviso_accertamento", "9870.00", "A-002"),
                                     ("la somma di € 1.000,00.", "diffida_messa_in_mora", "1000.00", "A-002"),
                                     ("importo residuo dovuto pari a EUR 700,00", "sollecito_pagamento", "700.00", "A-004"),
                                     ("la somma ingiunta di € 9.000,00", "decreto_ingiuntivo", "9000.00", "A-003"),
                                     ("per complessivi € 2.500,00", "atto_precetto", "2500.00", "A-002")):
            self.assertEqual(amounts.extract_amount(text, doc), (val, rule), text)

    def test_recitals_and_historical_totals_are_not_labels(self):
        for text, doc in (("per il credito di € 5.000,00 portato dal titolo", "pignoramento_mobiliare"),
                          ("somme pari a € 3.200,00 dovute al terzo", "pignoramento_presso_terzi"),
                          ("Totale versato: € 1.000,00.", "sollecito_pagamento"),
                          ("saldo di € 2.000,00", "sollecito_pagamento"),
                          ("importo di cui sopra € 700,00", "sollecito_pagamento"),
                          ("credito complessivo di € 700,00", "sollecito_pagamento")):
            self.assertEqual(amounts.extract_amount(text, doc), (None, None), text)

    # --- the merge ------------------------------------------------------------------------------------------
    def test_rule_files(self):
        self.assertEqual([r["id"] for r in self.AMOUNTS["rules"]], ["A-001", "A-002", "A-003", "A-004"])
        self.assertEqual([r["when"].get("reader", "labels") for r in self.AMOUNTS["rules"]], ["both", "labels", "labels", "grammar"])
        a2, a3, a4 = (r["when"] for r in self.AMOUNTS["rules"][1:])
        self.assertEqual(a2["after_not"], a3["after_not"])            # arm A's net, unchanged
        # the grammar reader's net is arm A's WHOLE pattern plus alternatives of its own: it can only refuse more
        self.assertTrue(a4["after_not"].startswith(a3["after_not"] + "|"))
        for text in ("Abbiamo emesso un importo pari a € 800,00 quale nota di credito.",
                     "Totale pari a € 120,00 riconosciuto a titolo di sconto.",
                     "La somma pari a € 640,00 Vi è stata bonificata il 2 ottobre."):
            self.assertEqual(amounts.extract_amount(text, "sollecito_pagamento"), (None, None), text)
        self.assertTrue(a4["unique_amount"])
        for r in self.AMOUNTS["agreement"]:
            self.assertTrue(r["rationale"] and r["tests"], r["id"])

    def test_inline_tests_of_the_agreement_table(self):
        for r in self.AMOUNTS["agreement"]:
            for t in r["tests"]:
                got = amounts.read_amount(t["input"]["text"], t["input"]["doc_type"])
                self.assertEqual((got.value, got.rule, got.agreement), (t["expect"]["amount_due"], t["expect_rule"], r["id"]), t["id"])

    def test_the_grammar_alone_reads_what_the_labels_do_not(self):
        for text, want in (("Totale da versare € 310,00 entro cinque giorni.", "310.00"),
                           ("Vi invitiamo a versare un importo pari a Euro 2.300,00.", "2300.00"),
                           ("Importo precettato: € 8.000,00, oltre interessi maturandi.", "8000.00"),
                           ("Somma dovuta pari a € 640,00", "640.00"),
                           ("Totale richiesto EUR 1.999,99", "1999.99"),
                           ("importo residuo da pagare: € 410,00", "410.00")):
            self.assertEqual(amounts.extract_amount(text, "sollecito_pagamento"), (want, "A-004"), text)

    def test_the_grammar_alone_is_held_by_arm_a_nets(self):
        """Every one of these is read by arm B's grammar as built (no condition); none is committed here."""
        for text, seen in (("Importo dovuto pari a € 1.000,00, oltre spese per € 50,00.", "1000.00"),        # two amounts
                           ("Totale da versare € 310,00 oltre euro 20 di bolli.", "310.00"),                 # second, no decimals
                           ("Importo pari a € 500,00 già versato in data 01/09/2026.", "500.00"),            # paid
                           ("Somma pari a € 1.234,56 a Vostro favore.", "1234.56"),                          # a credit
                           ("Totale richiesto € 90,00 da rimborsare a Voi.", "90.00"),                       # a refund
                           ("Importo pari a € 75,00 non dovuto.", "75.00"),
                           ("L'importo residuo pari a € 800,00 sarà oggetto di separata comunicazione.", "800.00"),
                           ("L'importo complessivo residuo di € 800,00 sarà comunicato.", "800.00")):        # bare residue
            t = " ".join(text.split())
            self.assertEqual(amounts._read(t, "sollecito_pagamento", "grammar", nets=False)[0], seen, text)   # it SEES it
            self.assertEqual(amounts.extract_amount(text, "sollecito_pagamento"), (None, None), text)         # not read
        # the word boundary: arm B's pattern read the tail of 'sottototale'
        self.assertEqual(amounts.extract_amount("Sottototale € 50,00 (IVA esclusa).", "sollecito_pagamento"), (None, None))
        self.assertEqual(amounts.extract_amount("Subtotale: € 50,00.", "sollecito_pagamento"), (None, None))

    def test_ax01_two_readers_two_figures(self):
        for text in ("L'importo residuo di € 800,00 resta sospeso. Importo dovuto: € 500,00.",
                     "Somma dovuta € 900,00; importo da pagare: € 1.000,00.",
                     "Totale € 100,00 per bolli. Per complessivi € 1.100,00."):
            got = amounts.read_amount(text, "sollecito_pagamento")
            self.assertEqual((got.value, got.rule, got.agreement), (None, "A-X01", "A-X01"), text)
            self.assertIn("disagree", got.reason)
        self.assertEqual(amounts.extract_amount("Somma dovuta € 900,00; importo da pagare: € 1.000,00.", "sollecito_pagamento"),
                         (None, "A-X01"))
        # the same figure under both labels is not a disagreement
        self.assertEqual(amounts.extract_amount("Somma dovuta € 900,00; importo da pagare: € 900,00.", "sollecito_pagamento"),
                         ("900.00", "A-002"))

    def test_ax01_through_the_classifier(self):
        r = record("CANTINE BELVEDERE S.P.A.\nSOLLECITO DI PAGAMENTO\nL'importo residuo di € 800,00 resta sospeso. "
                   "Importo dovuto: € 500,00.")
        self.assertIsNone(r["amount_due"])
        self.assertIn("amount_due", r["recuperare_fields"])
        self.assertIn("A-X01", r["recuperare_reasons"]["amount_due"])
        self.assertEqual(r["rule_trace"]["amount_due"], "A-X01")
        # also for a type that does not expect an amount: a silent null would hide the figure
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nL'importo residuo di € 800,00 resta sospeso. "
                   "Importo dovuto: € 500,00.", sender="contenzioso@civile.tribunale.example")
        self.assertEqual(r["doc_type"], "comunicazione_cancelleria")
        self.assertIsNone(r["amount_due"])
        self.assertIn("amount_due", r["recuperare_fields"])

    def test_the_table_covers_every_pair_and_a_broken_one_never_commits(self):
        rows = amounts._config()[1]
        for labels in ("committed", "silent"):
            for grammar in ("committed", "silent"):
                for same in ((True, False) if (labels, grammar) == ("committed", "committed") else (None,)):
                    hit = [r for r in rows if (r[1], r[2]) == (labels, grammar) and (r[3] is None or r[3] == same)]
                    self.assertTrue(hit, (labels, grammar, same))
        self.assertEqual({r[0] for r in rows}, {r["id"] for r in self.AMOUNTS["agreement"]})
        disagree = "Somma dovuta € 900,00; importo da pagare: € 1.000,00."
        only_labels = "a corrispondere la somma capitale di € 1.250,00 entro quindici giorni"
        unsafe_grammar = "Importo dovuto pari a € 1.000,00, oltre spese per € 50,00."
        for table in ((),                                                                   # no table at all
                      (("X", "committed", "committed", None, "labels"),),                   # 'labels win a disagreement'
                      (("X", "committed", "committed", None, "grammar"),),
                      (("X", "committed", "committed", None, "none"),)):
            with mock.patch.object(amounts, "_config", return_value=(amounts._rules(), table)):
                self.assertIsNone(amounts.read_amount(disagree, "sollecito_pagamento").value, table)
        with mock.patch.object(amounts, "_config", return_value=(amounts._rules(), ())):
            self.assertIsNone(amounts.read_amount(only_labels, "sollecito_pagamento").value)
            self.assertEqual(amounts.read_amount("nessuna cifra", "sollecito_pagamento"), (None, None, None, None))
        with mock.patch.object(amounts, "_config", return_value=(amounts._rules(), (("X", "silent", "committed", None, "grammar"),))):
            self.assertIsNone(amounts.read_amount(unsafe_grammar, "sollecito_pagamento").value)   # the nets are in the rule


class EndToEndInvariance(unittest.TestCase):
    """Arm B's tests, ported: the same notice in canonical and in rewritten phrasing must give the SAME committed
    doc type, deadline and amount (and the rewritten one must not abstain where the canonical one commits)."""

    def same(self, canonical, rewritten, sender, fields=("doc_type", "deadline", "amount_due")):
        a, b = record(canonical, sender=sender), record(rewritten, sender=sender)
        for f in fields:
            self.assertEqual(a[f], b[f], f)
            self.assertNotIn(a[f], (None, "RECUPERARE"), f"canonical {f} not committed: {a['recuperare_reasons']}")
        return a

    def test_cartella(self):
        can = ("AGENZIA ESEMPIO RISCOSSIONE\n\nCARTELLA DI PAGAMENTO N. SYN-068-2026-000123\nRif. pratica: PR-1\n\n"
               "Intestatario: FORNACE AURELIA S.R.L.\nRuolo reso esecutivo il 05/09/2026 dall'ente creditore.\n"
               "Importo dovuto: € 4.210,50.\nSi intima il pagamento entro sessanta giorni dalla notificazione della presente cartella.")
        rew = ("AGENZIA ESEMPIO RISCOSSIONE\n\nCARTELLA DI PAGAMENTO N. SYN-068-2026-000123\nNs. rif.: PR-1\n\n"
               "Intestatario: FORNACE AURELIA S.R.L.\nRuolo reso esecutivo il 05-09-2026 dall'ente creditore.\n"
               "Totale a debito: Euro 4.210,50.\nSi intima il pagamento nel termine di giorni sessanta dalla notificazione della presente cartella.")
        a = self.same(can, rew, AGENZIA)
        self.assertEqual(a["deadline"], "2026-12-05")  # Tue 06/10 + 60 = Sat 05/12; T-006: no Saturday roll-over [TO CONFIRM with counsel]

    def test_rateizzazione(self):
        can = ("AGENZIA ESEMPIO RISCOSSIONE\n\nPIANO DI RATEIZZAZIONE\nRif. pratica: PR-1\nRif. atto: EX-1 del 02/10/2026\n\n"
               "Importo complessivo rateizzato: € 40.982,40. Importo della rata: € 3.415,20. Numero rate: 12.\n"
               "La prima rata scade il 30/11/2026.")
        rew = ("AGENZIA ESEMPIO RISCOSSIONE\n\nPIANO DI RATEIZZAZIONE\nNs. rif.: PR-1\nRif. atto: EX-1 del 02-10-2026\n\n"
               "Importo complessivo rateizzato: € 40.982,40. Importo della rata: € 3.415,20. Numero rate: 12.\n"
               "La prima rata dovrà essere corrisposta il 30-11-2026.")
        a = self.same(can, rew, AGENZIA)
        self.assertEqual((a["deadline"], a["amount_due"]), ("2026-11-30", "3415.20"))

    def test_precetto(self):
        can = ("STUDIO LEGALE MOSCARDINI\n\nATTO DI PRECETTO\nRif. pratica: PR-1\n\nPer conto e nell'interesse di TESSITURE "
               "MONTEVERDE S.R.L., con sede in Esempio,\nINTIMA\na FORNACE AURELIA S.R.L., di pagare entro il termine di "
               "dieci giorni dalla notifica del presente atto la somma di € 12.380,00, oltre interessi.")
        rew = ("STUDIO LEGALE MOSCARDINI\n\nATTO DI PRECETTO E INTIMAZIONE\nNs. rif.: PR-1\n\nIn nome e per conto di TESSITURE "
               "MONTEVERDE S.R.L., con sede in Esempio,\nINTIMA\na FORNACE AURELIA S.R.L., di pagare nel termine di giorni "
               "dieci dalla notifica del presente atto l'importo complessivo di Euro 12.380,00, oltre interessi.")
        a = self.same(can, rew, LAWYER)
        self.assertEqual((a["doc_type"], a["amount_due"]), ("atto_precetto", "12380.00"))

    def test_diffida(self):
        can = ("OFFICINE LAGORAI S.R.L.\n\nDIFFIDA E MESSA IN MORA\nRif. pratica: PR-1\n\nSpett.le FORNACE AURELIA S.R.L.,\n"
               "Vi diffido a corrispondere entro quindici giorni dal ricevimento della presente la somma di € 1.000,00.")
        rew = ("OFFICINE LAGORAI S.R.L.\n\nLETTERA DI DIFFIDA\nNs. rif.: PR-1\n\nSpett.le FORNACE AURELIA S.R.L.,\n"
               "Vi diffido a corrispondere entro e non oltre quindici giorni dal ricevimento della presente l'importo "
               "complessivo di Euro 1.000,00.")
        a = self.same(can, rew, "amministrazione@pec.officinelagorai.example")
        self.assertEqual((a["doc_type"], a["deadline"], a["amount_due"]), ("diffida_messa_in_mora", "2026-10-21", "1000.00"))

    def test_rewritten_phrasing_the_term_reader_cannot_read_still_abstains_on_the_deadline(self):
        rew = ("OFFICINE LAGORAI S.R.L.\n\nLETTERA DI DIFFIDA\nNs. rif.: PR-1\n\nSpett.le FORNACE AURELIA S.R.L.,\n"
               "Vi diffido a corrispondere entro quindici giorni lavorativi dal ricevimento della presente la somma di € 1.000,00.")
        r = record(rew)
        self.assertEqual((r["doc_type"], r["deadline"], r["amount_due"]), ("diffida_messa_in_mora", "RECUPERARE", "1000.00"))

    def test_my_own_rewrites_title_and_amount_together(self):
        """Wording outside the generator's pool, written for this test: the two ported readers in one notice."""
        can = ("STUDIO LEGALE MOSCARDINI\n\nATTO DI PRECETTO\nRif. pratica: PR-1\n\nINTIMA a FORNACE AURELIA S.R.L. di pagare "
               "entro il termine di dieci giorni dalla notifica del presente atto la somma di € 12.380,00, oltre interessi.")
        rew = ("STUDIO LEGALE MOSCARDINI\n\nNOTIFICAZIONE DI ATTO DI PRECETTO SU SENTENZA\nRif. pratica: PR-1\n\nINTIMA a "
               "FORNACE AURELIA S.R.L. di pagare entro il termine di dieci giorni dalla notifica del presente atto la "
               "somma precettata pari a € 12.380,00, oltre interessi.")
        a = self.same(can, rew, LAWYER)
        self.assertEqual((a["doc_type"], a["deadline"], a["amount_due"]), ("atto_precetto", "2026-10-16", "12380.00"))
        r = record(rew, sender=LAWYER)
        self.assertEqual(r["rule_trace"]["amount_due"], "A-004")
        self.assertIn("DT-030", r["rule_trace"]["doc_type"])


if __name__ == "__main__":
    unittest.main()
