"""One synthetic record through ``classify.classify_record`` (offline; no corpus, no pipeline run)."""
from __future__ import annotations

import datetime as dt
import json

from tests._util import AS_OF, ROOT
from pipeline import classify

CONFIG = json.loads((ROOT / "corpus" / "config.json").read_text(encoding="utf-8"))
CTX = classify.build_context(CONFIG, dt.datetime.fromisoformat(AS_OF))


def record(text, subject="Comunicazione", sender="amministrazione@pec.officinelagorai.example",
           when="2026-10-06T10:00:00+02:00", transport="ok", display="Officine Lagorai S.r.l.", body="",
           reply_to=None):
    env = {"record_id": "ARC-T", "envelope": "t.eml", "sha256": "0" * 64,
           "daticert": {"mittente": sender, "data": when, "oggetto": subject},
           "inner": {"from_display": display, "from_addr": sender, "body": body, "subject": subject}}
    if reply_to:
        env["inner"]["reply_to"] = reply_to
    sig = {"transport": {"signature_integrity": transport},
           "documents": [{"name": "a.pdf", "signature_integrity": "not_signed"}]}
    txt = {"documents": [{"name": "a.pdf", "text": text, "status": "OK"}], "principal": "a.pdf", "text_status": "OK"}
    return classify.classify_record(env, sig, txt, CTX)
