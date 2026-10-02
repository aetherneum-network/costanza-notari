"""v2.1 - structural reading of relative terms (pipeline/termclauses.py + rules/term_clauses.json).

What is tested, in order: the two number readers against each other; the two clause readers against each other;
paraphrases that are NOT in the perturbation pool of corpus/perturb.py (positive and negative); the nets
(everything that looks like a term and is not read must surface); "code extracts, rules decide" (L7).
"""
import json
import shutil
import unittest

from tests._records import CTX, record
from tests._util import ROOT, tmpdir
from pipeline import deadlines as dl, termclauses as tc, terms


def read(text):
    r = tc.read(text)
    return [(t["days"], t["from_event"], t["conditional"]) for t in r["terms"]], [u["why"] for u in r["unread"]]


class Cardinals(unittest.TestCase):
    """Two implementations written in opposite directions: spell (int -> words), parse_cardinal (words -> int)."""

    def test_round_trip_1_to_999(self):
        for n in range(1, 1000):
            self.assertEqual(tc.parse_cardinal(tc.spell(n)), n, tc.spell(n))

    def test_generated_table_and_parser_agree_on_every_accepted_form(self):
        table = tc.number_table()
        self.assertGreater(len(table), 999)  # variants: ventitré/ventitre, centottanta/centoottanta, un
        for word, n in table.items():
            self.assertEqual(tc.parse_cardinal(word), n, word)

    def test_known_spellings(self):
        for word, n in (("dieci", 10), ("ventuno", 21), ("ventotto", 28), ("ventitré", 23), ("trentatre", 33),
                        ("quaranta", 40), ("sessanta", 60), ("novanta", 90), ("cento", 100), ("centoventi", 120),
                        ("centottanta", 180), ("duecentosettanta", 270), ("novecentonovantanove", 999), ("un", 1)):
            self.assertEqual(tc.parse_cardinal(word), n, word)
            self.assertEqual(tc.number_table()[word], n, word)

    def test_malformed_words_are_not_numbers_for_either_reader(self):
        for word in ("ventiuno", "trentaotto", "centocento", "zero", "mille", "diecimila", "dieci1", "unodue",
                     "ventidieci", "centuno", "", "giorni"):
            self.assertIsNone(tc.parse_cardinal(word), word)
            self.assertNotIn(word, tc.number_table())

    def test_out_of_range(self):
        for n in (0, 1000, -3):
            with self.assertRaises(ValueError):
                tc.spell(n)


class TwoReadersMustAgree(unittest.TestCase):
    def both(self, text):
        cfg = tc.config()
        t = " ".join(text.split())
        return tc.reader_a(t, cfg), tc.reader_b(t, cfg)

    def test_same_reading_on_well_formed_clauses(self):
        for text, days in (("entro dieci giorni dalla notifica", 10), ("nel termine di giorni 40 dalla notificazione", 40),
                           ("entro 60 (sessanta) gg. dal ricevimento", 60), ("nei 15 giorni successivi alla ricezione", 15),
                           ("entro trenta giorni, naturali e consecutivi, dalla data di notifica", 30)):
            a, b = self.both(text)
            self.assertEqual(len(a), 1, text)
            self.assertEqual(set(a), set(b), text)
            (ra,), (rb,) = a.values(), b.values()
            self.assertEqual((ra["days"], rb["days"]), (days, days), text)
            self.assertEqual((ra["unit"], ra["qty_start"], ra["anchor"]), (rb["unit"], rb["qty_start"], rb["anchor"]))

    def test_every_number_in_every_position_is_read_identically(self):
        """1..999, digits and words, number-unit and unit-number: the committed value is always n."""
        for n in range(1, 1000):
            for qty in (f"{n} giorni", f"{tc.spell(n)} giorni", f"giorni {n}", f"giorni {tc.spell(n)}",
                        f"{n} ({tc.spell(n)}) giorni"):
                terms, unread = read(f"da versare entro {qty} dalla notifica del presente atto.")
                self.assertEqual((terms, unread), ([(n, "notification", False)], []), qty)

    def test_a_disagreement_is_never_committed(self):
        # each input is read differently (or by one reader only): the clause must surface as unread
        for text in ("entro 1.000 giorni dalla notifica",      # A refuses a number glued to '1.', B reads 000
                     "entro 1,5 giorni dalla notifica",        # a decimal
                     "entro 10/15 giorni dalla notifica",      # a range
                     "entro dieci-quindici giorni dalla notifica",
                     "entro 30gg dal ricevimento"):            # number glued to the unit
            terms, unread = read(text)
            self.assertEqual(terms, [], text)
            self.assertEqual(unread, ["readers_disagree"], text)

    def test_bracketed_repetition_must_match(self):
        self.assertEqual(read("entro 10 (dieci) giorni dalla notifica"), ([(10, "notification", False)], []))
        self.assertEqual(read("entro dieci (10) giorni dalla notifica"), ([(10, "notification", False)], []))
        self.assertEqual(read("entro 10 (dodici) giorni dalla notifica"), ([], ["number"]))
        self.assertEqual(read("entro giorni 40 (trenta) dalla notifica"), ([], ["number"]))

    def test_zero_and_four_digit_numbers_are_not_terms(self):
        self.assertEqual(read("entro 0 giorni dalla notifica"), ([], ["number"]))
        self.assertEqual(read("entro 1200 giorni dalla notifica"), ([], ["structure"]))


