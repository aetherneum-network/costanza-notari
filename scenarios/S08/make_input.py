"""Generate S08 input (deterministic): a tree spec with 40 envelopes, 15 of which exceed 300 characters
once materialised under build/scenarios/S08/tree, with accented names (Società Agricola Valle dell’Èrto)."""
import json
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_NAME = "Società Agricola Valle dell’Èrto"


def main():
    paths = []
    for i in range(25):
        paths.append(f"{ROOT_NAME}/2026/Ottobre/atto_{i:02d} – notifica.eml")
    deep = "/".join([ROOT_NAME, "2026", "Ottobre", "Procedimenti esecutivi e monitori pendenti presso il Tribunale di Esempio",
                     "Pratiche della Società Agricola Valle dell’Èrto S.S. – fascicolo principale e allegati",
                     "Corrispondenza certificata ricevuta, già protocollata, perché urgente"])
    for i in range(15):
        paths.append(f"{deep}/Decreto ingiuntivo n. SYN-DI-8{i:03d} – Società Agricola Valle dell’Èrto S.S. – "
                     f"notifica ai sensi della L. 53-1994 – copia conforme.eml")
    paths = [unicodedata.normalize("NFC", p) for p in paths]
    spec = {"note": "materialised by check.py under build/scenarios/S08/tree (never committed: > 260 chars)",
            "paths": paths,
            "name_variants": ["Società Agricola Valle dell'Èrto S.S.", "SOCIETÀ AGRICOLA VALLE DELL’ÈRTO S.S.",
                              "Societa' Agricola Valle dell'Erto s.s.",
                              unicodedata.normalize("NFD", "Società Agricola Valle dell’Èrto S.S.")]}
    (HERE / "input").mkdir(exist_ok=True)
    (HERE / "input" / "tree_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8", newline="\n")
    (HERE / "input" / "handoff_single_backslashes.json").write_text(
        '{"id": "ARC-0801", "from": "chunk-01", "to": "consolidator", "source": "C:\\Users\\Archivio\\Èrto\\atto.eml",\n'
        ' "anchors": [{"k": "counterparty", "v": "SOCIETÀ AGRICOLA VALLE DELL’ÈRTO S.S."}]}\n', encoding="utf-8",
        newline="\n")


if __name__ == "__main__":
    main()
