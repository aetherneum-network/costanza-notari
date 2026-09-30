"""v2.1 - the other mechanisms that turn an abstention into a reading, each with the inputs on which it must
still abstain: date formats, structural nature rule (N-008), dateline (N-009), document type by agreement of two
readings, generalised amount label (A-003) - and the nets added around them: unknown dates still block, competing
written dates, vetoes on an actionable reading (N-V01, N-V02), cues read across an earlier date.
"""
import json
import unittest

from tests._records import CTX, record
from tests._util import ROOT
from pipeline import amounts, classify, deadlines as dl, typeagree

COURT = "contenzioso@civile.tribunale.example"
LAWYER = "avv.moscardini@pec.studiomoscardini.example"
REF = "2026-10-02"


def natures(text, reference=REF):
    return [dl.classify_nature(f["before"], f["after"], f["date"], reference, f["before_local"])
            for f in dl.find_dates(text)]


class DateFormats(unittest.TestCase):
    def test_one_separator_used_twice(self):
        for raw in ("12/11/2026", "12.11.2026", "12-11-2026", "2/3/2026", "02-03-2026"):
            found = dl.find_dates(f"entro il {raw} si provveda")
            self.assertEqual([f["raw"] for f in found], [raw])
            self.assertEqual(found[0]["date"][:4], "2026")
        self.assertEqual(dl.find_dates("udienza del 12-11-2026")[0]["date"], "2026-11-12")  # day first, as with '/'

    def test_not_a_date_stays_unread_and_is_flagged_inside_a_term_clause(self):
        for raw in ("12/11-2026", "12-11/2026", "12.11-2026",   # mixed separators
                    "12-11-26", "12/11/26",                     # two-digit year
                    "31-11-2026", "29/02/2027", "12-13-2026"):  # impossible calendar dates
            text = f"da versare entro il {raw}."
            self.assertEqual(dl.find_dates(text), [], raw)
            self.assertEqual(dl.unparsed_date_like(text), [raw], raw)

    def test_digits_glued_to_a_code_are_not_a_date(self):
        self.assertEqual(dl.find_dates("Rif. pratica: PR-10-11-2026"), [])
        self.assertEqual(dl.find_dates("cartella n. SYN-068-2026-000123"), [])
        self.assertEqual(dl.find_dates("prot. 1-12-11-2026"), [])

    def test_iso_dates_are_found_once(self):
        self.assertEqual([f["date"] for f in dl.find_dates("scadenza: 2026-11-12.")], ["2026-11-12"])

    def test_a_dashed_date_is_classified_like_any_other(self):
        self.assertEqual(natures("La prima rata scade il 30-11-2026."), [("actionable", "N-005")])
        self.assertEqual(natures("fattura n. 7 del 14-04-2026, insoluta."), [("historical", "N-000")])


