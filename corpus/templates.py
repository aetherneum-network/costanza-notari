"""Synthetic Italian procedural acts. Every date is written through ``Ctx.d``,
which records its gold nature *at the moment the sentence is written*.

All names, references and amounts are fictitious. References carry visibly
synthetic prefixes (PR-, EX-, SYN-) and never mimic real registry formats.
"""
from __future__ import annotations

import datetime as dt
import textwrap
from dataclasses import dataclass, field
from decimal import Decimal

from . import world as W
from .reference_terms import is_non_working

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
          "ottobre", "novembre", "dicembre"]
DEBTOR_UP = "FORNACE AURELIA S.R.L."
DEBTOR_ADDR = "FORNACE AURELIA S.R.L., con sede in Esempio, Via delle Fornaci 12"


def eur(v: Decimal) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass
class Doc:
    kind: str
    doc_type: str | None
    area: str | None
    sender_class: str
    sender_display: str
    sender_addr: str
    transmitter: str
    author: str
    party: str
    channel: str
    subject: str
    body: str
    pages: list = field(default_factory=list)      # principal attachment pages: [("text", lines) | ("image", seed)]
    principal_name: str = "atto.pdf"
    relata: list | None = None                     # optional second attachment pages
    principal_sig: str | None = None               # None | "p7m:<identity>" | "p7s:<identity>"
    relata_sig: str | None = None
    amount: str | None = None
    amount_text: str | None = None                 # the formatted amount as written (for tampering)
    pratica: str | None = None
    edition_ref: str | None = None
    edition_date: str | None = None
    supersedes_ref: str | None = None
    dates: list = field(default_factory=list)
    rel_terms: list = field(default_factory=list)
    reply_to: str | None = None
    hard: list = field(default_factory=list)
    scanned: bool = False


class Ctx:
    def __init__(self, rnd, notif: dt.datetime, seq: int):
        self.rnd, self.notif, self.seq = rnd, notif, seq
        self.nd = notif.date()
        self.dates: list = []
        self.rel: list = []

    def d(self, date: dt.date, nature: str, style: str | None = None) -> str:
        self.dates.append({"date": date.isoformat(), "nature": nature})
        style = style or ("word" if self.rnd.random() < 0.15 else "num")
        if style == "word":
            return f"{date.day} {MONTHS[date.month - 1]} {date.year}"
        return date.strftime("%d/%m/%Y")

    def rel_term(self, days: int, word: str, conditional: bool = False) -> str:
        self.rel.append({"days": days, "conditional": conditional})
        return word

    def past(self, lo: int, hi: int) -> dt.date:
        return self.nd - dt.timedelta(days=self.rnd.randint(lo, hi))

    def future_workday(self, lo: int, hi: int) -> dt.date:
        d = self.nd + dt.timedelta(days=self.rnd.randint(lo, hi))
        while d.weekday() >= 5 or is_non_working(d) or d.month == 8:
            d += dt.timedelta(days=1)
        return d

    def amount(self, lo: int, hi: int) -> Decimal:
        return Decimal(self.rnd.randint(lo * 100, hi * 100)) / 100

    def doc_date(self) -> dt.date:
        return self.nd - dt.timedelta(days=self.rnd.choice([0, 1, 1, 2, 3]))


def wrap(paras: list[str], width: int = 92) -> list[str]:
    out = []
    for p in paras:
        if p == "":
            out.append("")
            continue
        if p.isupper() and len(p) < 90:
            out.append(p)
        else:
            out.extend(textwrap.wrap(p, width=width, break_long_words=False, break_on_hyphens=False) or [""])
    return out


def _creditor_intro(ctx, cr, declare_pec: bool) -> str:
    pec = f", PEC {cr['pec']}" if declare_pec else ""
    return f"{cr['canonical']}, con sede in Esempio{pec}"


def _lawyer_bodies(ctx, lw, via_gateway):
    if via_gateway:
        gw = via_gateway
        body = (f"Messaggio trasmesso tramite il servizio di notifica di {gw['name']} per conto dell'Avv. "
                f"{lw['name']}.\nSi notifica l'atto allegato ai sensi della L. 53/1994.\n"
                f"Il servizio non è responsabile del contenuto del messaggio.")
        return gw["name"], gw["pec"], "TRANSMIT", gw["canonical"], body
    body = f"Si notifica, ai sensi della L. 53/1994, l'atto allegato.\n{lw['display'] if lw['display'].startswith('Avv') else 'Avv. ' + lw['name']}"
    return lw["display"], lw["pec"], "LAWYER", lw.get("transmitter_canonical", lw["canonical"]), body


