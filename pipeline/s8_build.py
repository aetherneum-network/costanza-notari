"""Stage 8 - master index (XLSX, openpyxl) and report (DOCX, python-docx). Rebuilt, never edited.

Both files are build artefacts of the ledger view: same ledger + same as_of
-> byte-identical files (fixed core properties, fixed zip timestamps).
The header always shows *Data as of* (L3); a red banner shows BLOCKED/FAILED
runs and stale data (L4). RECUPERARE is bold red on yellow, everywhere.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import deadlines as dl, entities as ent, urgency as urg
from .amounts import format_amount
from .lib import jsonio, tzrome, zipnorm
from .rules_engine import RULES_DIR
from .s7_ledger import edition_label

RECUPERARE = "RECUPERARE"
LEVELS = ["MAXIMUM", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]
HEADERS = ["Counterparty (party)", "Area", "Document type", "Urgency", "Deadline", "Deadline nature",
           "Deadline status", "Days left", "Amount (edition-bound)", "Dossier ref.", "Transmitter", "Author",
           "Sender class", "Counterparty channel", "Signature integrity", "Signer chain verified",
           "Transport signature", "Text", "RECUPERARE fields", "Record", "base_id"]
WIDTHS = [34, 20, 30, 15, 12, 14, 12, 9, 44, 22, 34, 30, 17, 40, 16, 16, 14, 12, 30, 10, 16]


def _fill(hex_):
    return PatternFill("solid", start_color=hex_, end_color=hex_)


def _show(v):
    if v == ent.DEBTOR_SENTINEL:
        return "- debtor (internal forward) -"
    return "-" if v in (None, "") else v


def rows_from_view(view: list[dict], as_of: _dt.datetime, terms_cfg: dict) -> list[dict]:
    out = []
    for unit in view:
        f = unit["facts"]
        drec = f.get("deadline") == RECUPERARE
        drv = None if drec else dl.driving_deadline(f.get("deadlines") or [], as_of.date())
        level, _, days = urg.compute(f.get("doc_type"), drv, drec, as_of.date())
        amt = f.get("amount_due") or {}
        amount_label = edition_label(amt) or (RECUPERARE if "amount_due" in (f.get("recuperare_fields") or []) else "-")
        out.append({
            "party": f.get("party_entity"), "area": f.get("area"), "doc_type": f.get("doc_type"), "urgency": level,
            "deadline": RECUPERARE if drec else (drv or {}).get("date"), "nature": (drv or {}).get("nature"),
            "status": (drv or {}).get("status"), "days": days, "amount": amount_label,
            "amount_value": amt.get("v") if amt.get("v") not in (None, RECUPERARE) else None,
            "pratica": f.get("pratica"), "transmitter": f.get("transmitter_entity"), "author": f.get("author_entity"),
            "sender_class": f.get("sender_class"), "channel": f.get("counterparty_channel"),
            "sig_integrity": f.get("principal_signature_integrity"),
            "sig_chain": "yes" if f.get("principal_signer_chain_verified") else (
                "NO" if f.get("principal_signature_integrity") not in (None, "not_signed") else "-"),
            "transport": f.get("transport_signature_integrity"), "text": f.get("text_status"),
            "recuperare": ", ".join(f.get("recuperare_fields") or []) or "-", "record": f.get("record_id"),
            "base_id": unit["base_id"], "reasons": f.get("recuperare_reasons") or {},
            "deadlines": f.get("deadlines") or [], "edition": unit["edition"], "history": unit["history"],
        })
    rank = {lv: i for i, lv in enumerate(LEVELS)}
    out.sort(key=lambda r: (r["party"] or "~", rank[r["urgency"]], r["deadline"] or "9999", r["record"]))
    return out


def write_xlsx(path: Path, rows, *, as_of, title, banner, banner_kind, stale_after, register, signatures,
               notes, colors) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Index"
    local = tzrome.to_rome(as_of)
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Data as of {local.strftime('%Y-%m-%d %H:%M')} (Europe/Rome, UTC{local.strftime('%z')[:3]}:{local.strftime('%z')[3:]})"
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = banner
    kind_fill = {"ok": "C6EFCE", "blocked": "C00000", "failed": "C00000", "stale": "C00000"}[banner_kind]
    ws["A3"].fill = _fill(kind_fill)
    ws["A3"].font = Font(bold=True, color="FFFFFF" if banner_kind != "ok" else "006100", size=12)
    ws.merge_cells("A3:U3")
    ws["A4"] = (f"SYNTHETIC DATA - every entity is fictitious. Data are STALE after {stale_after}. "
                "Rebuilt from the ledger on every run: do not edit by hand.")
    ws["A4"].font = Font(italic=True, color="7F7F7F")
    hr = 6
    for c, h in enumerate(HEADERS, start=1):
        cell = ws.cell(row=hr, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _fill("1F3864")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(c)].width = WIDTHS[c - 1]
    rec_font, rec_fill = Font(bold=True, color=colors[RECUPERARE]["font"]), _fill(colors[RECUPERARE]["fill"])
    for i, r in enumerate(rows, start=hr + 1):
        vals = [_show(r["party"]), _show(r["area"]), _show(r["doc_type"]), r["urgency"], _show(r["deadline"]),
                _show(r["nature"]), _show(r["status"]), r["days"] if r["days"] is not None else "-", r["amount"],
                _show(r["pratica"]), _show(r["transmitter"]), _show(r["author"]), _show(r["sender_class"]),
                _show(r["channel"]), _show(r["sig_integrity"]), r["sig_chain"], _show(r["transport"]),
                _show(r["text"]), r["recuperare"], r["record"], r["base_id"]]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=i, column=c, value=v)
            if isinstance(v, str) and v.startswith(RECUPERARE):
                cell.font, cell.fill = rec_font, rec_fill
        u = ws.cell(row=i, column=4)
        col = colors[r["urgency"]]
        u.fill, u.font = _fill(col["fill"]), Font(bold=col["bold"], color=col["font"])
    last = hr + max(1, len(rows))
    rng = f"A{hr + 1}:U{last}"
    for lv in LEVELS:
        col = colors[lv]
        ws.conditional_formatting.add(f"D{hr + 1}:D{last}", CellIsRule(
            operator="equal", formula=[f'"{lv}"'], fill=_fill(col["fill"]), font=Font(bold=col["bold"], color=col["font"])))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'NOT(ISERROR(SEARCH("{RECUPERARE}",A{hr + 1})))'],
                                                   fill=rec_fill, font=rec_font))
    ws.freeze_panes = f"A{hr + 1}"
    ws.auto_filter.ref = f"A{hr}:U{last}"

    by = {}
    for r in rows:
        k = r["party"] or RECUPERARE
        b = by.setdefault(k, {"units": 0, "urg": 4, "next": None, "total": 0.0, "rec": 0})
        b["units"] += 1
        b["urg"] = min(b["urg"], LEVELS.index(r["urgency"]))
        if r["deadline"] not in (None, RECUPERARE) and r["status"] == "open":
            b["next"] = min(filter(None, [b["next"], r["deadline"]]))
        if r["amount_value"]:
            b["total"] = round(b["total"] + float(r["amount_value"]), 2)
        b["rec"] += 0 if r["recuperare"] == "-" else 1
    s2 = wb.create_sheet("By counterparty")
    s2.append(["Counterparty", "Units", "Highest urgency", "Next open deadline", "Total current amounts",
               "Units with RECUPERARE"])
    for k in sorted(by):
        b = by[k]
        s2.append([_show(k), b["units"], LEVELS[b["urg"]], b["next"] or "-", b["total"], b["rec"]])
    s3 = wb.create_sheet("Deadlines")
    s3.append(["Date", "Nature", "Days left", "Record", "Counterparty", "Document type", "Basis"])
    dls = []
    for r in rows:
        for d in r["deadlines"]:
            dls.append([d["date"], d["nature"], (_dt.date.fromisoformat(d["date"]) - as_of.date()).days, r["record"],
                        _show(r["party"]), _show(r["doc_type"]), d.get("rule_id") or d.get("rule") or "-"])
    for row in sorted(dls):
        s3.append(row)
    s4 = wb.create_sheet("Signatures")
    s4.append(["Record", "File", "Format", "signature_integrity", "signer_chain_verified", "chain_status", "Signer",
               "Claimed signing time (untrusted)", "Validation time (PEC timestamp)"])
    for row in signatures:
        s4.append(row)
    s5 = wb.create_sheet(RECUPERARE)
    s5.append(["Record", "Field", "Why (complete by hand, then fix the rule or the source)"])
    for r in rows:
        for fld in (r["recuperare"].split(", ") if r["recuperare"] != "-" else []):
            s5.append([r["record"], fld, r["reasons"].get(fld, "-")])
    for row in s5.iter_rows(min_row=2, max_col=2, min_col=2):
        for cell in row:
            cell.font, cell.fill = rec_font, rec_fill
    s6 = wb.create_sheet("Superseded values")
    s6.append(["Register id", "Field", "Old", "New", "Since", "Proof (document)", "Supersedes", "Owners", "Counterparty"])
    for e in register:
        s6.append([e["id"], e["field"], e["old"], e["new"], e["since"], e["proof"]["document"],
                   e["proof"]["supersedes"], ", ".join(e["owners"]), _show(e["counterparty"])])
    s7 = wb.create_sheet("Notes")
    for line in notes:
        s7.append([line])
    t = as_of.astimezone(tzrome.UTC).replace(tzinfo=None)
    wb.properties.creator = "Costanza Notari (synthetic alumna) - pipeline v2"
    wb.properties.lastModifiedBy = "pipeline.s8_build"
    wb.properties.title = title
    wb.properties.created = t
    wb.properties.modified = t
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    zipnorm.normalize(path, as_of)


def write_docx(path: Path, rows, *, as_of, title, banner, banner_kind, judgement, register, sentinel, sig_summary,
               notes) -> None:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    doc.add_heading(title, level=0)
    p = doc.add_paragraph()
    run = p.add_run("SYNTHETIC - every company, person, address and amount in this report is fictitious.")
    run.italic = True
    local = tzrome.to_rome(as_of)
    p = doc.add_paragraph()
    r = p.add_run(f"Data as of {local.strftime('%Y-%m-%d %H:%M')} (Europe/Rome)")
    r.bold, r.font.size = True, Pt(12)
    p = doc.add_paragraph()
    r = p.add_run(banner)
    r.bold = True
    r.font.color.rgb = RGBColor(0x00, 0x61, 0x00) if banner_kind == "ok" else RGBColor(0xC0, 0x00, 0x00)

    doc.add_heading("Summary", level=1)
    t = doc.add_table(rows=1, cols=2)
    t.style = "Table Grid"
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Measure", "Value"
    counts = {lv: sum(1 for x in rows if x["urgency"] == lv) for lv in LEVELS}
    summary = [("Documentary units (current editions)", len(rows))] + [(f"Urgency {lv}", counts[lv]) for lv in LEVELS] + [
        ("Units with at least one RECUPERARE field", sum(1 for x in rows if x["recuperare"] != "-")),
        ("Expired terms (need a decision today)", sum(1 for x in rows if x["status"] == "expired")),
        ("Handoffs checked / anchor mismatches", f"{sentinel['handoffs_checked']} / {len(sentinel['mismatches'])}"),
        ("Signatures: integrity ok / failed", f"{sig_summary['ok']} / {sig_summary['failed']}"),
        ("Signatures: signer chain verified / NOT verified", f"{sig_summary['chain_yes']} / {sig_summary['chain_no']}")]
    for k, v in summary:
        c = t.add_row().cells
        c[0].text, c[1].text = k, str(v)

    doc.add_heading("Reading of the night (judgement)", level=1)
    for line in judgement:
        doc.add_paragraph(line)

    doc.add_heading("Open deadlines in the next 30 days", level=1)
    soon = [x for x in rows if x["status"] == "open" and x["days"] is not None and x["days"] <= 30]
    t = doc.add_table(rows=1, cols=6)
    t.style = "Table Grid"
    for i, h in enumerate(["Deadline", "Days", "Nature", "Document type", "Counterparty", "Record"]):
        t.rows[0].cells[i].text = h
    for x in sorted(soon, key=lambda x: (x["deadline"], x["record"])):
        c = t.add_row().cells
        for i, v in enumerate([x["deadline"], str(x["days"]), x["nature"], x["doc_type"], _show(x["party"]), x["record"]]):
            c[i].text = str(v)

    doc.add_heading("Superseded values (edition-bound)", level=1)
    if not register:
        doc.add_paragraph("None.")
    for e in register:
        old = format_amount(e["old"]) if e["field"] == "amount_due" else e["old"]
        new = format_amount(e["new"]) if e["field"] == "amount_due" else e["new"]
        doc.add_paragraph(f"{e['field']}: {new} - per notice ref. {e['proof']['document']} of {e['since']} "
                          f"(supersedes {old} of ref. {e['proof']['supersedes']}); owners: {', '.join(e['owners'])}.",
                          style="List Bullet")

    doc.add_heading("RECUPERARE - to be completed by a human", level=1)
    t = doc.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    for i, h in enumerate(["Record", "Field", "Why"]):
        t.rows[0].cells[i].text = h
    for x in rows:
        for fld in (x["recuperare"].split(", ") if x["recuperare"] != "-" else []):
            c = t.add_row().cells
            c[0].text, c[2].text = x["record"], str(x["reasons"].get(fld, "-"))
            rr = c[1].paragraphs[0].add_run(f"RECUPERARE: {fld}")
            rr.bold, rr.font.color.rgb = True, RGBColor(0xFF, 0x00, 0x00)

    doc.add_heading("Handoff sentinel", level=1)
    if sentinel["mismatches"]:
        for mm in sentinel["mismatches"]:
            doc.add_paragraph(f"handoff {mm['handoff_file']} (from {mm['handoff_from']}) vs receipt "
                              f"{mm['receipt_file']} (by {mm['receipt_by']}): anchor {mm['anchor']} "
                              f"sent {mm['sent']} / understood {mm['understood']}", style="List Bullet")
    else:
        doc.add_paragraph(f"{sentinel['handoffs_checked']} handoffs checked; every anchor restated identically.")

    doc.add_heading("Notes and legal assumptions", level=1)
    for line in notes:
        doc.add_paragraph(line, style="List Bullet")

    cp = doc.core_properties
    t0 = as_of.astimezone(tzrome.UTC).replace(tzinfo=None)
    cp.author, cp.last_modified_by = "Costanza Notari (synthetic alumna)", "pipeline.s8_build"
    cp.title, cp.subject, cp.comments = title, "Procedural report (synthetic)", "Build artefact - do not edit by hand."
    cp.created = cp.modified = cp.last_printed = t0
    cp.revision = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    zipnorm.normalize(path, as_of)


def notes_lines(terms_cfg: dict, holidays: dict, ocr_note: str | None, rule_versions: dict) -> list[str]:
    out = ["Synthetic proof pack: all data fictitious (.example domains, TEST CA only).",
           "Rule versions: " + ", ".join(f"{k} {v}" for k, v in sorted(rule_versions.items())),
           "Signatures: signature_integrity and signer_chain_verified are separate facts; chain validated only "
           "against the synthetic TEST root, at the PEC provider timestamp; no revocation checking. "
           "[TO CONFIRM with counsel] before any legal use.",
           "Deadline arithmetic: " + terms_cfg["rule_implemented"],
           terms_cfg["notification_date_note"]]
    for t in terms_cfg["terms"]:
        out.append(f"{t['id']} {t['doc_type']}: {t['legal_basis']} - {t['to_confirm']}")
    for h in holidays["fixed"]:
        if h.get("to_confirm"):
            out.append(f"Holiday {h['mm_dd']} {h['name']}: {h['to_confirm']}")
    out.append(holidays["note"])
    if ocr_note:
        out.append(ocr_note + ": scanned-only pages are RECUPERARE.")
    return out


def run(ledger_state: dict, sig_state: dict, sentinel: dict, config: dict, as_of: _dt.datetime, out_dir: Path, *,
        run_status: str, banner: str, banner_kind: str, judgement: list[str] | None, mode: str = "full",
        ocr_note: str | None = None, rule_versions: dict | None = None) -> dict:
    terms_cfg = jsonio.read(RULES_DIR / "terms.json")
    holidays = jsonio.read(RULES_DIR / "holidays.json")
    colors = jsonio.read(RULES_DIR / "urgency.json")["colors"]
    stale_h = jsonio.read(RULES_DIR / "misc.json")["staleness"]["max_age_hours"]
    stale_after = tzrome.to_rome(as_of + _dt.timedelta(hours=stale_h)).strftime("%Y-%m-%d %H:%M")
    rows = rows_from_view(ledger_state["view"], as_of, terms_cfg)
    title = f"Master index - {config['debtor']['canonical']} (debtor) - synthetic corpus"
    sigs, s = [], {"ok": 0, "failed": 0, "chain_yes": 0, "chain_no": 0}
    for rec in sig_state["records"]:
        for a in rec["attachments"]:
            sigs.append([rec["record_id"], a["file"], a["format"], a["signature_integrity"],
                         "true" if a["signer_chain_verified"] else "false", a["chain_status"],
                         (a.get("signer") or {}).get("cn") or "-", a.get("claimed_signing_time") or "-",
                         a.get("validation_time") or "-"])
            s["ok" if a["signature_integrity"] == "ok" else "failed"] += 1
            s["chain_yes" if a["signer_chain_verified"] else "chain_no"] += 1
    notes = notes_lines(terms_cfg, holidays, ocr_note, rule_versions or {})
    register = ledger_state["superseded_values"]
    out = {"stage": "s8_build", "mode": mode, "rows": len(rows), "files": {}}
    xlsx = Path(out_dir) / "master_index.xlsx"
    write_xlsx(xlsx, rows, as_of=as_of, title=title, banner=banner, banner_kind=banner_kind, stale_after=stale_after,
               register=register, signatures=sigs, notes=notes, colors=colors)
    out["files"]["master_index.xlsx"] = str(xlsx)
    if mode == "full":
        docx = Path(out_dir) / "report.docx"
        write_docx(docx, rows, as_of=as_of, title=f"Procedural report - {config['debtor']['canonical']}",
                   banner=banner, banner_kind=banner_kind, judgement=judgement or [], register=register,
                   sentinel=sentinel, sig_summary=s, notes=notes)
        out["files"]["report.docx"] = str(docx)
    ts = as_of.timestamp()
    for p in out["files"].values():  # logical time, not wall clock: build artefacts are "as of"
        os.utime(p, (ts, ts))
    out["urgency_counts"] = {lv: sum(1 for x in rows if x["urgency"] == lv) for lv in LEVELS}
    out["recuperare_units"] = sum(1 for x in rows if x["recuperare"] != "-")
    return out