class StructuralNature(unittest.TestCase):
    """N-008: term noun + future/deontic verb + linker + date. No phrase below is in the perturbation pool
    except the first two."""

    ACTIONABLE = [
        "a comparire all'udienza che si terrà il 12/11/2026 ore 9:30",
        "La prima rata dovrà essere corrisposta il 30/11/2026.",
        "L'udienza di comparizione delle parti è stata differita al giorno 15/12/2026.",
        "Il pagamento della seconda rata avverrà in data 15/12/2026.",
        "L'udienza sarà celebrata il 20 novembre 2026.",
        "La rata successiva andrà versata il 15-12-2026.",
        "Il saldo deve essere corrisposto il 10/12/2026.",
        "Le rate successive scadranno il 31/01/2027.",
        "L'udienza per la discussione viene fissata per il giorno 9 dicembre 2026.",
    ]
    NOT_A_TERM = [
        # (text, nature, rule)
        ("L'udienza non si terrà il 12/11/2026.", "RECUPERARE", "N-FALLBACK"),           # negation
        ("Il pagamento sarà accettato solo dopo il 12/11/2026.", "RECUPERARE", "N-FALLBACK"),
        ("L'udienza potrà essere rinviata al 15/12/2026.", "RECUPERARE", "N-FALLBACK"),   # possibility
        ("Il legale rappresentante sarà presente il 12/11/2026.", "RECUPERARE", "N-FALLBACK"),  # no term noun
        ("La rata sarà ricalcolata se versata il 12/11/2026.", "RECUPERARE", "N-FALLBACK"),     # 'se'
        ("Qualora la rata dovrà essere corrisposta il 12/11/2026, si comunica", "conditional", "N-001"),
        ("La rata che originariamente scadrà il 12/11/2026 è annullata", "historical", "N-002"),
        ("all'udienza che si terrà il 10/09/2026", "historical", "N-000"),                # not after the reference
    ]

    def test_actionable(self):
        for text in self.ACTIONABLE:
            got = natures(text)
            self.assertEqual([n for n, _ in got], ["actionable"], text)
            self.assertIn(got[0][1], ("N-008", "N-005"), text)
        self.assertEqual(natures(self.ACTIONABLE[0]), [("actionable", "N-008")])
        self.assertEqual(natures(self.ACTIONABLE[1]), [("actionable", "N-008")])

    def test_not_a_term(self):
        for text, nature, rule in self.NOT_A_TERM:
            self.assertEqual(natures(text), [(nature, rule)], text)

    def test_without_a_reference_date_the_rule_does_not_apply(self):
        self.assertEqual(natures("all'udienza che si terrà il 12/11/2026", reference=None), [("RECUPERARE", "N-FALLBACK")])

    def test_through_the_classifier(self):
        r = record("AGENZIA ESEMPIO RISCOSSIONE\nPIANO DI RATEIZZAZIONE\nImporto della rata: € 1.020,00.\n"
                   "La prima rata dovrà essere corrisposta il 30-11-2026.",
                   sender="notifica.cartelle@pec.agenzia-riscossione.example")
        self.assertEqual((r["deadline"], r["deadline_nature"], r["rule_trace"]["deadline"]),
                         ("2026-11-30", "actionable", "N-008"))
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nL'udienza non si terrà il 12/11/2026.",
                   sender=COURT)
        self.assertEqual(r["deadline"], "RECUPERARE")


class Dateline(unittest.TestCase):
    def test_place_and_date_line_is_the_document_date(self):
        # the document is dated AFTER the (tampered or wrong) transport timestamp: still not a term
        self.assertEqual(natures("Vi invitiamo a provvedere. Esempio, 05/10/2026", reference="2026-10-04"),
                         [("historical", "N-009")])
        self.assertEqual(natures("Distinti saluti. Reggio nell'Emilia, lì 5 ottobre 2026", reference="2026-10-04"),
                         [("historical", "N-009")])

    def test_only_a_line_made_of_the_place_alone(self):
        for text in ("Il Giudice ha disposto la comparizione in Esempio, 05/11/2026",
                     "Si provveda. Scadenza, 05/11/2026", "Si provveda. Udienza, 05/11/2026",
                     "Si provveda. esempio, 05/11/2026"):
            self.assertEqual(natures(text, reference="2026-10-04"), [("RECUPERARE", "N-FALLBACK")], text)


class UnknownDatesStillBlock(unittest.TestCase):
    """v2.1 keeps the v2.0 net untouched: ANY written future date of unknown nature forces RECUPERARE. (A shortcut
    that ignored an unknown date lying after the driving deadline was built and removed: a later date may be a
    postponement or an extension, i.e. exactly the date that replaces the deadline.)"""
    BODY = ("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nSi comunica che il Giudice ha rinviato l'udienza "
            "al 26/11/2026. {}")

    def test_no_relevance_shortcut_exists(self):
        self.assertFalse(hasattr(classify, "unknown_date_matters"))

    def test_an_unknown_date_blocks_wherever_it_falls(self):
        for tail in ("Il fascicolo sarà consultabile il 10/11/2026.",     # before the hearing
                     "Il fascicolo sarà consultabile il 10/12/2026.",     # after the hearing
                     "Il fascicolo sarà consultabile il 26/11/2026.",     # the same day
                     "Proroga concessa fino al 15/12/2026.",              # an extension: the later date is the real one
                     "Con successivo provvedimento la stessa è differita: 15/12/2026."):
            r = record(self.BODY.format(tail), sender=COURT)
            self.assertEqual(r["deadline"], "RECUPERARE", tail)
            self.assertEqual([d["nature"] for d in r["dates"]], ["actionable", "RECUPERARE"], tail)  # both surfaced

    def test_a_date_not_after_the_notification_does_not_block(self):
        r = record(self.BODY.format("Provvedimento del 01/10/2026."), sender=COURT)
        self.assertEqual(r["deadline"], "2026-11-26")


