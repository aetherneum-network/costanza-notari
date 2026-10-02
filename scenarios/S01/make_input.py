"""Generate S01 input: 200 classified records (synthetic) of the corpus of Fornace Aurelia S.r.l.

ARC-0412 carries the Appendix A figures: notice of assessment, 12380.00, 2026-11-14,
AGENZIA ESEMPIO RISCOSSIONE. Deterministic (seed 412).
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTIES = ["AGENZIA ESEMPIO RISCOSSIONE", "OFFICINE LAGORAI S.R.L.", "TESSITURE MONTEVERDE S.R.L.",
           "CANTINE BELVEDERE S.P.A.", "ISTITUTO ESEMPIO PREVIDENZA", "CARPENTERIE ROVERE S.R.L."]
TYPES = ["cartella_pagamento", "avviso_accertamento", "atto_precetto", "decreto_ingiuntivo", "avviso_addebito"]


def main():
    rnd = random.Random(412)
    recs = []
    for i in range(301, 501):
        recs.append({"record_id": f"ARC-{i:04d}", "doc_type": rnd.choice(TYPES),
                     "amount_due": f"{rnd.randint(30000, 9000000) / 100:.2f}",
                     "deadline": f"2026-{rnd.randint(11, 12)}-{rnd.randint(1, 28):02d}",
                     "party_entity": rnd.choice(PARTIES), "recuperare_fields": []})
    r = next(x for x in recs if x["record_id"] == "ARC-0412")
    r.update({"doc_type": "avviso_accertamento", "amount_due": "12380.00", "deadline": "2026-11-14",
              "party_entity": "AGENZIA ESEMPIO RISCOSSIONE"})
    (HERE / "input").mkdir(exist_ok=True)
    with open(HERE / "input" / "records.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for x in recs:
            fh.write(json.dumps(x, sort_keys=True) + "\n")
    (HERE / "input" / "fault_plan.json").write_text(json.dumps(
        {"note": "TEST ONLY - simulates the consolidator's transcription error of Appendix A, L1",
         "transpose": [{"record_id": "ARC-0412", "field": "amount_due"}]}, indent=2) + "\n", encoding="utf-8",
        newline="\n")


if __name__ == "__main__":
    main()
