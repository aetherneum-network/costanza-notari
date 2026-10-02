"""Phrasing perturbations for the STRESS evaluation suite (semantics unchanged, gold unchanged).

The rule files were written and adjusted against the development corpus. These rewrites use
phrasings the rules have never seen - the stress suite measures what happens then (misses become
RECUPERARE or errors; both are reported). Deterministic: its own RNG, so the main stream is untouched.
"""
import random
import re

REWRITES = [
    (r"entro il termine di (\w+) giorni dalla notifica", r"nel termine di giorni \1 dalla notifica"),
    (r"entro (\w+) giorni dalla notific", r"entro e non oltre \1 giorni dalla notific"),
    (r"udienza del ", "udienza che si terrà il "),
    (r"Importo dovuto: €", "Totale a debito: Euro"),
    (r"la somma di €", "l'importo complessivo di Euro"),
    (r"(\d{2})/(\d{2})/(\d{4})", r"\1-\2-\3"),
    (r"Rif\. pratica:", "Ns. rif.:"),
    (r"^DIFFIDA E MESSA IN MORA$", "LETTERA DI DIFFIDA"),
    (r"^ATTO DI PRECETTO$", "ATTO DI PRECETTO E INTIMAZIONE"),
    (r"La prima rata scade il", "La prima rata dovrà essere corrisposta il"),
    (r"Per conto e nell'interesse di", "In nome e per conto di"),
]


def make(seed: int, p: float = 0.35):
    rnd = random.Random(seed ^ 0x5EED)
    compiled = [(re.compile(a, re.M), b) for a, b in REWRITES]

    def perturb(paragraph: str) -> str:
        for rx, repl in compiled:
            if rx.search(paragraph) and rnd.random() < p:
                paragraph = rx.sub(repl, paragraph)
        return paragraph

    return perturb
