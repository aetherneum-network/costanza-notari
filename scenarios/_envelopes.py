"""Deterministic builder of scenario envelopes (same TEST PKI as the corpus; all fictitious)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from scenarios._common import ROOT  # noqa: F401 (sys.path)
from corpus import pec, testca
from pipeline.lib import cms, pdfwrite, tzrome

SEED = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))["seed"]
GESTORE = ("GESTORE PEC ESEMPIO S.P.A.", "posta-certificata@pec.gestore-uno.example", "gestore-G1")


@lru_cache(maxsize=None)
def pki():
    return testca.build(SEED)


def rome(y, m, d, hh=10, mm=0):
    return tzrome.to_rome(tzrome.rome_local_to_utc(dt.datetime(y, m, d, hh, mm)))


def envelope(*, n: int, when: dt.datetime, sender_display: str, sender_addr: str, to_addr: str, subject: str,
             body: str, lines: list[str], name: str = "atto.pdf", p7m_identity: str | None = None) -> bytes:
    ids = pki()
    utc = when.astimezone(tzrome.UTC)
    pdf = pdfwrite.build_pdf([("text", lines)])
    if p7m_identity:
        idn = ids[p7m_identity]
        blob = cms.sign(pdf, idn.cert_der, idn.key, signing_time=utc - dt.timedelta(hours=2), extra_certs=idn.chain)
        atts = [(name + ".p7m", "application/pkcs7-mime", blob)]
    else:
        atts = [(name, "application/pdf", pdf)]
    msgid = f"<SCN-{n:04d}.{utc.strftime('%Y%m%d%H%M%S')}@{sender_addr.split('@')[1]}>"
    ident = f"opec-syn.{utc.strftime('%Y%m%d%H%M%S')}.9{n:04d}@pec.gestore-uno.example"
    inner = pec.inner_message(from_display=sender_display, from_addr=sender_addr, to_addr=to_addr, subject=subject,
                              when=when, msgid=msgid, body=body, attachments=atts)
    dc = pec.daticert(mittente=sender_addr, destinatario=to_addr, oggetto=subject, gestore=GESTORE[0], when=when,
                      identificativo=ident, msgid=msgid)
    g = ids[GESTORE[2]]
    return pec.outer_message(gestore_addr=GESTORE[1], gestore_name=GESTORE[0], mittente=sender_addr,
                             destinatario=to_addr, subject=subject, when=when, identificativo=ident, orig_msgid=msgid,
                             inner=inner, daticert_xml=dc,
                             sign=lambda c: cms.sign(c, g.cert_der, g.key, signing_time=utc, detached=True))


def write_input(dirpath: Path, envelopes: dict[str, bytes]) -> None:
    files = []
    for rel, data in sorted(envelopes.items()):
        p = dirpath / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest()})
    (dirpath / "manifest.json").write_text(json.dumps({"expected_envelopes": len(files), "files": files}, indent=2)
                                           + "\n", encoding="utf-8", newline="\n")
