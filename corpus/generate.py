"""Deterministic synthetic PEC corpus generator (seeded).

    python corpus/generate.py            # -> corpus/out/ + corpus/gold/labels.jsonl
    python corpus/generate.py --check    # regenerate into build/ and compare with MANIFEST.sha256

~300 envelopes for the synthetic debtor FORNACE AURELIA S.R.L.: text PDFs,
image-only "scanned" PDFs, CAdES-attached .p7m and detached .p7s signatures
made with a local TEST CA (itself derived from the seed), transport S/MIME
signatures of two synthetic PEC providers, duplicates (re-exports) and revised
editions. Everything is fictitious; every address is ``.example``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from corpus import pec, templates as T, testca, world as W  # noqa: E402
from corpus.reference_terms import GOLD_TERMS, notification_day, walk  # noqa: E402
from pipeline.lib import cms, pdfwrite, tzrome  # noqa: E402

CONFIG = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))
SEED = CONFIG["seed"]
AS_OF = tzrome.parse_iso(CONFIG["as_of"])

COUNTS = {
    "precetto": 28, "decreto_ingiuntivo": 22, "ppt": 13, "ppt_bank": 8, "pign_mob": 9, "ricorso_liq": 9,
    "sentenza_liq": 3, "accertamento_ae": 15, "accertamento_comune": 6, "cartella": 30, "intimazione": 13,
    "addebito": 18, "rateizzazione": 14, "citazione": 14, "diffida_company": 18, "diffida_lawyer": 8,
    "diffida_bank": 7, "sollecito_company": 20, "sollecito_bank": 4, "canc_rinvio": 14, "canc_info": 7,
    "target_forward": 6,
}
REVISIONS = {"rateizzazione": 3, "cartella": 2, "addebito": 1}
N_DUPLICATES = 8
EXPECTS_AMOUNT = {"atto_precetto", "decreto_ingiuntivo", "avviso_accertamento", "cartella_pagamento",
                  "intimazione_pagamento", "avviso_addebito", "provvedimento_rateizzazione", "atto_citazione",
                  "diffida_messa_in_mora", "sollecito_pagamento"}
# Gold-side policy, written independently of rules/terms.json (a test asserts they agree).
EXPECTS_DEADLINE = {"atto_precetto", "decreto_ingiuntivo", "pignoramento_presso_terzi", "pignoramento_mobiliare",
                    "ricorso_liquidazione_giudiziale", "sentenza_liquidazione_giudiziale", "avviso_accertamento",
                    "cartella_pagamento", "intimazione_pagamento", "avviso_addebito", "provvedimento_rateizzazione",
                    "atto_citazione", "diffida_messa_in_mora"}


def _times(rnd: random.Random, n: int) -> list[dt.datetime]:
    start, end = dt.date.fromisoformat(CONFIG["period"][0]), dt.date.fromisoformat(CONFIG["period"][1])
    span = (end - start).days
    out = []
    while len(out) < n:
        day = start + dt.timedelta(days=rnd.randint(0, span))
        if day.weekday() == 6 and rnd.random() < 0.9:
            continue
        if rnd.random() < 0.06:
            h, m = rnd.randint(21, 23), rnd.randint(0, 59)
        else:
            h, m = rnd.randint(8, 19), rnd.randint(0, 59)
        local = dt.datetime(day.year, day.month, day.day, h, m, rnd.randint(0, 59))
        out.append(tzrome.to_rome(tzrome.rome_local_to_utc(local)))
    return sorted(out)


def _make(kind: str, ctx: T.Ctx, rnd: random.Random) -> T.Doc:
    cr = rnd.choice(W.CREDITORS)
    if kind in ("precetto", "decreto_ingiuntivo", "ppt", "pign_mob", "citazione", "diffida_lawyer"):
        lw = rnd.choice(W.LAWYERS)
        gw = rnd.choice(W.GATEWAYS) if rnd.random() < 0.3 else None
        doc = T.lawyer_act(ctx, kind, lw, cr, gw)
        if rnd.random() < 0.7:
            doc.principal_sig = f"p7m:lawyer-{lw['key']}"
            if rnd.random() < 0.5:
                doc.relata = [("text", T.wrap([
                    "RELATA DI NOTIFICA A MEZZO PEC", "",
                    f"Io sottoscritto Avv. {lw['name']}, ai sensi dell'art. 3-bis della L. 53/1994, ho notificato l'atto "
                    f"allegato a {T.DEBTOR_UP} all'indirizzo PEC {W.DEBTOR['pec']}, estratto da pubblico elenco (sintetico).",
                    f"Avv. {lw['name']}"]))]
                doc.relata_sig = f"p7s:lawyer-{lw['key']}"
        elif rnd.random() < 0.3:
            doc.pages = doc.pages + [("image", ctx.seq * 13 + 5)]
            doc.hard.append("mixed_scan_page")
        return doc
    if kind == "ppt_bank":
        return T.bank_third_party(ctx, rnd.choice(W.BANKS), cr)
    if kind in ("diffida_bank", "sollecito_bank"):
        return T.bank_corporate(ctx, rnd.choice(W.BANKS), kind)
    if kind in ("ricorso_liq", "sentenza_liq", "canc_rinvio", "canc_info"):
        doc = T.court_act(ctx, kind, cr)
        if rnd.random() < 0.3:
            doc.principal_sig = "p7m:court"
        return doc
    if kind in ("cartella", "intimazione", "rateizzazione", "accertamento_ae", "accertamento_comune", "addebito"):
        doc = T.public_act(ctx, kind)
        if kind in ("cartella", "intimazione", "addebito") and rnd.random() < 0.12:
            doc.scanned = True
            doc.pages = [("image", ctx.seq * 11 + 3)]
            doc.hard.append("scanned_public_notice")
        return doc
    if kind in ("diffida_company", "sollecito_company"):
        return T.company_act(ctx, kind, cr)
    if kind == "target_forward":
        return T.target_forward(ctx)
    raise ValueError(kind)


def _pdf(pages) -> bytes:
    conv = [("text", p) if k == "text" else ("image", pdfwrite.scan_raster(p)) for k, p in pages]
    return pdfwrite.build_pdf(conv)


def _gold_deadlines(doc: T.Doc, notif: dt.datetime, transport_ok: bool) -> dict:
    pol = GOLD_TERMS.get(doc.doc_type or "", (None, False, False, False))
    days_default, susp, sat, after21 = pol
    visible_text = not doc.scanned and doc.kind != "target_forward"
    deadlines, recuperare_reasons = [], []
    if visible_text:
        deadlines += [d for d in doc.dates if d["nature"] == "actionable"]
    known_notification = doc.sender_class != "TARGET" and transport_ok
    rels = [r for r in doc.rel_terms if not r["conditional"]] if visible_text else []
    if not rels and days_default and not visible_text:
        rels = [{"days": days_default, "conditional": False, "statutory": True}]
    if rels:
        if known_notification:
            nday = notification_day(tzrome.to_rome(notif), after21)
            for r in rels:
                deadlines.append({"date": walk(nday, r["days"], susp, sat).isoformat(), "nature": "computed",
                                  "days": r["days"]})
        else:
            recuperare_reasons.append("notification date not verifiable")
    as_of = AS_OF.date().isoformat()
    driving = None
    if deadlines:
        up = sorted([d for d in deadlines if d["date"] >= as_of], key=lambda d: (d["date"], d["nature"]))
        driving = {**up[0], "status": "open"} if up else {**sorted(deadlines, key=lambda d: (d["date"], d["nature"]))[-1],
                                                          "status": "expired"}
    expects = (doc.doc_type in EXPECTS_DEADLINE) or doc.doc_type is None
    deadline_rec = driving is None and expects
    return {"deadlines": deadlines, "driving": driving, "deadline_recuperare": deadline_rec,
            "reasons": recuperare_reasons}


def _urgency(doc_type, drv, deadline_rec) -> str:
    if doc_type is None or deadline_rec:
        return "MAXIMUM"
    if drv is None:
        return "INFORMATIONAL"
    days = (dt.date.fromisoformat(drv["date"]) - AS_OF.date()).days
    if drv["status"] == "expired":
        lvl = "MAXIMUM" if -days <= 15 else "LOW"
    else:
        lvl = "MAXIMUM" if days <= 10 else "HIGH" if days <= 30 else "MEDIUM" if days <= 60 else "LOW"
    if doc_type in ("ricorso_liquidazione_giudiziale", "sentenza_liquidazione_giudiziale") and lvl in ("MEDIUM", "LOW"):
        lvl = "HIGH"
    return lvl


def generate(out: Path, gold_path: Path | None, seed: int = SEED) -> dict:
    rnd = random.Random(seed)
    ids = testca.build(seed)
    testca.write(ids, out / "testca")

    def cms_sign(identity: str, content: bytes, when: dt.datetime, detached: bool, tamper: bytes | None = None):
        idn = ids[identity]
        return cms.sign(content, idn.cert_der, idn.key, signing_time=when, extra_certs=idn.chain,
                        detached=detached, tamper_encapsulated=tamper)

    kinds = [k for k, n in COUNTS.items() for _ in range(n)]
    rnd.shuffle(kinds)
    times = _times(rnd, len(kinds))
    docs: list[tuple[T.Doc, dt.datetime]] = []
    for i, (kind, t) in enumerate(zip(kinds, times), start=1):
        ctx = T.Ctx(rnd, t, i)
        doc = _make(kind, ctx, rnd)
        doc.dates, doc.rel_terms = ctx.dates, ctx.rel
        docs.append((doc, t))
    # revised editions (same pratica, new edition, corrected amount)
    seq = len(docs)
    revised_of = {}
    for kind, n in REVISIONS.items():
        cands = [(d, t) for d, t in docs if d.kind == kind and not d.scanned and t.date() <= dt.date(2026, 10, 1)]
        for d, t in rnd.sample(cands, n):
            seq += 1
            t2 = t + dt.timedelta(days=rnd.randint(5, 18), hours=rnd.randint(0, 3))
            if t2.date() > dt.date(2026, 10, 20):
                t2 = t + dt.timedelta(days=2)
            old = Decimal(d.amount)
            new = (old * Decimal(rnd.choice(["0.92", "0.95", "0.88"]))).quantize(Decimal("0.01"))
            ctx = T.Ctx(rnd, tzrome.to_rome(t2), seq)
            nd = T.public_act(ctx, kind, edition={"pratica": d.pratica, "prev_ref": d.edition_ref,
                                                  "prev_date": d.edition_date, "new_amount": str(new)})
            nd.dates, nd.rel_terms = ctx.dates, ctx.rel
            nd.principal_sig = d.principal_sig
            docs.append((nd, tzrome.to_rome(t2)))
            revised_of[id(nd)] = d
    docs.sort(key=lambda x: x[1])
    # planted signature defects
    p7m_docs = [d for d, _ in docs if (d.principal_sig or "").startswith("p7m:") and d.amount_text
                and "lawyer-SL" not in d.principal_sig]
    tampered = {id(d) for d in rnd.sample(p7m_docs, 3)}
    plain = [d for d, _ in docs if d.principal_sig is None and d.sender_class not in ("TARGET",) and not d.scanned]
    transport_broken = {id(d) for d in rnd.sample(plain, 2)}

    env_dir = out / "envelopes"
    labels, files = [], []
    path_of = {}
    for n, (doc, t) in enumerate(docs, start=1):
        utc = t.astimezone(tzrome.UTC)
        ident = f"opec-syn.{utc.strftime('%Y%m%d%H%M%S')}.{n:05d}@" + ("pec.gestore-uno.example" if n % 2 else "postacerta-esempio.example")
        gest = W.GESTORI[0] if n % 2 else W.GESTORI[1]
        msgid = f"<SYN-{n:04d}.{utc.strftime('%Y%m%d%H%M%S')}@{doc.sender_addr.split('@')[1]}>"
        pdf = _pdf(doc.pages)
        attachments = []
        sig_gold = []
        claimed = utc - dt.timedelta(hours=rnd.randint(1, 6), minutes=rnd.randint(0, 59))
        if doc.principal_sig and doc.principal_sig.startswith("p7m:"):
            identity = doc.principal_sig[4:]
            tamper = None
            if id(doc) in tampered:
                swapped = _swap(doc.amount_text)
                alt_pages = [(k, [ln.replace(doc.amount_text, swapped) for ln in p]) if k == "text" else (k, p)
                             for k, p in doc.pages]
                tamper = _pdf(alt_pages)
                doc.hard.append("tampered_p7m")
            blob = cms_sign(identity, pdf, claimed, detached=False, tamper=tamper)
            attachments.append((doc.principal_name + ".p7m", "application/pkcs7-mime", blob))
            sig_gold.append(_sig_gold(doc.principal_name + ".p7m", "CAdES-attached", identity, utc, claimed,
                                      tampered=id(doc) in tampered))
        else:
            attachments.append((doc.principal_name, "application/pdf", pdf))
            if doc.principal_sig and doc.principal_sig.startswith("p7s:"):
                identity = doc.principal_sig[4:]
                attachments.append((doc.principal_name + ".p7s", "application/pkcs7-signature",
                                    cms_sign(identity, pdf, claimed, detached=True)))
                sig_gold.append(_sig_gold(doc.principal_name + ".p7s", "CAdES-detached", identity, utc, claimed))
        if doc.relata:
            rpdf = _pdf(doc.relata)
            attachments.append(("relata_notifica.pdf", "application/pdf", rpdf))
            if doc.relata_sig:
                identity = doc.relata_sig[4:]
                attachments.append(("relata_notifica.pdf.p7s", "application/pkcs7-signature",
                                    cms_sign(identity, rpdf, claimed, detached=True)))
                sig_gold.append(_sig_gold("relata_notifica.pdf.p7s", "CAdES-detached", identity, utc, claimed))
        inner = pec.inner_message(from_display=doc.sender_display, from_addr=doc.sender_addr,
                                  to_addr=W.DEBTOR["pec"], subject=doc.subject, when=t, msgid=msgid, body=doc.body,
                                  attachments=attachments, reply_to=doc.reply_to)
        dc = pec.daticert(mittente=doc.sender_addr, destinatario=W.DEBTOR["pec"], oggetto=doc.subject,
                          gestore=gest["name"], when=t, identificativo=ident, msgid=msgid)
        tampered_dc = None
        if id(doc) in transport_broken:
            tampered_dc = pec.daticert(mittente=doc.sender_addr, destinatario=W.DEBTOR["pec"], oggetto=doc.subject,
                                       gestore=gest["name"], when=t - dt.timedelta(days=3), identificativo=ident,
                                       msgid=msgid)
            doc.hard.append("transport_signature_broken")
        raw = pec.outer_message(gestore_addr=gest["addr"], gestore_name=gest["name"], mittente=doc.sender_addr,
                                destinatario=W.DEBTOR["pec"], subject=doc.subject, when=t, identificativo=ident,
                                orig_msgid=msgid, inner=inner, daticert_xml=dc,
                                sign=lambda c, g=gest, w=utc: cms_sign(f"gestore-{g['key']}", c, w, detached=True),
                                tampered_daticert=tampered_dc)
        rel = f"envelopes/{t.strftime('%Y-%m')}/PEC_{t.strftime('%Y%m%d_%H%M%S')}_{n:04d}.eml"
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        files.append(rel)
        path_of[id(doc)] = rel
        transport_ok = id(doc) not in transport_broken
        dl = _gold_deadlines(doc, t, transport_ok)
        exp_rec = []
        if doc.doc_type is None:
            exp_rec += ["doc_type", "area"]
        for f in ("author", "party", "channel"):
            if getattr(doc, f) == "RECUPERARE":
                exp_rec.append({"author": "author_entity", "party": "party_entity", "channel": "counterparty_channel"}[f])
        amount = doc.amount
        if doc.scanned or doc.kind == "target_forward" or id(doc) in tampered:
            amount = None
        if amount is None and (doc.doc_type in EXPECTS_AMOUNT or doc.doc_type is None):
            exp_rec.append("amount_due")
        if dl["deadline_recuperare"]:
            exp_rec.append("deadline")
        if any(k == "image" for k, _ in doc.pages):
            exp_rec.append("text")
        author = doc.author
        channel = doc.channel
        if doc.scanned and doc.kind != "target_forward":
            author = "AGENZIA ESEMPIO RISCOSSIONE" if (doc.principal_sig or "") == "p7s:agency" else "RECUPERARE"
            channel = doc.sender_addr
            exp_rec = [x for x in exp_rec if x != "counterparty_channel"]
            if author == "RECUPERARE":
                exp_rec.append("author_entity")
        labels.append({
            "envelope": rel, "kind": doc.kind,
            "doc_type": doc.doc_type or "RECUPERARE", "area": doc.area or "RECUPERARE",
            "sender_class": doc.sender_class, "transmitter_entity": doc.transmitter, "author_entity": author,
            "party_entity": doc.party, "counterparty_channel": channel,
            "amount_due": amount, "pratica": doc.pratica, "edition_ref": doc.edition_ref,
            "edition_date": doc.edition_date, "supersedes_ref": doc.supersedes_ref,
            "notification_utc": utc.isoformat(),
            "dates": doc.dates if not (doc.scanned or doc.kind == "target_forward") else [],
            "deadlines": dl["deadlines"], "deadline": (dl["driving"] or {}).get("date") if not dl["deadline_recuperare"] else "RECUPERARE",
            "deadline_nature": (dl["driving"] or {}).get("nature"),
            "urgency": _urgency(doc.doc_type, dl["driving"], dl["deadline_recuperare"]),
            "expected_recuperare": sorted(set(exp_rec)),
            "signatures": sig_gold, "transport_signature_integrity": "ok" if transport_ok else "failed",
            "hard_cases": sorted(set(doc.hard)), "duplicate_of": None,
            "supersedes": path_of.get(id(revised_of[id(doc)])) if id(doc) in revised_of else None,
        })
    # duplicates: accidental re-exports, byte-identical
    dup_src = rnd.sample([lab for lab in labels if lab["kind"] != "target_forward"], N_DUPLICATES)
    for lab in dup_src:
        src = out / lab["envelope"]
        rel = "envelopes/reexport/" + Path(lab["envelope"]).stem + " (copia).eml"
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(src.read_bytes())
        files.append(rel)
        labels.append({**lab, "envelope": rel, "duplicate_of": lab["envelope"], "hard_cases": sorted(set(lab["hard_cases"]) | {"duplicate_reexport"})})
    labels.sort(key=lambda x: x["envelope"])
    files.sort()
    manifest = {"generator": "corpus/generate.py", "seed": seed, "expected_envelopes": len(files),
                "files": [{"path": f, "sha256": hashlib.sha256((out / f).read_bytes()).hexdigest()} for f in files]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                                       newline="\n")
    if gold_path:
        gold_path.parent.mkdir(parents=True, exist_ok=True)
        with open(gold_path, "w", encoding="utf-8", newline="\n") as fh:
            for lab in labels:
                fh.write(json.dumps(lab, ensure_ascii=False, sort_keys=True) + "\n")
    return {"envelopes": len(files), "labels": len(labels)}


def _swap(s: str) -> str:
    """Transpose the first two different adjacent digits (12.380,00 -> 12.830,00-like)."""
    ch = list(s)
    digits = [i for i, c in enumerate(ch) if c.isdigit()]
    for a, b in zip(digits, digits[1:]):
        if b == a + 1 and ch[a] != ch[b] and a > 0:
            ch[a], ch[b] = ch[b], ch[a]
            return "".join(ch)
    ch[digits[0]], ch[digits[1]] = ch[digits[1]], ch[digits[0]]
    return "".join(ch)


def _sig_gold(name, fmt, identity, pec_utc, claimed, tampered=False) -> dict:
    if identity == "lawyer-SL":
        chain, status = False, "untrusted_issuer"
    elif identity == "lawyer-DM" and pec_utc > dt.datetime(2026, 7, 31, 23, 59, 59, tzinfo=tzrome.UTC):
        chain, status = False, "expired_at_validation_time"
    else:
        chain, status = True, "verified"
    return {"file": name, "format": fmt, "signature_integrity": "failed" if tampered else "ok",
            "signer_chain_verified": chain, "chain_status": status}


def file_hashes(out: Path) -> dict:
    res = {}
    for p in sorted(out.rglob("*")):
        if p.is_file():
            res[p.relative_to(out).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "corpus" / "out"))
    ap.add_argument("--gold", default=str(ROOT / "corpus" / "gold" / "labels.jsonl"))
    ap.add_argument("--write-manifest", action="store_true", help="write corpus/MANIFEST.sha256")
    ap.add_argument("--check", action="store_true", help="regenerate into build/corpus-check and compare")
    ap.add_argument("--seed", type=int, default=SEED, help="held-out corpora use a different seed (e.g. 20261001)")
    a = ap.parse_args(argv)
    if a.check:
        out = ROOT / "build" / "corpus-check"
        gold = ROOT / "build" / "corpus-check-gold.jsonl"
        generate(out, gold)
        expected = dict(line.split("  ", 1)[::-1] for line in
                        (ROOT / "corpus" / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines() if line)
        expected = {k.strip(): v for k, v in expected.items()}
        got = file_hashes(out)
        gold_ok = gold.read_bytes() == (ROOT / "corpus" / "gold" / "labels.jsonl").read_bytes()
        diff = sorted(k for k in set(expected) | set(got) if expected.get(k) != got.get(k))
        print(f"corpus files: {len(got)}; mismatches vs MANIFEST.sha256: {len(diff)}; gold identical: {gold_ok}")
        for k in diff[:10]:
            print("  differs:", k)
        return 0 if not diff and gold_ok else 1
    out = Path(a.out)
    res = generate(out, Path(a.gold), a.seed)
    if a.write_manifest:
        with open(ROOT / "corpus" / "MANIFEST.sha256", "w", encoding="utf-8", newline="\n") as fh:
            for k, v in file_hashes(out).items():
                fh.write(f"{v}  {k}\n")
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
