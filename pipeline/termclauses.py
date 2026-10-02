"""Structural reading of relative term clauses (v2.1): "entro N giorni dalla notifica".

v2.0 read one fixed phrasing with one regular expression and abstained on everything
else. v2.1 reads the clause slot by slot and commits only when every slot is
recognised by a rule of ``rules/term_clauses.json``:

    LEAD-IN     is it a last useful day?          entro | entro e non oltre | nel termine di | ...
    QUANTITY    how many, of what                  dieci giorni | giorni 10 | 10 (dieci) gg.
    QUALIFIER   does it change the count?          naturali e consecutivi (no) | lavorativi (yes)
    ANCHOR      an event the envelope can date     notifica | notificazione | ricevimento | ricezione
    COMPLEMENT  is it THIS act's notification?     del presente atto (yes) | del precetto (unknown)
    MOOD        conditional / recital              qualora ... | doveva ...

The QUANTITY + ANCHOR - the part where a misreading yields a wrong date - is read twice, by
two readers written differently on purpose:

* reader A: one regular-expression grammar; number words come from a table *generated* by
  :func:`spell` (int -> words);
* reader B: a token scanner that starts from the anchor word and walks leftwards; number words
  are *parsed* by :func:`parse_cardinal` (words -> int).

A term is committed only when both readers return the same days, unit and position for the same
anchor. Everything else that looks like a term (a third, deliberately loose, detector) is
reported as *unread* with a reason, and the caller turns it into ``RECUPERARE``.
Code extracts; rules decide (L7). Null is honest; a guess is a defect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .lib import jsonio
from .rules_engine import RULES_DIR

# ------------------------------------------------------------------ Italian cardinals, twice
_ONES = ("", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici",
         "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove")
_TENS = ("", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta")
MAX_N = 999


def spell(n: int) -> str:
    """int -> Italian cardinal, 1..999 (generating direction; feeds reader A's table)."""
    if not 1 <= n <= MAX_N:
        raise ValueError(n)
    h, r = divmod(n, 100)
    out = ""
    if h:
        out = ("" if h == 1 else _ONES[h]) + "cento"
        if 80 <= r <= 89:
            out = out[:-1]  # centottanta
    if r < 20:
        return out + _ONES[r]
    t, u = divmod(r, 10)
    w = _TENS[t]
    if u in (1, 8):
        w = w[:-1]  # ventuno, ventotto
    return out + w + ("tré" if u == 3 else _ONES[u])


@lru_cache(maxsize=None)
def number_table() -> dict:
    """Every accepted written form -> value (reader A)."""
    table = {}
    for n in range(1, MAX_N + 1):
        w = spell(n)
        forms = {w, w.replace("é", "e")}
        h, r = divmod(n, 100)
        if h and (80 <= r <= 89 or r == 8):
            head = ("" if h == 1 else _ONES[h]) + "cento"
            tail = spell(r)
            forms |= {head + tail, head[:-1] + tail}  # centoottanta / centottanta, centootto / centotto
        for f in forms:
            table[f] = n
    table["un"] = 1
    return table


_P_ONES = {w: i for i, w in enumerate(_ONES) if w}
_P_ONES["un"] = 1
_P_TENS = {w: i * 10 for i, w in enumerate(_TENS) if w}


def _under_100(s: str) -> int | None:
    if s in _P_ONES:
        return _P_ONES[s]
    for w, v in _P_TENS.items():
        if s == w:
            return v
        for stem in (w, w[:-1]):
            if s.startswith(stem):
                u = _P_ONES.get(s[len(stem):])
                if u is None or not 1 <= u <= 9 or s[len(stem):] == "un":
                    continue
                if (stem != w) != (u in (1, 8)):
                    continue  # elision is mandatory before uno/otto and forbidden elsewhere
                return v + u
    return None


def parse_cardinal(word: str) -> int | None:
    """Italian cardinal -> int (parsing direction; reader B). None when it is not a cardinal 1..999."""
    s = (word or "").strip().lower().replace("é", "e")
    if not s or not s.isalpha():
        return None
    r = _under_100(s)
    if r is not None:
        return r
    for h in range(1, 10):
        head = ("" if h == 1 else _ONES[h]) + "cento"
        if s == head:
            return h * 100
        if s.startswith(head):
            r = _under_100(s[len(head):])
            if r is not None:
                return h * 100 + r
        if s.startswith(head[:-1] + "ott"):
            r = _under_100(s[len(head) - 1:])
            if r is not None and (80 <= r <= 89 or r == 8):
                return h * 100 + r
    return None


# ------------------------------------------------------------------ rules
_AFTER = ("successivi", "successivo", "seguenti")
_PREP = r"(?:dall['’]\s*|dalla\s+|dal\s+|(?:successiv[oi]|seguenti)\s+(?:all['’]\s*|alla\s+|al\s+))"
_DATA = r"(?:data\s+d(?:i|ella|el)\s+)?"
# any "from ..." complement, whatever the event ("dal deposito", "dalla data della presente", "da oggi");
# "dalle ore 9" and "da parte di" are not events
_ANY_PREP = (r"(?:\b(?:dall['’]|dalla|dallo|dal|dai|dagli|da(?!\s+parte\b))\b|"
             r"\b(?:successiv[oi]|seguenti)\s+(?:all['’]|alla|allo|al|ai|agli|alle|a)\b)")
_FILL5 = r"(?:\s*,?\s*[\w()’']+){0,5}?\s*,?\s*"
_FILL3 = r"(?:\s*,?\s*[\w()’']+){0,3}?\s*,?\s*"
# "il giorno 12 novembre": a singular unit followed by a number is a calendar day, not a quantity
_SINGULAR_DAY = ("giorno",)
_TOK = re.compile(r"\d+|[A-Za-zÀ-ÖØ-öø-ÿ]+|\S")


@dataclass(frozen=True)
class _Cfg:
    version: str
    units: dict            # word -> (rule id, modelled)
    anchors: tuple         # (rule id, compiled fullmatch regex, event)
    lead_ins: tuple        # (rule id, compiled regex anchored at the end, polarity)
    qualifiers: dict       # phrase -> (rule id, effect)
    complements: tuple     # (rule id, compiled regex anchored at the start, refers_to)
    moods: tuple           # (rule id, compiled regex, mood, side: "before" the lead-in | "after" the anchor)
    rx_a: re.Pattern
    rx_loose_anchor: re.Pattern
    rx_loose_any: re.Pattern
    qual_tokens: frozenset

    def anchor_event(self, word: str):
        for rid, rx, event in self.anchors:
            if rx.fullmatch(word):
                return rid, event
        return None


@lru_cache(maxsize=None)
def config(rules_dir=None) -> _Cfg:
    data = jsonio.read((rules_dir or RULES_DIR) / "term_clauses.json")
    by = {}
    for r in data["rules"]:
        by.setdefault(r["slot"], []).append(r)
    units = {w: (r["id"], bool(r["then"].get("modelled"))) for r in by["unit"] for w in r["when"]["words"]}
    anchors = tuple((r["id"], re.compile(r["when"]["regex"], re.I), r["then"]["event"]) for r in by["anchor"])
    lead_ins = tuple((r["id"], re.compile(r"(?<![\w’'])(?:" + r["when"]["regex"] + r")\s+$", re.I),
                      r["then"]["polarity"]) for r in by["lead_in"])
    qualifiers = {p: (r["id"], r["then"]["effect"]) for r in by["qualifier"] for p in r["when"]["phrases"]}
    complements = tuple((r["id"], re.compile(r"\s*(?:" + r["when"]["regex"] + ")", re.I), r["then"]["refers_to"])
                        for r in by["complement"])
    moods = tuple((r["id"], re.compile(r["when"]["regex"], re.I), r["then"]["mood"], r["when"].get("side", "before"))
                  for r in by["mood"])
    num = r"(?:\d{1,3}|" + "|".join(sorted(number_table(), key=len, reverse=True)) + r")"
    unit = "(?:" + "|".join(sorted(units, key=len, reverse=True)) + ")"
    qual = "(?:" + "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in sorted(qualifiers, key=len, reverse=True)) + ")"
    anch = "(?:" + "|".join(r["when"]["regex"] for r in by["anchor"]) + ")"
    qty = (rf"(?P<qty>(?<![\w.,/-])(?P<n1>{num})(?:\s*\(\s*(?P<p1>{num})\s*\))?\s+(?P<u1>{unit})\b\.?"
           rf"|(?<![\w’'])(?P<u2>{unit})\b\.?\s+(?P<n2>{num})\b(?:\s*\(\s*(?P<p2>{num})\s*\))?)")
    gap = rf"(?:\s*,?\s*{qual}\b)*\s*,?\s*"
    rx_a = re.compile(qty + rf"(?P<gap>{gap})(?P<prep>{_PREP}){_DATA}(?P<a>{anch})\b", re.I)
    rx_loose_anchor = re.compile(rf"(?<![\w’'])(?P<u>{unit})\b\.?{_FILL5}(?P<prep>{_PREP}){_DATA}{anch}\b", re.I)
    rx_loose_any = re.compile(
        rf"(?:(?<![\w.,/-]){num}(?:\s*\(\s*{num}\s*\))?\s+(?P<u1>{unit})\b\.?|(?<![\w’'])(?P<u2>{unit})\b\.?\s+{num}\b"
        rf"(?:\s*\(\s*{num}\s*\))?){_FILL3}(?P<prep>{_ANY_PREP})", re.I)
    qual_tokens = frozenset(tok.lower() for p in qualifiers for tok in p.split())
    return _Cfg(data["version"], units, anchors, lead_ins, qualifiers, complements, moods, rx_a,
                rx_loose_anchor, rx_loose_any, qual_tokens)