class CompetingWrittenDates(unittest.TestCase):
    """A date read by a structural rule (then.sole_candidate) is accepted only when no other future date competes."""
    REF = "2026-10-06"

    @staticmethod
    def d(date, rule, nature="actionable"):
        return {"date": date, "rule": rule, "nature": nature, "raw": date}

    def test_flag_comes_from_the_rule_file(self):
        self.assertEqual(dl.sole_candidate_rules(), frozenset({"N-008"}))

    def test_unit(self):
        f, d = classify.competing_written_dates, self.d
        both = [d("2026-11-12", "N-008"), d("2026-12-15", "N-005")]
        self.assertEqual([x["date"] for x in f(both, self.REF)], ["2026-11-12", "2026-12-15"])
        self.assertEqual([x["date"] for x in f(both[::-1], self.REF)], ["2026-11-12", "2026-12-15"])
        self.assertEqual(f([d("2026-11-12", "N-008")], self.REF), [])                                # alone
        self.assertEqual(f([d("2026-11-12", "N-005"), d("2026-12-15", "N-005")], self.REF), [])      # v2.0 rules only
        self.assertEqual(f([d("2026-11-12", "N-008"), d("2026-11-12", "N-005")], self.REF), [])      # the same day
        self.assertEqual(f([d("2026-11-12", "N-008"), d("2026-10-01", "N-005")], self.REF), [])      # not future
        self.assertEqual(f([d("2026-11-12", "N-008"), d("2026-12-15", "N-006", "historical")], self.REF), [])
        self.assertEqual(f([d("2026-11-12", "N-008"), d("2026-12-15", "N-001", "conditional")], self.REF), [])
        self.assertEqual(len(f([d("2026-11-12", "N-008"), d("2026-12-15", "N-FALLBACK", "RECUPERARE")], self.REF)), 2)
        self.assertEqual(len(f(both, None)), 2)   # no reference date: every date counts

    def test_through_the_classifier(self):
        head = "TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\n"
        r = record(head + "L'udienza si terrà il 12/11/2026. La rata dovrà essere versata il 15/12/2026.", sender=COURT)
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("more than one future date", r["recuperare_reasons"]["deadline"])
        # one structural date alone is read
        r = record(head + "L'udienza si terrà il 12/11/2026.", sender=COURT)
        self.assertEqual((r["deadline"], r["rule_trace"]["deadline"]), ("2026-11-12", "N-008"))
        # two dates read by the v2.0 cue rules: v2.0 behaviour (the earliest drives) is not changed by v2.1
        r = record(head + "Udienza del 12/11/2026. Note da depositare entro il 05/11/2026.", sender=COURT)
        self.assertEqual(r["deadline"], "2026-11-05")