class ParaphrasesOutsideThePerturbationPool(unittest.TestCase):
    """None of these phrasings is produced by corpus/templates.py or corpus/perturb.py."""

    READ = [
        ("Il pagamento dovrà pervenire non oltre venti giorni dalla notificazione del presente avviso.", 20, "notification"),
        ("da versare entro il termine perentorio di giorni 30 (trenta) dal ricevimento della presente.", 30, "receipt"),
        ("Vi invitiamo a provvedere nei quindici giorni successivi al ricevimento della presente.", 15, "receipt"),
        ("entro i dieci giorni successivi alla notifica del presente atto", 10, "notification"),
        ("entro 60 gg. dalla notifica della presente cartella", 60, "notification"),
        ("entro gg. 5 dalla notifica", 5, "notification"),
        ("entro 40 giorni dalla data di notifica del presente avviso", 40, "notification"),
        ("entro novanta giorni dalla data del ricevimento", 90, "receipt"),
        ("entro 30 giorni naturali e consecutivi decorrenti dalla notifica", 30, "notification"),
        ("entro il termine essenziale di giorni sette dalla ricezione della presente", 7, "receipt"),
        ("nel termine massimo di centoventi giorni dalla notificazione", 120, "notification"),
        ("ENTRO E NON OLTRE VENTUNO GIORNI DALLA NOTIFICA DEL PRESENTE ATTO", 21, "notification"),
        ("entro\n   ventotto  giorni\n dall'  ricevimento", 28, "receipt"),
        ("entro quarantacinque giorni di calendario dalla notifica, a pena di decadenza", 45, "notification"),
        ("entro e non oltre il termine di 40 giorni dalla notifica", 40, "notification"),
    ]
    UNREAD = [
        # (text, slot that was not understood)
        ("L'esecuzione non potrà iniziare prima di dieci giorni dalla notifica del presente atto.", "lead_in"),
        ("Decorsi inutilmente dieci giorni dalla notifica si procederà ad esecuzione forzata.", "lead_in"),
        ("per almeno trenta giorni dalla notifica", "lead_in"),
        ("nei successivi dieci giorni dalla notifica", "lead_in"),
        ("entro il termine di complessivi dieci giorni dalla notifica", "lead_in"),
        ("entro dieci o venti giorni dalla notifica", "lead_in"),
        ("entro dieci giorni lavorativi dal ricevimento della presente", "qualifier"),
        ("entro venti giorni liberi dalla notifica", "qualifier"),
        ("entro cinque giorni feriali successivi alla notifica", "qualifier"),
        ("entro sei mesi dalla notifica", "unit"),
        ("entro due settimane dal ricevimento della presente", "unit"),
        ("entro il termine di 3 anni dalla notifica", "unit"),
        ("entro trenta giorni dalla data della presente", "anchor"),
        ("entro dieci giorni dal deposito del provvedimento", "anchor"),
        ("entro trenta giorni dalla comunicazione del presente provvedimento", "anchor"),
        ("entro sessanta giorni dall'avvenuta notifica", "anchor"),
        ("entro quaranta giorni dal perfezionamento della notifica", "anchor"),
        ("entro dieci giorni da oggi", "anchor"),
        ("non avendo il debitore pagato entro dieci giorni dalla notifica del precetto", "complement"),
        ("opposizione entro quaranta giorni dalla notifica del decreto", "complement"),
        ("entro venti giorni dalla notifica dello stesso", "complement"),
        ("entro venti giorni dalla notifica di cui sopra", "complement"),
        ("il pagamento doveva avvenire entro dieci giorni dalla notifica", "mood"),
        ("il versamento, originariamente dovuto entro 30 giorni dal ricevimento", "mood"),
        ("entro trentauno giorni dalla notifica", "structure"),
        ("entro alcuni giorni dalla notifica", "structure"),
        ("entro XV giorni dalla notifica", "structure"),
    ]
    SILENT = [
        # no term from an event, nothing to surface: same as v2.0
        "a costituirsi nel termine di settanta giorni prima dell'udienza indicata, ai sensi dell'art. 166 c.p.c.",
        "entro dieci giorni.",
        "udienza del giorno 12 novembre 2026 dalle ore 9:30",
        "entro dieci giorni da parte Vostra dovrà pervenire riscontro",
        "Relata di notifica a mezzo PEC. La notifica è stata eseguita in data odierna.",
        "fattura n. 12 di 30 giorni fa",
    ]

    def test_read(self):
        for text, days, event in self.READ:
            self.assertEqual(read(text), ([(days, event, False)], []), text)

    def test_unread_with_the_slot_that_failed(self):
        for text, why in self.UNREAD:
            self.assertEqual(read(text), ([], [why]), text)

    def test_silent(self):
        for text in self.SILENT:
            self.assertEqual(read(text), ([], []), text)

    def test_conditional_terms_are_read_but_flagged(self):
        terms, unread = read("Qualora il pagamento non avvenga entro 5 giorni dalla notifica; si procederà. "
                             "Entro 60 giorni dalla notifica può proporsi ricorso.")
        self.assertEqual((terms, unread), ([(5, "notification", True), (60, "notification", False)], []))
        for cue in ("In caso di mancato pagamento", "Nel caso in cui non si provveda", "Laddove non si adempia"):
            self.assertEqual(read(f"{cue} entro dieci giorni dalla notifica, il piano decade."),
                             ([(10, "notification", True)], []), cue)

    def test_one_unread_clause_does_not_hide_a_read_one_and_vice_versa(self):
        terms, unread = read("Pagare entro dieci giorni dalla notifica del presente atto. L'opposizione si propone "
                             "entro venti giorni lavorativi dalla notifica.")
        self.assertEqual((terms, unread), ([(10, "notification", False)], ["qualifier"]))


