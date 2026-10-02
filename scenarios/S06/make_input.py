"""Generate S06 input (deterministic): four notices to the synthetic debtor CANTINE BELVEDERE S.P.A.
20 date items (17 written dates + 3 relative terms), of which 6 are actionable or computed."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios import _envelopes as E  # noqa: E402

DEBTOR_PEC = "contabilita@pec.cantinebelvedere.example"
NOTICES = {
    "envelopes/2026-10/PEC_S06_N1.eml": dict(
        n=601, when=E.rome(2026, 10, 16, 10, 0), sender_display="Carpenterie Rovere S.r.l.",
        sender_addr="amministrazione@pec.carpenterierovere.example", subject="Diffida e messa in mora",
        body="In allegato la comunicazione in oggetto.", name="diffida.pdf",
        lines=["CARPENTERIE ROVERE S.R.L.", "", "DIFFIDA E MESSA IN MORA", "Rif. pratica: PR-CR-6001", "",
               "Spett.le CANTINE BELVEDERE S.P.A.,",
               "rileviamo che la fattura n. 208 del 14/04/2026, scaduta il 14/06/2026, risulta ancora insoluta.",
               "Il termine originariamente fissato al 24/10/2026 deve intendersi superato dalla presente.",
               "Con la presente Vi diffidiamo e costituiamo formalmente in mora, invitandoVi a corrispondere",
               "entro quindici giorni dal ricevimento della presente la somma di € 9.870,00.",
               "Esempio, 16/10/2026", "CARPENTERIE ROVERE S.R.L. - Il legale rappresentante"]),
    "envelopes/2026-10/PEC_S06_N2.eml": dict(
        n=602, when=E.rome(2026, 10, 2, 10, 0), sender_display="Agenzia Esempio Riscossione",
        sender_addr="notifica.cartelle@pec.agenzia-riscossione.example", subject="Esito istanza di rateizzazione",
        body="Si notifica il documento allegato.", name="piano_rateizzazione.pdf",
        lines=["AGENZIA ESEMPIO RISCOSSIONE", "", "PIANO DI RATEIZZAZIONE", "Rif. pratica: PR-RAT-6002",
               "Rif. atto: EX-6002 del 02/10/2026", "",
               "In accoglimento dell'istanza presentata il 10/09/2026 da CANTINE BELVEDERE S.P.A., è concessa la",
               "rateizzazione del debito.",
               "Importo complessivo rateizzato: € 40.982,40. Importo della rata: € 3.415,20. Numero rate: 12.",
               "La prima rata scade il 30/11/2026.",
               "In caso di mancato pagamento entro il 28/10/2026 della rata residua del piano precedente, il presente",
               "piano non avrà effetto.",
               "Qualora la prima rata non sia versata entro il 15/12/2026, il piano si intenderà revocato.",
               "AGENZIA ESEMPIO RISCOSSIONE - Il Responsabile del procedimento"]),
    "envelopes/2026-10/PEC_S06_N3.eml": dict(
        n=603, when=E.rome(2026, 10, 9, 11, 0), sender_display="Avv. Ilaria Moscardini",
        sender_addr="ilaria.moscardini@pec.ordineavvocati-esempio.example", subject="Notifica atto di citazione",
        body="Si notifica, ai sensi della L. 53/1994, l'atto allegato.\nAvv. Ilaria Moscardini", name="citazione.pdf",
        lines=["STUDIO LEGALE MOSCARDINI", "", "ATTO DI CITAZIONE", "Rif. pratica: PR-TM-6003", "",
               "Per conto e nell'interesse di TESSITURE MONTEVERDE S.R.L., con sede in Esempio, rappresentata e",
               "difesa dall'Avv. Ilaria Moscardini,",
               "premesso che con contratto stipulato il 18/01/2025 TESSITURE MONTEVERDE S.R.L. forniva a CANTINE",
               "BELVEDERE S.P.A. tessuti per la somma di € 27.300,00, come da fattura del 05/03/2025;",
               "che il pagamento doveva avvenire entro il 30/06/2025 e non è avvenuto;",
               "CITA", "CANTINE BELVEDERE S.P.A., in persona del legale rappresentante, a comparire all'udienza del",
               "12/03/2027 innanzi al Tribunale di Esempio.", "Esempio, 08/10/2026", "Avv. Ilaria Moscardini"]),
    "envelopes/2026-10/PEC_S06_N4.eml": dict(
        n=604, when=E.rome(2026, 10, 1, 11, 0), sender_display="Istituto Esempio Previdenza",
        sender_addr="direzione.esempio@pec.previdenza-esempio.example", subject="Notifica avviso di addebito",
        body="Si notifica il documento allegato.", name="avviso_addebito.pdf",
        lines=["ISTITUTO ESEMPIO PREVIDENZA", "Direzione Provinciale di Esempio", "",
               "AVVISO DI ADDEBITO N. SYN-AVA-6004", "Rif. pratica: PR-ADD-6004", "Rif. atto: EX-6004 del 30/09/2026", "",
               "Contributi previdenziali dovuti per il periodo 01/2025 - 12/2025, come da verbale di accertamento",
               "del 12/05/2026.", "Importo dovuto: € 7.820,00.",
               "Il pagamento deve essere effettuato entro sessanta giorni dalla notifica.",
               "Entro quaranta giorni dalla notifica può essere proposta opposizione innanzi al Giudice del lavoro.",
               "Termine ultimo del 20/11/2026 per la richiesta di rateizzazione agevolata.",
               "ISTITUTO ESEMPIO PREVIDENZA - Il Responsabile del procedimento"]),
}


def main():
    inp = HERE / "input"
    envs = {rel: E.envelope(to_addr=DEBTOR_PEC, **spec) for rel, spec in NOTICES.items()}
    E.write_input(inp / "corpus", envs)
    cfg = {"synthetic": "Scenario S06 - all entities fictitious", "seed": E.SEED, "as_of": "2026-10-21T09:40:00+02:00",
           "debtor": {"canonical": "CANTINE BELVEDERE S.P.A.", "aliases": ["Cantine Belvedere S.p.A.", "Cantine Belvedere spa"],
                      "pec": [DEBTOR_PEC], "domains": ["cantinebelvedere.example"]},
           "trust_anchors": "corpus/out/testca/trust", "chunk_size": 40}
    (inp / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