# ------------------------------------------------------------------ reader A (regular-expression grammar)
def _num_a(s: str | None) -> int | None:
    if s is None:
        return None
    s = s.lower()
    return int(s) if s.isdigit() else number_table().get(s)


def reader_a(t: str, cfg: _Cfg) -> dict:
    out = {}
    for m in cfg.rx_a.finditer(t):
        main, par = _num_a(m.group("n1") or m.group("n2")), m.group("p1") or m.group("p2")
        conflict = par is not None and _num_a(par) != main
        out[m.start("prep")] = {"days": None if conflict else main, "conflict": conflict,
                                "unit": (m.group("u1") or m.group("u2")).lower(), "qty_start": m.start("qty"),
                                "qty_end": m.end("qty"), "anchor": m.group("a").lower(), "anchor_end": m.end("a")}
    return out


# ------------------------------------------------------------------ reader B (token scanner, anchor first)
def _num_b(w: str) -> int | None:
    if w.isdigit():
        return int(w) if len(w) <= 3 else None
    return parse_cardinal(w)


def _group_ending_at(low: list, e: int):
    """A number, optionally repeated in brackets, whose last token is ``e``: (value, conflict, first token)."""
    if e >= 3 and low[e] == ")" and low[e - 2] == "(":
        main, par = _num_b(low[e - 3]), _num_b(low[e - 1])
        if main is None or par is None:
            return None
        return (main if main == par else None), main != par, e - 3
    if e < 0:
        return None
    main = _num_b(low[e])
    return None if main is None else (main, False, e)