class VetoesOnAnActionableReading(unittest.TestCase):
    """N-V01 / N-V02 (rules/deadline_nature.json, 'vetoes'): the cue says 'term', the sentence says more."""
    HEAD = "TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\n"

    def test_predicate_or_negation_after_the_date(self):
        for text in ("Si comunica che l'udienza del 12/11/2026 è rinviata a data da destinarsi.",
                     "L'udienza che si terrà il 12/11/2026 è annullata.",
                     "L'udienza del 12/11/2026 non si terrà.",
                     "L'udienza fissata per il 12/11/2026 viene anticipata.",
                     "La rata con scadenza il 30/11/2026 si intende sostituita dal nuovo piano."):
            self.assertEqual(natures(text), [("RECUPERARE", "N-V01")], text)
            self.assertEqual(record(self.HEAD + text, sender=COURT)["deadline"], "RECUPERARE", text)

    def test_postponement_with_both_dates_is_never_committed(self):
        for text in ("Si comunica che l'udienza del 12/11/2026 è rinviata al 15/12/2026.",
                     "L'udienza già fissata per il 12/11/2026 è differita al 15/12/2026.",
                     "L'udienza del 12/11/2026 sarà rinviata al 15/12/2026.",
                     "L'udienza si terrà il 15-12-2026 anziché il 12-11-2026.",
                     "L'udienza è fissata al 12/11/2026. Con successivo provvedimento l'udienza è stata rinviata "
                     "al 15/12/2026."):
            r = record(self.HEAD + text, sender=COURT)
            self.assertEqual(r["deadline"], "RECUPERARE", text)
            self.assertEqual(len(r["dates"]), 2, text)     # both dates are surfaced to the reader

    def test_a_confirming_predicate_does_not_veto(self):
        for text, rule in (("L'udienza del 12/11/2026 resta confermata.", "N-005"),
                           ("L'udienza che si terrà il 12/11/2026 ore 9:30 innanzi al Giudice è confermata.", "N-008"),
                           ("La prima rata scade il 12/11/2026 e deve essere versata mediante bonifico.", "N-005"),
                           ("a comparire all'udienza del 12/11/2026 ore 9:30 innanzi al Tribunale di Sonora", "N-005")):
            self.assertEqual(natures(text), [("actionable", rule)], text)

    def test_negation_in_the_clause_before_the_date(self):
        for text in ("L'udienza non è più fissata al 12/11/2026.",
                     "Non risulta che l'udienza si terrà il 12/11/2026.",
                     "La rata non va più versata entro il 12/11/2026."):
            self.assertEqual(natures(text), [("RECUPERARE", "N-V02")], text)
            self.assertEqual(record(self.HEAD + text, sender=COURT)["deadline"], "RECUPERARE", text)

    def test_emphasis_is_not_a_negation(self):
        for text in ("da versare entro e non oltre il 12/11/2026",
                     "termine non prorogabile con scadenza il 12/11/2026",
                     "Non essendo pervenute opposizioni, l'udienza è fissata al 12/11/2026"):
            self.assertEqual(natures(text), [("actionable", "N-005")], text)

    def test_the_veto_applies_to_actionable_readings_only(self):
        self.assertEqual(natures("Il termine fissato al 12/11/2026 è scaduto."), [("historical", "N-004")])
        self.assertEqual(natures("fattura non pagata del 12/09/2026"), [("historical", "N-000")])


class CueAcrossAnEarlierDate(unittest.TestCase):
    """when.across_a_date: a lead-in found only by reading across an earlier date of the sentence is not trusted."""

    def test_find_dates_gives_the_local_lead_in(self):
        f = dl.find_dates("L'udienza, originariamente prevista per il 12/11/2026, si terrà il 15/12/2026. Poi il 20/12/2026.")
        self.assertEqual([x["before_local"] for x in f],
                         ["L'udienza, originariamente prevista per il ", ", si terrà il ", " Poi il "])
        self.assertTrue(f[1]["before"].startswith("L'udienza, originariamente"))

    def test_recital_cue_that_may_belong_to_the_other_date(self):
        self.assertEqual(natures("L'udienza, originariamente prevista per il 12/11/2026, si terrà il 15/12/2026."),
                         [("historical", "N-002"), ("RECUPERARE", "N-002")])
        r = record("TRIBUNALE DI ESEMPIO\nCOMUNICAZIONE DI CANCELLERIA\nL'udienza, originariamente prevista per il "
                   "12/11/2026, si terrà il 15/12/2026.", sender=COURT)
        self.assertEqual(r["deadline"], "RECUPERARE")     # v2.0 answered 'no deadline' here

    def test_structural_rule_does_not_read_across_a_date(self):
        self.assertEqual(natures("La rata del 30/10/2026 sarà addebitata il 15/11/2026.")[1], ("RECUPERARE", "N-008"))
        self.assertEqual(natures("Con provvedimento del 01/10/2026 il Giudice ha disposto che l'udienza si terrà il "
                                 "15/11/2026.")[1], ("actionable", "N-008"))

    def test_a_cue_between_the_two_dates_governs_the_second(self):
        self.assertEqual(natures("La rata del 30/09/2026 doveva essere versata entro il 30/11/2026.")[1],
                         ("historical", "N-002"))

    def test_default_is_the_whole_lead_in(self):
        self.assertEqual(dl.classify_nature("già comunicato e valido per il", "", "2026-12-15", REF), ("historical", "N-007"))
        self.assertEqual(dl.classify_nature("già comunicato il 30/09/2026 e valido per il", "", "2026-12-15", REF,
                                            " e valido per il"), ("RECUPERARE", "N-007"))