# ---------------------------------------------------------------- lawyer acts
def lawyer_act(ctx: Ctx, kind: str, lw: dict, cr: dict, via_gateway: dict | None) -> Doc:
    r = ctx.rnd
    declare = r.random() < 0.6
    pr = f"PR-{cr['key']}-{ctx.seq:04d}"
    display, addr, scls, transmitter, body = _lawyer_bodies(ctx, lw, via_gateway)
    head = [lw["studio"], ""]
    intro = (f"Per conto e nell'interesse di {_creditor_intro(ctx, cr, declare)}, rappresentata e difesa "
             f"dall'Avv. {lw['name']},")
    amount_v = None
    if kind == "precetto":
        a = ctx.amount(1500, 60000)
        amount_v = a
        di_date, ex_date = ctx.past(120, 200), ctx.past(40, 110)
        paras = head + ["ATTO DI PRECETTO", f"Rif. pratica: {pr}", "", intro,
                        f"premesso che con decreto ingiuntivo n. SYN-DI-{ctx.seq:04d} emesso il {ctx.d(di_date, 'historical')} "
                        f"dal Tribunale di Esempio, dichiarato esecutivo il {ctx.d(ex_date, 'historical')}, è stato ingiunto a "
                        f"{DEBTOR_UP} il pagamento del credito;"]
        if r.random() < 0.4:
            paras.append(f"che il pagamento doveva avvenire entro il {ctx.d(ctx.past(20, 39), 'historical')} e non è avvenuto;")
        paras += ["INTIMA", f"a {DEBTOR_ADDR}, di pagare entro il termine di "
                  f"{ctx.rel_term(10, 'dieci')} giorni dalla notifica del presente atto la somma di € {eur(a)}, oltre "
                  "interessi e spese, con avvertimento che in mancanza si procederà ad esecuzione forzata."]
        subject = "Notifica atto di precetto" if r.random() < 0.85 else "Sollecito"
        dt_ = "atto_precetto"
        area = "pre_enforcement"
        name = "atto_precetto.pdf"
    elif kind == "decreto_ingiuntivo":
        a = ctx.amount(2000, 80000)
        amount_v = a
        dep = ctx.past(30, 90)
        f1, f2 = ctx.past(120, 200), ctx.past(91, 119)
        paras = ["TRIBUNALE DI ESEMPIO", "", f"DECRETO INGIUNTIVO N. SYN-DI-{ctx.seq:04d}", f"Rif. pratica: {pr}", "",
                 f"Il Giudice, letto il ricorso depositato il {ctx.d(dep, 'historical')} da {_creditor_intro(ctx, cr, declare)}, "
                 f"rappresentata e difesa dall'Avv. {lw['name']}, nei confronti di {DEBTOR_UP};",
                 f"viste le fatture n. {100 + ctx.seq % 50} del {ctx.d(f1, 'historical')} e n. {151 + ctx.seq % 40} del "
                 f"{ctx.d(f2, 'historical')};",
                 "INGIUNGE", f"a {DEBTOR_UP} di pagare al ricorrente, entro {ctx.rel_term(40, 'quaranta')} giorni dalla "
                 f"notifica del presente decreto, la somma di € {eur(a)} oltre interessi e spese, avvertendo che nello "
                 "stesso termine può essere proposta opposizione.",
                 f"Esempio, {ctx.d(ctx.past(5, 25), 'historical')}", "Il Giudice (copia conforme notificata)", "",
                 f"Relata di notifica ai sensi della L. 53/1994: notificato per conto e nell'interesse di {cr['canonical']}, "
                 f"dall'Avv. {lw['name']}."]
        subject = "Notifica decreto ingiuntivo"
        dt_, area, name = "decreto_ingiuntivo", "payment_order", "decreto_ingiuntivo.pdf"
    elif kind == "ppt":
        a = ctx.amount(3000, 50000)
        amount_v = a
        bank = r.choice(W.BANKS)
        hearing = ctx.future_workday(30, 75)
        paras = head + ["ATTO DI PIGNORAMENTO PRESSO TERZI", f"Rif. pratica: {pr}", "",
                        intro.replace("rappresentata", "creditore procedente, rappresentata"),
                        f"premesso che in data {ctx.d(ctx.past(25, 70), 'historical')} è stato notificato a {DEBTOR_UP} "
                        f"atto di precetto per la somma di € {eur(a)}, rimasto senza esito;",
                        "PIGNORA", f"le somme dovute a {DEBTOR_UP} dal terzo {bank['canonical']}, fino alla concorrenza "
                        "del credito;",
                        "CITA", f"il debitore e il terzo a comparire all'udienza del {ctx.d(hearing, 'actionable')} ore 9:30 "
                        "innanzi al Giudice dell'esecuzione del Tribunale di Esempio, con invito al terzo a rendere la "
                        "dichiarazione di cui all'art. 547 c.p.c."]
        subject = "Notifica atto di pignoramento presso terzi"
        dt_, area, name = "pignoramento_presso_terzi", "third_party_attachment", "pignoramento_presso_terzi.pdf"
    elif kind == "pign_mob":
        hearing = ctx.future_workday(40, 90)
        paras = head + ["AVVISO DI PIGNORAMENTO MOBILIARE", f"Rif. pratica: {pr}", "",
                        intro.replace("rappresentata", "creditore procedente, rappresentata"),
                        f"si comunica che in data {ctx.d(ctx.past(1, 6), 'historical')} l'Ufficiale Giudiziario ha eseguito "
                        f"presso la sede di {DEBTOR_UP} pignoramento mobiliare per il credito di € "
                        f"{eur(ctx.amount(2000, 30000))}, come da verbale allegato.",
                        f"Si avverte che eventuali opposizioni agli atti esecutivi devono essere proposte entro "
                        f"{ctx.rel_term(20, 'venti')} giorni dalla notifica del presente avviso.",
                        f"L'udienza per l'autorizzazione alla vendita è fissata al {ctx.d(hearing, 'actionable')}."]
        subject = "Avviso di pignoramento mobiliare"
        dt_, area, name = "pignoramento_mobiliare", "enforcement", "avviso_pignoramento.pdf"
    elif kind == "citazione":
        a = ctx.amount(5000, 90000)
        amount_v = a
        hearing = ctx.future_workday(95, 150)
        paras = head + ["ATTO DI CITAZIONE", f"Rif. pratica: {pr}", "", intro,
                        f"premesso che con contratto stipulato il {ctx.d(ctx.past(250, 500), 'historical')} "
                        f"{cr['canonical']} forniva a {DEBTOR_UP} materiali per la somma di € {eur(a)}, rimasta insoluta;",
                        "CITA", f"{DEBTOR_UP}, in persona del legale rappresentante, a comparire all'udienza del "
                        f"{ctx.d(hearing, 'actionable')} innanzi al Tribunale di Esempio, con invito a costituirsi nel "
                        "termine di settanta giorni prima dell'udienza."]
        if r.random() < 0.35:
            paras.append(f"Il termine originariamente fissato al {ctx.d(ctx.nd + dt.timedelta(days=r.randint(3, 9)), 'historical')} "
                         "deve intendersi superato dalla presente citazione.")
            ctx_hard = "recital_future_date"
        else:
            ctx_hard = None
        subject = "Notifica atto di citazione"
        dt_, area, name = "atto_citazione", "civil_litigation", "atto_citazione.pdf"
    elif kind == "diffida_lawyer":
        a = ctx.amount(1000, 40000)
        amount_v = a
        paras = head + ["DIFFIDA E MESSA IN MORA", f"Rif. pratica: {pr}", "", intro,
                        f"Vi diffido a corrispondere entro {ctx.rel_term(15, 'quindici')} giorni dal ricevimento della "
                        f"presente la somma di € {eur(a)}, relativa alle forniture di cui alla fattura n. {200 + ctx.seq % 90} "
                        f"del {ctx.d(ctx.past(60, 150), 'historical')}.",
                        "In difetto, procederò per il recupero giudiziale senza ulteriore avviso."]
        subject = "Diffida e messa in mora"
        dt_, area, name = "diffida_messa_in_mora", "out_of_court_recovery", "diffida.pdf"
    else:
        raise ValueError(kind)
    if kind != "decreto_ingiuntivo":
        paras += [f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", f"Avv. {lw['name']}"]
    else:
        paras += [f"Avv. {lw['name']}"]
    doc = Doc(kind=kind, doc_type=dt_, area=area, sender_class=scls, sender_display=display, sender_addr=addr,
              transmitter=transmitter, author=lw["canonical"], party=cr["canonical"],
              channel=cr["pec"] if declare else "RECUPERARE", subject=subject, body=body,
              pages=[("text", wrap(paras))], principal_name=name, amount=None if amount_v is None else f"{amount_v:.2f}",
              amount_text=None if amount_v is None else eur(amount_v), pratica=pr)
    if kind == "precetto" and subject == "Sollecito":
        doc.hard.append("subject_mismatch")
    if kind == "citazione" and ctx_hard:
        doc.hard.append(ctx_hard)
    if lw["key"] == "TO" and not via_gateway:
        doc.hard.append("lawyer_generic_domain")
    return doc


# ---------------------------------------------------------------- bank acts
def bank_third_party(ctx: Ctx, bank: dict, cr: dict) -> Doc:
    pr = f"PR-{cr['key']}-{ctx.seq:04d}"
    hearing = ctx.future_workday(25, 70)
    paras = [bank["canonical"], "Ufficio Pignoramenti", "",
             "Oggetto: dichiarazione del terzo ai sensi dell'art. 547 c.p.c.", f"Rif. pratica: {pr}", "",
             f"La scrivente {bank['canonical']}, in qualità di terzo pignorato nella procedura promossa da "
             f"{cr['canonical']}, con atto notificato alla scrivente in data {ctx.d(ctx.past(3, 20), 'historical')}, "
             f"comunica che sui rapporti intestati a {DEBTOR_UP} sono state accantonate somme pari a € "
             f"{eur(ctx.amount(500, 20000))}.",
             f"La presente dichiarazione è resa in vista dell'udienza del {ctx.d(hearing, 'actionable')} fissata "
             "innanzi al Giudice dell'esecuzione del Tribunale di Esempio.",
             f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", f"{bank['canonical']} - Ufficio Pignoramenti"]
    return Doc(kind="ppt_bank", doc_type="pignoramento_presso_terzi", area="third_party_attachment",
               sender_class="BANK_THIRD_PARTY", sender_display=bank["name"], sender_addr=bank["pec"],
               transmitter=bank["canonical"], author=bank["canonical"], party=cr["canonical"], channel="RECUPERARE",
               subject="Dichiarazione del terzo - art. 547 c.p.c.", body="Si trasmette in allegato la comunicazione in oggetto.",
               pages=[("text", wrap(paras))], principal_name="dichiarazione_terzo.pdf", pratica=pr)


def bank_corporate(ctx: Ctx, bank: dict, kind: str) -> Doc:
    pr = f"PR-{bank['key']}-{ctx.seq:04d}"
    a = ctx.amount(5000, 90000)
    if kind == "diffida_bank":
        paras = [bank["canonical"], "Direzione Crediti", "", "DIFFIDA E MESSA IN MORA", f"Rif. pratica: {pr}", "",
                 f"Spett.le {DEBTOR_UP},",
                 "con la presente Vi comunichiamo la revoca degli affidamenti concessi sul conto corrente n. "
                 f"SYN-CC-{ctx.seq:04d} e Vi intimiamo il rientro dell'esposizione per la somma di € {eur(a)}, pari al "
                 f"saldo debitore alla data del {ctx.d(ctx.past(2, 10), 'historical')}, entro "
                 f"{ctx.rel_term(15, 'quindici')} giorni dal ricevimento della presente.",
                 f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", f"{bank['canonical']} - Direzione Crediti"]
        dt_, subj, area = "diffida_messa_in_mora", "Revoca affidamenti e messa in mora", "banking"
    else:
        paras = [bank["canonical"], "Filiale di Esempio", "", "SOLLECITO DI PAGAMENTO", f"Rif. pratica: {pr}", "",
                 f"Spett.le {DEBTOR_UP},",
                 f"Vi ricordiamo che la rata del finanziamento n. SYN-FIN-{ctx.seq:04d}, scaduta il "
                 f"{ctx.d(ctx.past(10, 40), 'historical')}, per un importo di € {eur(a)}, risulta ancora insoluta, con "
                 "conseguente saldo debitore del conto di appoggio. Vi invitiamo a provvedere con cortese sollecitudine.",
                 f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", f"{bank['canonical']} - Filiale di Esempio"]
        dt_, subj, area = "sollecito_pagamento", "Sollecito di pagamento", "banking"
    return Doc(kind=kind, doc_type=dt_, area=area, sender_class="BANK_CORPORATE", sender_display=bank["name"],
               sender_addr=bank["pec"], transmitter=bank["canonical"], author=bank["canonical"], party=bank["canonical"],
               channel=bank["pec"], subject=subj, body="Si trasmette in allegato la comunicazione in oggetto.",
               pages=[("text", wrap(paras))], principal_name="comunicazione.pdf", amount=f"{a:.2f}", amount_text=eur(a),
               pratica=pr)


# ---------------------------------------------------------------- court acts
def court_act(ctx: Ctx, kind: str, cr: dict) -> Doc:
    r = ctx.rnd
    declare = r.random() < 0.5
    if kind == "ricorso_liq":
        office = "crisi"
        pr = f"PR-CRISI-SYN-{ctx.seq:04d}"
        hearing = ctx.future_workday(30, 70)
        a = ctx.amount(20000, 250000)
        paras = ["TRIBUNALE DI ESEMPIO", "Sezione Crisi d'Impresa", "", "DECRETO DI CONVOCAZIONE", f"Rif. pratica: {pr}", "",
                 f"Il Tribunale, letto il ricorso per l'apertura della liquidazione giudiziale depositato in data "
                 f"{ctx.d(ctx.past(15, 45), 'historical')} da {_creditor_intro(ctx, cr, declare)}, nei confronti di "
                 f"{DEBTOR_UP}, per crediti per complessivi € {eur(a)};",
                 "FISSA", f"per la comparizione delle parti l'udienza del {ctx.d(hearing, 'actionable')} ore 10:00, "
                 "assegnando al debitore termine fino a sette giorni prima dell'udienza per il deposito di memorie.",
                 f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", "Il Cancelliere - TRIBUNALE DI ESEMPIO"]
        dt_, area, subj, amount = "ricorso_liquidazione_giudiziale", "insolvency", "Comunicazione decreto di convocazione", a
    elif kind == "sentenza_liq":
        office = "crisi"
        pr = f"PR-CRISI-SYN-{ctx.seq:04d}"
        paras = ["TRIBUNALE DI ESEMPIO", "Sezione Crisi d'Impresa", "", "SENTENZA DI APERTURA DELLA LIQUIDAZIONE GIUDIZIALE",
                 f"Rif. pratica: {pr}", "",
                 f"Il Tribunale, su ricorso di {cr['canonical']}, udite le parti all'udienza del "
                 f"{ctx.d(ctx.past(20, 40), 'historical')};",
                 f"DICHIARA aperta la liquidazione giudiziale di {DEBTOR_UP}; nomina il curatore e fissa gli adempimenti di legge.",
                 f"Sentenza depositata il {ctx.d(ctx.past(1, 5), 'historical')}.",
                 f"Avverso la presente sentenza può essere proposto reclamo entro {ctx.rel_term(30, 'trenta')} giorni "
                 "dalla notificazione.",
                 "Il Cancelliere - TRIBUNALE DI ESEMPIO"]
        dt_, area, subj, amount = "sentenza_liquidazione_giudiziale", "insolvency", "Notifica sentenza", None
        declare = False
    elif kind == "canc_rinvio":
        office = r.choice(["contenzioso", "esecuzioni"])
        pr = f"PR-RG-SYN-2026-{ctx.seq:04d}"
        new = ctx.future_workday(35, 120)
        paras = ["TRIBUNALE DI ESEMPIO", "Cancelleria " + ("Contenzioso" if office == "contenzioso" else "Esecuzioni"), "",
                 "COMUNICAZIONE DI CANCELLERIA", f"Rif. pratica: {pr}", "",
                 f"Procedimento: causa promossa da {cr['canonical']} contro {DEBTOR_UP}.",
                 f"Si comunica che il Giudice, con provvedimento depositato il {ctx.d(ctx.past(1, 6), 'historical')}, ha "
                 f"rinviato l'udienza al {ctx.d(new, 'actionable')}.",
                 "Il Cancelliere - TRIBUNALE DI ESEMPIO"]
        dt_, area, subj, amount = "comunicazione_cancelleria", "court", "Comunicazione di cancelleria", None
        declare = False
    elif kind == "canc_info":
        office = r.choice(["contenzioso", "esecuzioni"])
        pr = f"PR-RG-SYN-2026-{ctx.seq:04d}"
        paras = ["TRIBUNALE DI ESEMPIO", "Cancelleria " + ("Contenzioso" if office == "contenzioso" else "Esecuzioni"), "",
                 "COMUNICAZIONE DI CANCELLERIA", f"Rif. pratica: {pr}", "",
                 f"Procedimento: causa promossa da {cr['canonical']} contro {DEBTOR_UP}.",
                 f"Si comunica l'avvenuto deposito in data {ctx.d(ctx.past(1, 6), 'historical')} del provvedimento n. "
                 f"SYN-PROVV-{ctx.seq:04d}, consultabile nel fascicolo telematico.",
                 "Il Cancelliere - TRIBUNALE DI ESEMPIO"]
        dt_, area, subj, amount = "comunicazione_cancelleria", "court", "Comunicazione di cancelleria", None
        declare = False
    else:
        raise ValueError(kind)
    disp, addr = W.COURT["offices"][office]
    return Doc(kind=kind, doc_type=dt_, area=area, sender_class="COURT", sender_display=disp, sender_addr=addr,
               transmitter=W.COURT["canonical"], author=W.COURT["canonical"], party=cr["canonical"],
               channel=cr["pec"] if declare else "RECUPERARE", subject=subj,
               body="Comunicazione telematica della cancelleria. Si prega di non rispondere a questo indirizzo.",
               pages=[("text", wrap(paras))], principal_name="provvedimento.pdf",
               amount=None if amount is None else f"{amount:.2f}", amount_text=None if amount is None else eur(amount),
               pratica=pr)


# ---------------------------------------------------------------- public bodies
def public_act(ctx: Ctx, kind: str, edition: dict | None = None) -> Doc:
    """edition: {"pratica", "prev_ref", "prev_date", "new_amount"} for a revised notice."""
    r = ctx.rnd
    ex = f"EX-{2000 + ctx.seq}"
    ed_date = ctx.doc_date()
    if kind in ("cartella", "intimazione", "rateizzazione"):
        body_entity, sig = W.AGENCY, "agency"
    elif kind in ("accertamento_ae",):
        body_entity, sig = W.TAX_OFFICE, None
    elif kind == "accertamento_comune":
        body_entity, sig = W.MUNICIPALITY, None
    elif kind == "addebito":
        body_entity, sig = W.SOCIAL, None
    else:
        raise ValueError(kind)
    E = body_entity
    pr = edition["pratica"] if edition else f"PR-{kind[:3].upper()}-{ctx.seq:04d}"
    declare_contact = kind in ("cartella", "intimazione", "rateizzazione") and r.random() < 0.6
    head = [E["canonical"]]
    ref_lines = [f"Rif. pratica: {pr}", f"Rif. atto: {ex} del {ctx.d(ed_date, 'historical')}"]
    sup = []
    if edition:
        sup = [f"Il presente atto annulla e sostituisce l'atto n. {edition['prev_ref']} del "
               f"{ctx.d(dt.date.fromisoformat(edition['prev_date']), 'historical')}."]
    a = Decimal(edition["new_amount"]) if edition else None
    if kind == "cartella":
        a = a or ctx.amount(400, 30000)
        paras = head + ["", f"CARTELLA DI PAGAMENTO N. SYN-068-2026-{ctx.seq:06d}" + (" - RETTIFICA" if edition else "")] + ref_lines + [""] + sup + [
            f"Intestatario: {DEBTOR_UP}.",
            f"Ruolo reso esecutivo il {ctx.d(ctx.past(60, 120), 'historical')} dall'ente creditore.",
            f"Importo dovuto: € {eur(a)}.",
            f"Si intima il pagamento entro {ctx.rel_term(60, 'sessanta')} giorni dalla notificazione della presente "
            "cartella; decorso tale termine si procederà ad esecuzione forzata."]
        dt_, area, subj = "cartella_pagamento", "collection", f"Notifica cartella di pagamento n. SYN-068-2026-{ctx.seq:06d}"
    elif kind == "intimazione":
        a = a or ctx.amount(400, 30000)
        paras = head + ["", f"INTIMAZIONE DI PAGAMENTO N. SYN-INT-{ctx.seq:05d}"] + ref_lines + [""] + [
            f"Relativa alla cartella n. SYN-068-2025-{ctx.seq:06d} notificata il {ctx.d(ctx.past(200, 360), 'historical')}, "
            "rimasta senza pagamento.",
            f"Importo dovuto: € {eur(a)}.",
            f"Si intima il pagamento entro {ctx.rel_term(5, 'cinque')} giorni dalla notifica della presente intimazione."]
        dt_, area, subj = "intimazione_pagamento", "collection", f"Notifica intimazione di pagamento n. SYN-INT-{ctx.seq:05d}"
    elif kind == "rateizzazione":
        total = ctx.amount(8000, 60000)
        rata = a or (total / 12).quantize(Decimal("0.01"))
        a = rata
        first = ctx.future_workday(20, 55)
        paras = head + ["", "PIANO DI RATEIZZAZIONE" + (" - REVISIONE" if edition else "")] + ref_lines + [""] + sup + [
            f"In accoglimento dell'istanza presentata il {ctx.d(ctx.past(15, 40), 'historical')} da {DEBTOR_UP}, è concessa "
            "la rateizzazione del debito relativo alle cartelle indicate nel prospetto allegato.",
            f"Importo complessivo rateizzato: € {eur(total)}. Importo della rata: € {eur(rata)}. Numero rate: 12.",
            f"La prima rata scade il {ctx.d(first, 'actionable')}.",
            "In caso di mancato pagamento di cinque rate, anche non consecutive, il debitore decade dal beneficio."]
        if r.random() < 0.5:
            paras.append(f"Qualora la prima rata non sia versata entro il {ctx.d(first + dt.timedelta(days=15), 'conditional')}, "
                         "il piano si intenderà revocato.")
        dt_, area, subj = "provvedimento_rateizzazione", "collection", "Esito istanza di rateizzazione"
    elif kind in ("accertamento_ae", "accertamento_comune"):
        a = ctx.amount(1500, 90000)
        if kind == "accertamento_ae":
            title = f"AVVISO DI ACCERTAMENTO N. SYN-AVV-2026-{ctx.seq:05d}"
            recital = f"A seguito del processo verbale di constatazione del {ctx.d(ctx.past(90, 200), 'historical')}, l'Ufficio accerta maggiori imposte per il periodo d'imposta 2022."
            head2 = ["Direzione Provinciale di Esempio"]
            area = "tax"
        else:
            title = f"AVVISO DI ACCERTAMENTO IMU N. SYN-IMU-{ctx.seq:05d}"
            recital = f"Dalla verifica dei versamenti IMU per l'anno 2021, effettuata in data {ctx.d(ctx.past(30, 120), 'historical')}, risulta un omesso versamento."
            head2 = ["Ufficio Tributi"]
            area = "local_tax"
        paras = head + head2 + ["", title] + ref_lines + ["", f"Destinatario: {DEBTOR_ADDR}.", recital,
                                                          f"Importo dovuto: € {eur(a)}, comprensivo di imposta, sanzioni e interessi.",
                                                          f"Avverso il presente atto può essere proposto ricorso entro "
                                                          f"{ctx.rel_term(60, 'sessanta')} giorni dalla notificazione."]
        dt_, subj = "avviso_accertamento", "Notifica avviso di accertamento"
    elif kind == "addebito":
        a = a or ctx.amount(800, 40000)
        paras = head + ["Direzione Provinciale di Esempio", "", f"AVVISO DI ADDEBITO N. SYN-AVA-{ctx.seq:05d}"] + ref_lines + [""] + sup + [
            "Contributi previdenziali dovuti per il periodo 01/2025 - 12/2025.",
            f"Importo dovuto: € {eur(a)}.",
            f"Il pagamento deve essere effettuato entro {ctx.rel_term(60, 'sessanta')} giorni dalla notifica.",
            f"Entro {ctx.rel_term(40, 'quaranta')} giorni dalla notifica può essere proposta opposizione innanzi al "
            "Giudice del lavoro."]
        dt_, area, subj = "avviso_addebito", "social_security", f"Notifica avviso di addebito n. SYN-AVA-{ctx.seq:05d}"
    if declare_contact:
        paras.append(f"Per le comunicazioni: {W.AGENCY['contact']}")
    paras += [f"{E['canonical']} - Il Responsabile del procedimento"]
    channel = W.AGENCY["contact"] if declare_contact else E["pec"]
    doc = Doc(kind=kind, doc_type=dt_, area=area, sender_class="CORPORATE_PEC", sender_display=E["name"],
              sender_addr=E["pec"], transmitter=E["canonical"], author=E["canonical"], party=E["canonical"],
              channel=channel, subject=subj, body=f"Si notifica il documento allegato.\n{E['name']}",
              pages=[("text", wrap(paras))], principal_name=f"{dt_}.pdf", amount=f"{a:.2f}", amount_text=eur(a),
              pratica=pr, edition_ref=ex, edition_date=ed_date.isoformat(),
              supersedes_ref=edition["prev_ref"] if edition else None)
    if sig and r.random() < 0.5:
        doc.principal_sig = f"p7s:{sig}"
    return doc


# ---------------------------------------------------------------- companies
def company_act(ctx: Ctx, kind: str, cr: dict) -> Doc:
    pr = f"PR-{cr['key']}-{ctx.seq:04d}"
    a = ctx.amount(300, 25000)
    if kind == "diffida_company":
        f1 = ctx.past(90, 160)
        paras = [cr["canonical"], "", "DIFFIDA E MESSA IN MORA", f"Rif. pratica: {pr}", "", f"Spett.le {DEBTOR_UP},",
                 f"rileviamo che la fattura n. {200 + ctx.seq % 80} del {ctx.d(f1, 'historical')}, scaduta il "
                 f"{ctx.d(f1 + dt.timedelta(days=60), 'historical')}, risulta ancora insoluta.",
                 f"Con la presente Vi diffidiamo e costituiamo formalmente in mora, invitandoVi a corrispondere entro "
                 f"{ctx.rel_term(15, 'quindici')} giorni dal ricevimento della presente la somma di € {eur(a)}.",
                 "Decorso inutilmente tale termine, procederemo per vie legali senza ulteriore avviso.",
                 f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", f"{cr['canonical']} - Il legale rappresentante"]
        dt_, area, subj = "diffida_messa_in_mora", "out_of_court_recovery", "Diffida e messa in mora"
    else:
        f1 = ctx.past(50, 120)
        paras = [cr["canonical"], "", "SOLLECITO DI PAGAMENTO", f"Rif. pratica: {pr}", "", f"Spett.le {DEBTOR_UP},",
                 f"Vi ricordiamo che la fattura n. {70 + ctx.seq % 60} del {ctx.d(f1, 'historical')}, scaduta il "
                 f"{ctx.d(f1 + dt.timedelta(days=30), 'historical')}, per un importo di € {eur(a)}, risulta ancora insoluta.",
                 "Vi invitiamo a provvedere al pagamento con cortese sollecitudine.",
                 f"Esempio, {ctx.d(ctx.doc_date(), 'historical')}", f"{cr['canonical']} - Ufficio Amministrazione"]
        dt_, area, subj = "sollecito_pagamento", "out_of_court_recovery", "Sollecito di pagamento"
    return Doc(kind=kind, doc_type=dt_, area=area, sender_class="CORPORATE_PEC", sender_display=cr["name"],
               sender_addr=cr["pec"], transmitter=cr["canonical"], author=cr["canonical"], party=cr["canonical"],
               channel=cr["pec"], subject=subj, body="In allegato la comunicazione in oggetto.\nCordiali saluti\nUfficio Amministrazione",
               pages=[("text", wrap(paras))], principal_name=f"{dt_}.pdf", amount=f"{a:.2f}", amount_text=eur(a),
               pratica=pr)


# ---------------------------------------------------------------- debtor forwards
def target_forward(ctx: Ctx) -> Doc:
    r = ctx.rnd
    hint = r.choice(["precetto", "decreto", None])
    if hint == "precetto":
        subj, dt_, area = "Inoltro atto di precetto ricevuto a mezzo posta raccomandata", "atto_precetto", "pre_enforcement"
    elif hint == "decreto":
        subj, dt_, area = "Inoltro decreto ingiuntivo ricevuto a mezzo posta", "decreto_ingiuntivo", "payment_order"
    else:
        subj, dt_, area = f"Documento scansionato - protocollo n. SYN-PROT-{ctx.seq:04d}", None, None
    body = "Si inoltra per l'archiviazione l'atto pervenuto a mezzo posta raccomandata.\nUfficio Protocollo"
    hard = ["debtor_forward_scan"]
    r.random()  # keep the random stream stable; the trap is planted deterministically below
    if ctx.seq % 2 == 0:
        body += f"\nDocumento trasmesso nell'interesse di {DEBTOR_UP}, per la sola conservazione."
        hard.append("debtor_named_as_party_trap")
    return Doc(kind="target_forward", doc_type=dt_, area=area, sender_class="TARGET",
               sender_display="Fornace Aurelia S.r.l. - Protocollo", sender_addr=W.DEBTOR["forward_pec"],
               transmitter="@DEBTOR", author="RECUPERARE", party="RECUPERARE", channel="RECUPERARE", subject=subj,
               body=body, pages=[("image", ctx.seq * 7 + 1)], principal_name="scansione.pdf", hard=hard, scanned=True)