class ClauseThatGoesOnAfterTheAnchor(unittest.TestCase):
    """Mood rules with side 'after' (TC-M03..05): what follows the anchor, up to the end of the sentence."""

    def test_recital_of_a_term_already_run(self):
        for text in ("premesso che nel termine di giorni dieci dalla notifica non è stato effettuato alcun pagamento",
                     "Il termine, da osservarsi entro e non oltre 10 giorni dalla notifica, è inutilmente decorso.",
                     "entro 40 giorni dalla notificazione la società non ha proposto opposizione",
                     "entro dieci giorni dalla notifica il debitore avrebbe potuto proporre opposizione",
                     "entro dieci giorni dalla notifica la società doveva provvedere"):
            self.assertEqual(read(text), ([], ["mood"]), text)

    def test_term_modified_by_the_rest_of_the_sentence(self):
        for text in ("di pagare entro venti giorni dalla notifica, ridotti a dieci in caso di urgenza, la somma",
                     "di pagare entro dieci giorni dalla notifica, prorogati di ulteriori venti, la somma",
                     "entro dieci giorni dalla notifica, termine sospeso fino a nuova comunicazione, la somma"):
            self.assertEqual(read(text), ([], ["mood"]), text)

    def test_only_the_sentence_of_the_clause_is_looked_at(self):
        text = ("di pagare entro dieci giorni dalla notifica del presente atto la somma di € 1.000,00. "
                "Il precedente termine è inutilmente decorso e non è stato prorogato.")
        self.assertEqual(read(text), ([(10, "notification", False)], []))

    def test_plain_continuations_are_still_read(self):
        for text in ("di pagare entro dieci giorni dalla notifica del presente atto la somma di € 1.000,00, con "
                     "avvertimento che in difetto si procederà ad esecuzione forzata",
                     "entro dieci giorni dalla notifica, a mezzo bonifico, l'importo dovuto"):
            self.assertEqual(read(text), ([(10, "notification", False)], []), text)

    def test_through_the_classifier_a_recital_never_becomes_a_computed_deadline(self):
        r = record("STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO\nintima di pagare la somma di € 1.000,00. Si rammenta "
                   "che entro e non oltre dieci giorni dalla notifica il debitore avrebbe potuto proporre opposizione.",
                   subject="Notifica atto di precetto", sender="avv.moscardini@pec.studiomoscardini.example")
        self.assertEqual(r["deadline"], "RECUPERARE")
        self.assertIn("mood", r["recuperare_reasons"]["deadline"])


