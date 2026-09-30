"""Stage 2 - PEC envelope parse (.eml, daticert.xml, postacert.eml).

Evidence files are never modified: attachments are *copied* into the work
area, and the exact bytes covered by the provider's transport signature are
extracted by boundary (re-serialising MIME would change them).
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .lib import jsonio
from .s1_enumerate import extended


def _boundary(ctype: str) -> str | None:
    m = re.search(r'boundary="?([^";]+)"?', ctype or "", re.I)
    return m.group(1) if m else None


def signed_part_bytes(raw: bytes) -> tuple[bytes | None, bytes | None]:
    """(signed content, base64 smime.p7s body) of a multipart/signed message."""
    head_end = raw.find(b"\r\n\r\n")
    if head_end < 0:
        return None, None
    headers = raw[:head_end].decode("ascii", errors="replace")
    unfolded = re.sub(r"\r\n[ \t]+", " ", headers)
    ct = re.search(r"^Content-Type:\s*(.+)$", unfolded, re.I | re.M)
    if not ct or "multipart/signed" not in ct.group(1).lower():
        return None, None
    b = _boundary(ct.group(1)).encode()
    delim = b"--" + b + b"\r\n"
    start = raw.find(delim, head_end)
    if start < 0:
        return None, None
    start += len(delim)
    end = raw.find(b"\r\n--" + b, start)
    content = raw[start:end]
    sig_start = end + len(b"\r\n--" + b + b"\r\n")
    sig_end = raw.find(b"\r\n--" + b + b"--", sig_start)
    sig_part = raw[sig_start:sig_end]
    body_at = sig_part.find(b"\r\n\r\n")
    return content, sig_part[body_at + 4:] if body_at >= 0 else None


def parse_daticert(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)

    def t(path):
        el = root.find(path)
        return el.text.strip() if el is not None and el.text else None

    data = root.find("dati/data")
    zona = data.get("zona") if data is not None else None
    giorno, ora = t("dati/data/giorno"), t("dati/data/ora")
    iso = None
    if giorno and ora and zona:
        d, m, y = giorno.split("/")
        iso = f"{y}-{m}-{d}T{ora}{zona[:3]}:{zona[3:]}"
    return {"tipo": root.get("tipo"), "errore": root.get("errore"), "mittente": t("intestazione/mittente"),
            "destinatari": [e.text for e in root.findall("intestazione/destinatari")],
            "risposte": t("intestazione/risposte"), "oggetto": t("intestazione/oggetto"),
            "gestore_emittente": t("dati/gestore-emittente"), "data": iso,
            "identificativo": t("dati/identificativo"), "msgid": t("dati/msgid")}


def _addr(h) -> tuple[str, str]:
    name, addr = email.utils.parseaddr(str(h or ""))
    return name, addr.lower()


def parse_envelope(raw: bytes, att_dir: Path, base: Path | None = None) -> dict:
    base = base or att_dir

    def rel(x: Path) -> str:
        return x.relative_to(base).as_posix()

    out: dict = {"errors": []}
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    out["outer"] = {"from": str(msg.get("From", "")), "subject": str(msg.get("Subject", "")),
                    "date": str(msg.get("Date", "")), "message_id": str(msg.get("Message-ID", "")),
                    "x_trasporto": str(msg.get("X-Trasporto", ""))}
    signed, p7s_b64 = signed_part_bytes(raw)
    att_dir.mkdir(parents=True, exist_ok=True)
    if signed is not None:
        (att_dir / "_transport_signed_part.bin").write_bytes(signed)
        import base64
        (att_dir / "_transport_smime.p7s").write_bytes(base64.b64decode(p7s_b64 or b""))
        out["transport"] = {"signed_part": rel(att_dir / "_transport_signed_part.bin"),
                            "signature": rel(att_dir / "_transport_smime.p7s"),
                            "signed_part_sha256": hashlib.sha256(signed).hexdigest()}
    else:
        out["transport"] = None
        out["errors"].append("no multipart/signed transport envelope")
    dc, inner = None, None
    for part in msg.walk():
        fn = part.get_filename()
        if fn == "daticert.xml":
            dc = part.get_payload(decode=True)
        elif part.get_content_type() == "message/rfc822" and inner is None:
            inner = part.get_payload()[0] if isinstance(part.get_payload(), list) else part.get_payload()
    out["daticert"] = parse_daticert(dc) if dc else None
    if dc is None:
        out["errors"].append("daticert.xml missing")
    if inner is None:
        out["errors"].append("postacert.eml missing")
        out["inner"], out["attachments"] = None, []
        return out
    fdisp, faddr = _addr(inner.get("From"))
    _, rto = _addr(inner.get("Reply-To"))
    body = ""
    atts = []
    for part in inner.walk():
        if part.is_multipart():
            continue
        fn = part.get_filename()
        if fn:
            data = part.get_payload(decode=True) or b""
            safe = re.sub(r"[^A-Za-z0-9._() -]", "_", fn)
            p = att_dir / f"{len(atts):02d}_{safe}"
            p.write_bytes(data)
            atts.append({"name": fn, "content_type": part.get_content_type(), "size": len(data),
                         "sha256": hashlib.sha256(data).hexdigest(), "path": rel(p)})
        elif part.get_content_type() == "text/plain" and not body:
            body = part.get_content()
    out["inner"] = {"from_display": fdisp, "from_addr": faddr, "to": str(inner.get("To", "")),
                    "reply_to": rto or None, "subject": str(inner.get("Subject", "")),
                    "date": str(inner.get("Date", "")), "message_id": str(inner.get("Message-ID", "")),
                    "body": body.replace("\r\n", "\n").strip()}
    out["attachments"] = atts
    return out


def run(input_root: Path, enum_state: dict, work_dir: Path, out_path: Path) -> dict:
    records = []
    for r in enum_state["records"]:
        raw = open(extended(Path(input_root) / r["envelope"]), "rb").read()
        if hashlib.sha256(raw).hexdigest() != r["sha256"]:
            raise RuntimeError(f"{r['envelope']} changed between stage 1 and stage 2")
        try:
            parsed = parse_envelope(raw, work_dir / "att" / r["record_id"], work_dir)
        except Exception as exc:  # parse failure: recorded, never guessed
            parsed = {"errors": [f"parse failure: {type(exc).__name__}: {exc}"], "inner": None, "attachments": [],
                      "daticert": None, "transport": None}
        records.append({"record_id": r["record_id"], "envelope": r["envelope"], "sha256": r["sha256"], **parsed})
    state = {"stage": "s2_envelope", "records": records,
             "errors": sum(1 for x in records if x["errors"])}
    jsonio.write(out_path, state)
    return state
