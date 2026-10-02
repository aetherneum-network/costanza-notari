"""Generate S09 input (deterministic). Debtor: OFFICINE LAGORAI S.R.L. (synthetic).
A precetto signed (CAdES .p7m) by Avv. Serena Lupatelli, whose certificate is issued by the
'Esempio UNTRUSTED Test CA' - deliberately absent from the trust list."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios import _envelopes as E  # noqa: E402

DEBTOR_PEC = "officinelagorai@pec.officinelagorai.example"


def main():
    e = E.envelope(
        n=901, when=E.rome(2026, 10, 19, 11, 30), sender_display="Avv. Serena Lupatelli",
        sender_addr="avv.serenalupatelli@pec.legalmail-esempio.example", to_addr=DEBTOR_PEC,
        subject="Notifica atto di precetto", body="Si notifica, ai sensi della L. 53/1994, l'atto allegato.\nAvv. Serena Lupatelli",
        lines=["STUDIO LEGALE LUPATELLI", "", "ATTO DI PRECETTO", "Rif. pratica: PR-FO-9001", "",
               "Per conto e nell'interesse di FORNITURE DELL’ONTANO S.R.L., con sede in Esempio, PEC",
               "ufficio.crediti@pec.fornitureontano.example, rappresentata e difesa dall'Avv. Serena Lupatelli,",
               "INTIMA", "a OFFICINE LAGORAI S.R.L. di pagare entro il termine di dieci giorni dalla notifica del presente",
               "atto la somma di € 6.930,00, oltre interessi e spese.", "Esempio, 18/10/2026", "Avv. Serena Lupatelli"],
        name="atto_precetto.pdf", p7m_identity="lawyer-SL")
    inp = HERE / "input"
    E.write_input(inp / "corpus", {"envelopes/2026-10/PEC_S09_P7M.eml": e})
    cfg = {"synthetic": "Scenario S09 - all entities fictitious", "seed": E.SEED, "as_of": "2026-10-21T09:40:00+02:00",
           "debtor": {"canonical": "OFFICINE LAGORAI S.R.L.", "aliases": ["Officine Lagorai S.r.l."],
                      "pec": [DEBTOR_PEC], "domains": ["officinelagorai.example"]},
           "trust_anchors": "corpus/out/testca/trust", "chunk_size": 40}
    (inp / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