def reader_b(t: str, cfg: _Cfg) -> dict:
    toks = [(m.group(0), m.start(), m.end()) for m in _TOK.finditer(t)]
    low = [x[0].lower() for x in toks]
    out = {}
    for i, w in enumerate(low):
        if not w[0].isalpha() or cfg.anchor_event(w) is None:
            continue
        j = i - 1
        if j >= 1 and low[j] in ("di", "della", "del") and low[j - 1] == "data":
            j -= 2
        if j >= 0 and low[j] in ("dalla", "dal"):
            p = j
        elif j >= 1 and low[j] in ("'", "’") and low[j - 1] == "dall":
            p = j - 1
        elif j >= 1 and low[j] in ("alla", "al") and low[j - 1] in _AFTER:
            p = j - 1
        elif j >= 2 and low[j] in ("'", "’") and low[j - 1] == "all" and low[j - 2] in _AFTER:
            p = j - 2
        else:
            continue  # "relata di notifica", "la notifica": not the anchor of a term
        k = p - 1
        while k >= 0 and (low[k] == "," or low[k] in cfg.qual_tokens):
            k -= 1
        if k < 0:
            continue
        last = k
        if low[k] == "." and k >= 1 and low[k - 1] in cfg.units:
            k -= 1
        if low[k] in cfg.units:                       # NUMBER UNIT
            grp = _group_ending_at(low, k - 1)
            if grp is None:
                continue
            unit, first = low[k], grp[2]
        else:                                         # UNIT NUMBER
            if last != k:
                continue
            grp = _group_ending_at(low, k)
            if grp is None:
                continue
            u = grp[2] - 1
            if u >= 1 and low[u] == "." and low[u - 1] in cfg.units:
                u -= 1
            if u < 0 or low[u] not in cfg.units:
                continue
            unit, first = low[u], u
        out[toks[p][1]] = {"days": grp[0], "conflict": grp[1], "unit": unit, "qty_start": toks[first][1],
                           "qty_end": toks[last][2], "anchor": w, "anchor_end": toks[i][2]}
    return out


# ------------------------------------------------------------------ gates (shared; they can only abstain)
_SENTENCE_END = re.compile(r"[.;:!?](?=\s+[A-ZÀ-Ý\"«(])|;")