class LimitsOfTheNewNatureRules(unittest.TestCase):
    def test_dateline_needs_a_date_close_to_the_notification_and_no_time_of_day(self):
        ok = "Vi invitiamo a provvedere. Esempio, 05/10/2026"
        self.assertEqual(natures(ok, reference="2026-10-04"), [("historical", "N-009")])
        self.assertEqual(natures("Vi invitiamo a provvedere. Esempio, 11/10/2026", reference="2026-10-04"),
                         [("historical", "N-009")])                                          # 7 days: still a dateline
        for text, ref in (("Vi invitiamo a provvedere. Esempio, 12/10/2026", "2026-10-04"),    # 8 days after
                          ("La prossima udienza si terrà altrove. Tribunale di Esempio, 15/12/2026", "2026-10-04"),
                          ("Udienza tenuta. Tribunale di Esempio, 07/10/2026 ore 9:30", "2026-10-04"),
                          (ok, None)):                                                        # no reference date
            self.assertEqual(natures(text, reference=ref), [("RECUPERARE", "N-FALLBACK")], text)

    def test_payment_nouns_need_an_obligation(self):
        self.assertEqual(natures("Il pagamento avverrà il 30/11/2026 a mezzo bonifico."), [("RECUPERARE", "N-FALLBACK")])
        self.assertEqual(natures("Il saldo sarà accreditato il 30/11/2026."), [("RECUPERARE", "N-FALLBACK")])
        self.assertEqual(natures("Il pagamento dovrà essere effettuato il 30/11/2026."), [("actionable", "N-008")])
        self.assertEqual(natures("Il versamento va eseguito il 30/11/2026."), [("actionable", "N-008")])


