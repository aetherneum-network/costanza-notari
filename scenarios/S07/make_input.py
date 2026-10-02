"""Generate S07 input (deterministic): 12 notices to the synthetic debtor TESSITURE MONTEVERDE S.R.L.
(4 cartelle, 2 intimazioni, 1 piano di rateizzazione, 2 avvisi di accertamento, 1 diffida,
1 comunicazione di cancelleria, 1 sollecito) and the one-rule patch of the scenario."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios import _envelopes as E  # noqa: E402

DEBTOR_PEC = "amministrazione@pec.tessituremonteverde.example"
AG = ("Agenzia Esempio Riscossione", "notifica.cartelle@pec.agenzia-riscossione.example", "AGENZIA ESEMPIO RISCOSSIONE")


def agency(n, day, title, subject, amount, term_word, extra=None):
    lines = [AG[2], "", title, f"Rif. pratica: PR-AR-7{n:03d}", f"Rif. atto: EX-7{n:03d} del {day:02d}/10/2026", "",
             "Intestatario: TESSITURE MONTEVERDE S.R.L.", f"Importo dovuto: € {amount}."]
    lines += extra or [f"Si intima il pagamento entro {term_word} giorni dalla notificazione del presente atto."]
    lines += [f"{AG[2]} - Il Responsabile del procedimento"]
    return dict(n=700 + n, when=E.rome(2026, 10, day, 10, 0), sender_display=AG[0], sender_addr=AG[1], subject=subject,
                body="Si notifica il documento allegato.", lines=lines, name=f"atto_{n}.pdf")


def main():
    specs = {
        "N01": agency(1, 1, "CARTELLA DI PAGAMENTO N. SYN-068-2026-700001", "Notifica cartella di pagamento", "1.240,00", "sessanta"),
        "N02": agency(2, 2, "CARTELLA DI PAGAMENTO N. SYN-068-2026-700002", "Notifica cartella di pagamento", "8.310,55", "sessanta"),
        "N03": agency(3, 5, "CARTELLA DI PAGAMENTO N. SYN-068-2026-700003", "Notifica cartella di pagamento", "612,90", "sessanta"),
        "N04": agency(4, 6, "CARTELLA DI PAGAMENTO N. SYN-068-2026-700004", "Notifica cartella di pagamento", "22.004,10", "sessanta"),
        "N05": agency(5, 7, "INTIMAZIONE DI PAGAMENTO N. SYN-INT-70005", "Notifica intimazione di pagamento", "3.100,00", "cinque"),
        "N06": agency(6, 8, "INTIMAZIONE DI PAGAMENTO N. SYN-INT-70006", "Notifica intimazione di pagamento", "940,00", "cinque"),
        "N07": agency(7, 9, "PIANO DI RATEIZZAZIONE", "Esito istanza di rateizzazione", "0,00", None,
                      extra=["Importo della rata: € 1.020,00.", "La prima rata scade il 30/11/2026."]),
        "N08": dict(n=708, when=E.rome(2026, 10, 12, 11, 0), sender_display="Agenzia Esempio Entrate",
                    sender_addr="dp.esempio@pec.agenzia-entrate-esempio.example", subject="Notifica avviso di accertamento",
                    body="Si notifica il documento allegato.", name="accertamento.pdf",
                    lines=["AGENZIA ESEMPIO ENTRATE", "Direzione Provinciale di Esempio", "",
                           "AVVISO DI ACCERTAMENTO N. SYN-AVV-2026-70008", "Rif. pratica: PR-AE-7008", "",
                           "Importo dovuto: € 15.300,00.",
                           "Avverso il presente atto può essere proposto ricorso entro sessanta giorni dalla notificazione.",
                           "AGENZIA ESEMPIO ENTRATE - Il Capo Ufficio"]),
        "N09": dict(n=709, when=E.rome(2026, 10, 13, 11, 0), sender_display="Comune di Esempio",
                    sender_addr="tributi@pec.comune-esempio.example", subject="Notifica avviso di accertamento",
                    body="Si notifica il documento allegato.", name="imu.pdf",
                    lines=["COMUNE DI ESEMPIO", "Ufficio Tributi", "", "AVVISO DI ACCERTAMENTO IMU N. SYN-IMU-70009",
                           "Rif. pratica: PR-IMU-7009", "", "Importo dovuto: € 2.450,00.",
                           "Avverso il presente atto può essere proposto ricorso entro sessanta giorni dalla notificazione.",
                           "COMUNE DI ESEMPIO - Il Funzionario responsabile"]),
        "N10": dict(n=710, when=E.rome(2026, 10, 14, 9, 0), sender_display="Officine Lagorai S.r.l.",
                    sender_addr="crediti@pec.officinelagorai.example", subject="Diffida e messa in mora",
                    body="In allegato la comunicazione in oggetto.", name="diffida.pdf",
                    lines=["OFFICINE LAGORAI S.R.L.", "", "DIFFIDA E MESSA IN MORA", "Rif. pratica: PR-OL-7010", "",
                           "Vi invitiamo a corrispondere entro quindici giorni dal ricevimento della presente la somma di € 5.600,00.",
                           "OFFICINE LAGORAI S.R.L. - Il legale rappresentante"]),
        "N11": dict(n=711, when=E.rome(2026, 10, 15, 12, 0), sender_display="Tribunale di Esempio - Cancelleria Contenzioso",
                    sender_addr="contenzioso@civile.tribunale.example", subject="Comunicazione di cancelleria",
                    body="Comunicazione telematica della cancelleria.", name="provvedimento.pdf",
                    lines=["TRIBUNALE DI ESEMPIO", "Cancelleria Contenzioso", "", "COMUNICAZIONE DI CANCELLERIA",
                           "Rif. pratica: PR-RG-SYN-2026-7011", "",
                           "Procedimento: causa promossa da CARPENTERIE ROVERE S.R.L. contro TESSITURE MONTEVERDE S.R.L.",
                           "Si comunica che il Giudice ha rinviato l'udienza al 14/01/2027.",
                           "Il Cancelliere - TRIBUNALE DI ESEMPIO"]),
        "N12": dict(n=712, when=E.rome(2026, 10, 16, 12, 0), sender_display="Cantine Belvedere S.p.A.",
                    sender_addr="contabilita@pec.cantinebelvedere.example", subject="Sollecito di pagamento",
                    body="In allegato la comunicazione in oggetto.", name="sollecito.pdf",
                    lines=["CANTINE BELVEDERE S.P.A.", "", "SOLLECITO DI PAGAMENTO", "Rif. pratica: PR-CB-7012", "",
                           "Vi ricordiamo che la fattura n. 77 per un importo di € 2.145,90 risulta ancora insoluta.",
                           "CANTINE BELVEDERE S.P.A. - Ufficio Amministrazione"]),
    }
    envs = {f"envelopes/2026-10/PEC_S07_{k}.eml": E.envelope(to_addr=DEBTOR_PEC, **v) for k, v in specs.items()}
    inp = HERE / "input"
    E.write_input(inp / "corpus", envs)
    cfg = {"synthetic": "Scenario S07 - all entities fictitious", "seed": E.SEED, "as_of": "2026-10-21T09:40:00+02:00",
           "debtor": {"canonical": "TESSITURE MONTEVERDE S.R.L.", "aliases": ["Tessiture Monteverde S.r.l."],
                      "pec": [DEBTOR_PEC], "domains": ["tessituremonteverde.example"]},
           "trust_anchors": "corpus/out/testca/trust", "chunk_size": 40}
    (inp / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")
    (inp / "rule_patch.json").write_text(json.dumps({
        "file": "area.json", "rule_id": "R-014", "then": {"area": "tax"},
        "rationale": "the office decides cartelle are handled by the tax desk (Appendix A, L7 example)"}, indent=2) + "\n",
        encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