def _gate(t: str, r: dict, cfg: _Cfg) -> tuple[str | None, dict]:
    """Return (reason the clause is unread | None, facts)."""
    facts = {}
    if r["conflict"] or r["days"] is None or r["days"] < 1:
        return "number", facts
    rid, modelled = cfg.units[r["unit"]]
    facts["unit_rule"] = rid
    if not modelled:
        return "unit", facts
    gap = t[r["qty_end"]:r["prep_start"]]
    rest = re.sub(r"\s+", " ", gap.replace(",", " ")).strip().lower()
    while rest:
        for ph in sorted(cfg.qualifiers, key=len, reverse=True):
            if rest == ph or rest.startswith(ph + " "):
                if cfg.qualifiers[ph][1] != "none":
                    return "qualifier", facts
                rest = rest[len(ph):].strip()
                break
        else:
            return "qualifier", facts
    lead = None
    for rid, rx, polarity in cfg.lead_ins:
        m = rx.search(t[:r["qty_start"]])
        if m:
            lead = (rid, polarity, m.start())
            break
    if lead is None or lead[1] != "deadline":
        return "lead_in", facts
    facts["lead_in_rule"], facts["lead_start"] = lead[0], lead[2]
    for rid, rx, refers in cfg.complements:
        if rx.match(t[r["anchor_end"]:]):
            if refers != "this_act":
                return "complement", facts
            facts["complement_rule"] = rid
            break
    before = t[max(0, lead[2] - 120):lead[2]]
    after = _SENTENCE_END.split(t[r["anchor_end"]:r["anchor_end"] + 200], maxsplit=1)[0]
    facts["conditional"] = False
    for rid, rx, mood, side in cfg.moods:
        if rx.search(after if side == "after" else before):
            if mood == "conditional":
                facts["conditional"], facts["mood_rule"] = True, rid
                break
            return "mood", facts
    return None, facts


def read(text: str, rules_dir=None) -> dict:
    """Read every relative term of ``text``.

    Returns ``{"terms": [...], "unread": [...]}``. ``terms``: clauses on which both readers agree and
    every slot is recognised (``days``, ``from_event``, ``conditional``, ``raw``, ``start``, ``rules``).
    ``unread``: everything else that looks like a term, with ``why`` in
    {readers_disagree, number, unit, qualifier, lead_in, anchor, complement, mood, structure}.
    """
    cfg = config(rules_dir)
    t = re.sub(r"\s+", " ", text or "").strip()
    a, b = reader_a(t, cfg), reader_b(t, cfg)
    terms, unread, settled = [], [], set()
    for pos in sorted(set(a) | set(b)):
        ra, rb = a.get(pos), b.get(pos)
        settled.add(pos)
        one = ra or rb
        raw = t[one["qty_start"]:one["anchor_end"]]
        if ra is None or rb is None or any(ra[k] != rb[k] for k in ("days", "conflict", "unit", "qty_start", "anchor")):
            unread.append({"raw": raw, "why": "readers_disagree", "start": pos})
            continue
        r = {**rb, "prep_start": pos}
        why, facts = _gate(t, r, cfg)
        if why:
            unread.append({"raw": raw, "why": why, "start": pos})
            continue
        arule, event = cfg.anchor_event(r["anchor"])
        terms.append({"days": r["days"], "raw": t[facts["lead_start"]:r["anchor_end"]], "from_event": event,
                      "conditional": facts["conditional"], "start": facts["lead_start"],
                      "rules": [x for x in (facts.get("lead_in_rule"), facts.get("unit_rule"), arule,
                                            facts.get("complement_rule"), facts.get("mood_rule")) if x]})
    # the loose detector: anything else that looks like a term must not be ignored
    for rx, why in ((cfg.rx_loose_anchor, "structure"), (cfg.rx_loose_any, "anchor")):
        for m in rx.finditer(t):
            pos = m.start("prep")
            if pos in settled:
                continue
            gd = m.groupdict()
            if why == "anchor" and (gd.get("u2") or "").lower() in _SINGULAR_DAY:
                continue
            settled.add(pos)
            unit = (gd.get("u") or gd.get("u1") or gd.get("u2") or "").lower()
            if why == "structure" and unit in cfg.units and not cfg.units[unit][1]:
                why_here = "unit"
            else:
                why_here = why
            unread.append({"raw": t[m.start():m.end()], "why": why_here, "start": pos})
    terms.sort(key=lambda x: x["start"])
    unread.sort(key=lambda x: x["start"])
    return {"terms": terms, "unread": unread}


def run_inline_tests(rules_dir=None) -> list[str]:
    """The tests carried by each rule of rules/term_clauses.json. Empty list = all pass."""
    data = jsonio.read((rules_dir or RULES_DIR) / "term_clauses.json")
    failures = []
    for r in data["rules"]:
        for tc in r["tests"]:
            got = read(tc["input"]["text"], rules_dir)
            terms = [[x["days"], x["from_event"], x["conditional"]] for x in got["terms"]]
            why = [x["why"] for x in got["unread"]]
            if terms != tc["expect"]["terms"] or why != tc["expect"]["unread"]:
                failures.append(f"term_clauses.json:{r['id']}:{tc['id']}: got terms={terms} unread={why}")
            elif tc["expect"]["terms"] and not any(r["id"] in x["rules"] for x in got["terms"]) \
                    and r["slot"] not in ("qualifier",):
                failures.append(f"term_clauses.json:{r['id']}:{tc['id']}: rule not used ({got['terms']})")
    return failures