class TypeByAgreement(unittest.TestCase):
    DIFFIDA = "OFFICINE LAGORAI S.R.L.\nLETTERA DI DIFFIDA\nVi invitiamo a corrispondere {} la somma di € 1.000,00."
    PRECETTO = ("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO E INTIMAZIONE\nINTIMA a FORNACE AURELIA S.R.L. di pagare "
                "{} la somma di € 1.000,00.")

    def test_inline_tests_of_the_families(self):
        rules = json.loads((ROOT / "rules" / "doc_type.json").read_text(encoding="utf-8"))
        self.assertEqual(typeagree.run_inline_tests(rules, CTX.terms_cfg), [])
        ids = [f["id"] for f in rules["title_families"]]
        self.assertEqual(len(ids), len(set(ids)))
        for f in rules["title_families"]:
            self.assertTrue(f["rationale"] and f["tests"], f["id"])

    def test_title_and_stated_term_agree(self):
        r = record(self.DIFFIDA.format("entro quindici giorni dal ricevimento della presente"))
        self.assertEqual((r["doc_type"], r["deadline"]), ("diffida_messa_in_mora", "2026-10-21"))
        self.assertIn("TF-011", r["rule_trace"]["doc_type"])
        self.assertIn("T-009", r["rule_trace"]["doc_type"])

    def test_title_and_subject_agree(self):
        r = record(self.DIFFIDA.format("senza indugio"), subject="Diffida e messa in mora - PR-OL-0001")
        self.assertEqual(r["doc_type"], "diffida_messa_in_mora")
        self.assertIn("subject", r["rule_trace"]["doc_type"])

    def test_title_alone_is_not_enough(self):
        r = record(self.DIFFIDA.format("senza indugio"))
        self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"))
        self.assertIn("no independent reading", r["recuperare_reasons"]["doc_type"])
        # a term that runs from the notification does not confirm a private demand (T-009 runs from receipt)
        r = record(self.DIFFIDA.format("entro quindici giorni dalla notifica"))
        self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"))

    def test_two_families_on_the_title_are_resolved_only_by_a_second_reading(self):
        r = record(self.PRECETTO.format("nel termine di giorni dieci dalla notifica del presente atto"),
                   subject="Sollecito", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("atto_precetto", "2026-10-16"))
        r = record(self.PRECETTO.format("senza indugio"), subject="Sollecito", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"))
        # subject says precetto, the stated term (5 days) is the one of an intimazione: two confirmed families
        r = record(self.PRECETTO.format("entro cinque giorni dalla notifica"), subject="Atto di precetto", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"))
        self.assertIn("more than one confirmed family", r["recuperare_reasons"]["doc_type"])

    def test_a_title_with_a_foreign_word_is_not_understood_and_vetoes_the_subject_fallback(self):
        """v2.0 committed atto_precetto on the subject alone (DT-050) and computed the 10-day statutory term."""
        for title, subject in (("ATTO DI OPPOSIZIONE A PRECETTO", "Opposizione a precetto"),
                               ("PREAVVISO DI PRECETTO", "Preavviso di precetto"),
                               ("RINUNCIA AL PRECETTO", "Notifica atto di precetto")):
            r = record(f"STUDIO LEGALE MOSCARDINI\n{title}\nLa società comunica quanto segue.", subject=subject,
                       sender=LAWYER)
            self.assertEqual((r["doc_type"], r["deadline"]), ("RECUPERARE", "RECUPERARE"), title)
            self.assertIn("not understood", r["recuperare_reasons"]["doc_type"])
            self.assertEqual(r["deadlines"], [], title)  # nothing computed, not even kept aside

    def test_strict_title_rules_still_win(self):
        r = record("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO\nin forza del decreto", subject="Sollecito", sender=LAWYER)
        self.assertEqual((r["doc_type"], r["rule_trace"]["doc_type"]), ("atto_precetto", "DT-014"))

    def test_subject_fallback_is_kept_for_documents_without_text_or_without_a_title_family(self):
        r = record("", subject="Inoltro atto di precetto ricevuto a mezzo posta")
        self.assertEqual((r["doc_type"], r["rule_trace"]["doc_type"]), ("atto_precetto", "DT-050"))
        r = record("STUDIO LEGALE MOSCARDINI\nSi trasmette in allegato quanto in oggetto.", subject="Notifica cartella")
        self.assertEqual((r["doc_type"], r["rule_trace"]["doc_type"]), ("cartella_pagamento", "DT-053"))

    def test_title_lines_are_upper_case_lines_of_the_heading_only(self):
        self.assertEqual(typeagree.title_lines("STUDIO ROSSI\nLettera di diffida\nLETTERA DI DIFFIDA\n" + "x" * 700
                                               + "\nATTO DI PRECETTO"), ["STUDIO ROSSI", "LETTERA DI DIFFIDA"])
        fam = CTX.title_families
        self.assertEqual(typeagree.read_title("TRIBUNALE DI ESEMPIO\nSEZIONE CIVILE", fam), ([], []))
        cands, bad = typeagree.read_title("AVVISO DI ACCERTAMENTO N. SYN-AVV-2026-00015", fam)
        self.assertEqual(([c[1] for c in cands], bad), (["avviso_accertamento"], []))


class GeneralisedAmountLabel(unittest.TestCase):
    def test_inline(self):
        rules = json.loads((ROOT / "rules" / "amounts.json").read_text(encoding="utf-8"))["rules"]
        self.assertEqual([r["id"] for r in rules], ["A-001", "A-002", "A-003"])  # strict labels first

    def test_read(self):
        for text, want in (("Totale a debito: Euro 6.877,15, comprensivo di sanzioni e interessi.", "6877.15"),
                           ("di pagare l'importo complessivo di Euro 40.700,38, oltre interessi", "40700.38"),
                           ("Somma dovuta: € 310,00", "310.00"),
                           ("per un totale di € 1.250,00", "1250.00"),
                           ("Importo totale da versare: EUR 99,90", "99.90")):
            self.assertEqual(amounts.extract_amount(text, "cartella_pagamento"), (want, "A-003"), text)

    def test_not_read(self):
        for text in ("Totale a debito: Euro 6.877,15, di cui interessi per € 120,00.",     # two amounts
                     "Totale a debito: Euro 6.877,15. Aliquota applicata 10,60 per mille.",  # a second money-like figure
                     "Risulta un totale già versato di € 500,00.",
                     "L'importo residuo di € 800,00 sarà oggetto di separata comunicazione.",
                     "La dilazione è ammessa con importo minimo di € 50,00 per rata.",
                     "sono state accantonate somme pari a € 1.754,21.",
                     "si procede a pignoramento mobiliare per il credito di € 9.000,00.",
                     "Importo complessivo rateizzato: € 40.982,40.",
                     "Totale a debito: Euro 1.234,56, già corrisposto.",                   # paid: said AFTER the figure
                     "Importo complessivo di Euro 1.234,56 da rimborsare a Voi.",          # a refund
                     "Somma di € 1.234,56 a Vostro favore.",                               # a credit
                     "Importo di € 1.234,56 non dovuto.",
                     "Totale a debito: Euro 1.234,56 oltre euro 200 di spese.",            # second amount, no decimals
                     "Totale a debito: Euro 1.234,56 oltre 200 € di spese."):
            self.assertEqual(amounts.extract_amount(text, "cartella_pagamento"), (None, None), text)

    def test_amounts_without_decimals_count_only_next_to_a_currency_word(self):
        f = amounts.distinct_amounts
        self.assertEqual(f("Euro 1.234,56 oltre euro 200 di spese e 1.500 € di onorari"), {"1234.56", "200.00", "1500.00"})
        self.assertEqual(f("Euro 1.234,56 entro 10 giorni, art. 480 c.p.c., cartella n. 2026"), {"1234.56"})
        self.assertEqual(f("€ 1.234,56"), {"1234.56"})     # the integer part of a decimal amount is not a second amount

    def test_wording_after_the_figure_is_looked_at_inside_the_sentence_only(self):
        text = "Totale a debito: Euro 1.234,56. Quanto già versato resta acquisito."
        self.assertEqual(amounts.extract_amount(text, "cartella_pagamento"), ("1234.56", "A-003"))

    def test_strict_labels_are_not_subject_to_the_uniqueness_check(self):
        text = "Importo dovuto: € 6.877,15, di cui interessi per € 120,00."
        self.assertEqual(amounts.extract_amount(text, "cartella_pagamento"), ("6877.15", "A-002"))
        self.assertEqual(amounts.distinct_amounts(text), {"6877.15", "120.00"})

    def test_through_the_classifier(self):
        r = record("AGENZIA ESEMPIO RISCOSSIONE\nCARTELLA DI PAGAMENTO N. SYN-1\nTotale a debito: Euro 6.877,15, di cui "
                   "interessi per € 120,00.", sender="notifica.cartelle@pec.agenzia-riscossione.example")
        self.assertIsNone(r["amount_due"])
        self.assertIn("amount_due", r["recuperare_fields"])


if __name__ == "__main__":
    unittest.main()