class ThroughTheClassifier(unittest.TestCase):
    PRECETTO = "STUDIO LEGALE MOSCARDINI\nATTO DI PRECETTO\nINTIMA a FORNACE AURELIA S.R.L. di pagare {} la somma di € 1.000,00."

    def test_output_shape_of_relative_terms_is_unchanged(self):
        r = dl.relative_terms("Si intima di pagare entro il termine di dieci giorni dalla notifica.")
        self.assertEqual(len(r), 1)
        self.assertLessEqual({"days", "raw", "from_event", "conditional", "start"}, set(r[0]))
        self.assertEqual((r[0]["days"], r[0]["conditional"], r[0]["start"]), (10, False, 20))
        self.assertEqual(r[0]["raw"], "entro il termine di dieci giorni dalla notifica")

    def test_new_phrasings_give_the_same_date_as_the_v20_phrasing(self):
        base = record(self.PRECETTO.format("entro il termine di dieci giorni dalla notifica del presente atto"))
        self.assertEqual((base["deadline"], base["deadline_nature"]), ("2026-10-16", "computed"))  # 6 Oct + 10
        for phrase in ("nel termine di giorni dieci dalla notifica del presente atto",
                       "entro e non oltre 10 (dieci) giorni dalla notificazione del presente atto",
                       "non oltre gg. 10 dalla data di notifica"):
            r = record(self.PRECETTO.format(phrase))
            self.assertEqual(r["deadline"], base["deadline"], phrase)
            self.assertEqual([{k: v for k, v in d.items() if k != "source"} for d in r["deadlines"]],
                             [{k: v for k, v in d.items() if k != "source"} for d in base["deadlines"]], phrase)
            self.assertIn(phrase.split(" del presente")[0], r["deadlines"][0]["source"])

    def test_stated_days_are_computed_with_the_policy_of_the_act(self):
        r = record(self.PRECETTO.format("entro venti giorni dalla notifica del presente atto"))
        term = next(t for t in CTX.terms_cfg["terms"] if t["doc_type"] == "atto_precetto")
        want = terms.add_days(CTX.calendar, terms.D(2026, 10, 6), 20, feriale_suspension=False, saturday_rollover=True)
        self.assertEqual((r["deadline"], r["deadlines"][0]["rule_id"]), (want.isoformat(), term["id"]))

    def test_an_unread_clause_never_falls_back_to_the_statutory_default(self):
        """The dangerous silent path: the text states a term v2.1 cannot read, the act has a statutory term."""
        for phrase in ("entro dieci giorni lavorativi dalla notifica del presente atto",
                       "entro due mesi dalla notifica",
                       "entro venti giorni dalla notifica del decreto",
                       "entro 10 (venti) giorni dalla notifica",
                       "entro trenta giorni dalla comunicazione del presente atto"):
            r = record(self.PRECETTO.format(phrase))
            self.assertEqual(r["doc_type"], "atto_precetto")
            self.assertEqual(r["deadline"], "RECUPERARE", phrase)
            self.assertEqual(r["deadlines"] and r["deadlines"][0].get("source"), "statutory default", phrase)
            self.assertIn("could not be parsed", r["recuperare_reasons"]["deadline"])

    def test_text_silent_still_uses_the_statutory_default(self):
        r = record(self.PRECETTO.format("senza indugio"))
        self.assertEqual((r["deadline"], r["deadlines"][0]["source"]), ("2026-10-16", "statutory default"))


class RulesDecide(unittest.TestCase):
    """L7: what a slot value MEANS is in rules/term_clauses.json; changing the rule changes the reading."""

    def test_inline_tests_of_the_rule_file(self):
        self.assertEqual(tc.run_inline_tests(), [])

    def test_moving_a_word_between_rules_changes_the_reading_and_nothing_else(self):
        text = "entro dieci giorni utili dalla notifica. Entro venti giorni liberi dal ricevimento."
        self.assertEqual(read(text), ([], ["qualifier", "qualifier"]))
        tmp = tmpdir("rules-term-clauses")
        shutil.copytree(ROOT / "rules", tmp / "rules")
        path = tmp / "rules" / "term_clauses.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {r["id"]: r for r in data["rules"]}
        by_id["TC-Q02"]["when"]["phrases"].remove("utili")
        by_id["TC-Q01"]["when"]["phrases"].append("utili")
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        got = tc.read(text, tmp / "rules")
        self.assertEqual([(t["days"], t["from_event"]) for t in got["terms"]], [(10, "notification")])
        self.assertEqual([u["why"] for u in got["unread"]], ["qualifier"])
        self.assertEqual(read(text), ([], ["qualifier", "qualifier"]))  # the shipped rules are untouched

    def test_committed_terms_name_the_rules_that_read_them(self):
        t = tc.read("nel termine di giorni dieci dalla notifica del presente atto")["terms"][0]
        self.assertEqual(t["rules"], ["TC-L03", "TC-U01", "TC-A01", "TC-C01"])


if __name__ == "__main__":
    unittest.main()
