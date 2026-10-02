"""Generate S05 input (deterministic). Debtor: OFFICINE LAGORAI S.R.L. (synthetic).

E1: a precetto authored by Avv. Ilaria Moscardini (CAdES .p7m), on behalf of CARPENTERIE ROVERE S.R.L.,
    TRANSMITTED by the gateway Servizi Notifiche Digitali Esempio S.p.A.
E2: a diffida sent directly by the lawyer's own PEC on behalf of AUTOTRASPORTI GHIAIOLA S.R.L.
Plus six handoff/receipt files whose NAMES point at the wrong author (L5).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios import _envelopes as E  # noqa: E402

DEBTOR_PEC = "officinelagorai@pec.officinelagorai.example"


def main():
    inp = HERE / "input"
    e1 = E.envelope(
        n=501, when=E.rome(2026, 10, 14, 10, 20), sender_display="Servizi Notifiche Digitali Esempio S.p.A.",
        sender_addr="notifiche@pec.notifichedigitali.example", to_addr=DEBTOR_PEC,
        subject="Notifica atto di precetto",
        body=("Messaggio trasmesso tramite il servizio di notifica di Servizi Notifiche Digitali Esempio S.p.A. per "
              "conto dell'Avv. Ilaria Moscardini.\nIl servizio non è responsabile del contenuto del messaggio."),
        lines=["STUDIO LEGALE MOSCARDINI", "", "ATTO DI PRECETTO", "Rif. pratica: PR-CR-5001", "",
               "Per conto e nell'interesse di CARPENTERIE ROVERE S.R.L., con sede in Esempio, PEC",
               "amministrazione@pec.carpenterierovere.example, rappresentata e difesa dall'Avv. Ilaria Moscardini,",
               "premesso che con decreto ingiuntivo n. SYN-DI-5001 emesso il 12/05/2026 è stato ingiunto a",
               "OFFICINE LAGORAI S.R.L. (PEC " + DEBTOR_PEC + ") il pagamento del credito;",
               "INTIMA", "a OFFICINE LAGORAI S.R.L., con sede in Esempio, di pagare entro il termine di dieci giorni",
               "dalla notifica del presente atto la somma di € 18.450,00, oltre interessi e spese.",
               "Esempio, 13/10/2026", "Avv. Ilaria Moscardini"],
        name="atto_precetto.pdf", p7m_identity="lawyer-IM")
    e2 = E.envelope(
        n=502, when=E.rome(2026, 10, 15, 16, 5), sender_display="Avv. Ilaria Moscardini",
        sender_addr="ilaria.moscardini@pec.ordineavvocati-esempio.example", to_addr=DEBTOR_PEC,
        subject="Diffida e messa in mora", body="Si trasmette la diffida allegata.\nAvv. Ilaria Moscardini",
        lines=["STUDIO LEGALE MOSCARDINI", "", "DIFFIDA E MESSA IN MORA", "Rif. pratica: PR-AG-5002", "",
               "Per conto e nell'interesse di AUTOTRASPORTI GHIAIOLA S.R.L., con sede in Esempio, rappresentata e",
               "difesa dall'Avv. Ilaria Moscardini,", "Vi diffido a corrispondere entro quindici giorni dal ricevimento "
               "della presente la somma di € 4.210,00.", "Esempio, 15/10/2026", "Avv. Ilaria Moscardini"],
        name="diffida.pdf")
    E.write_input(inp / "corpus", {"envelopes/2026-10/PEC_S05_E1.eml": e1, "envelopes/2026-10/PEC_S05_E2.eml": e2})
    cfg = {"synthetic": "Scenario S05 - all entities fictitious", "seed": E.SEED, "as_of": "2026-10-21T09:40:00+02:00",
           "debtor": {"canonical": "OFFICINE LAGORAI S.R.L.", "aliases": ["Officine Lagorai S.r.l.", "Officine Lagorai srl"],
                      "pec": [DEBTOR_PEC, "crediti@pec.officinelagorai.example"], "domains": ["officinelagorai.example"]},
           "trust_anchors": "corpus/out/testca/trust", "chunk_size": 40}
    (inp / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = {  # file name suggests one author; the fields say another
        "RCPT_chunk-07_ARC-0231.json": {"id": "ARC-0231", "by": "consolidator", "dissent": "none"},
        "handoff_consolidator_ARC-0232.json": {"id": "ARC-0232", "from": "chunk-02", "to": "consolidator"},
        "consolidator_ARC-0233.json": {"id": "ARC-0233", "from": "chunk-03", "to": "consolidator"},
        "chunk-04_receipt_ARC-0234.json": {"id": "ARC-0234", "by": "consolidator", "dissent": "No dissent."},
        "ARC-0235_by_chunk-05.json": {"id": "ARC-0235", "by": "consolidator", "dissent": "none"},
        "reply_from_consolidator_ARC-0236.json": {"id": "ARC-0236", "from": "chunk-06", "to": "consolidator"},
    }
    (inp / "handoff_files").mkdir(parents=True, exist_ok=True)
    for name, obj in files.items():
        (inp / "handoff_files" / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
