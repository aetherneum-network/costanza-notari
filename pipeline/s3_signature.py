"""Stage 3 - signatures. Contributed by Adèle Maurique (synthetic alumna).

Two questions, two fields, never merged:

* ``signature_integrity``  - do the signed bytes match? ("ok" | "failed" |
  "unparseable" | "not_signed"). Pure mathematics: digest + RSA over the
  CAdES signed attributes.
* ``signer_chain_verified`` - does the signer certificate chain up to a trust
  anchor we accept, valid at the validation time? (true | false, with
  ``chain_status``). The ONLY trust anchor accepted is the synthetic TEST root
  in ``corpus/out/testca/trust``. "Extracted" never implies "verified" (L8).

Time-of-signing semantics (see docs/SIGNATURES.md):

* ``claimed_signing_time`` is the CMS signingTime attribute. It is asserted by
  the signer and is NOT trusted: no RFC 3161 timestamp token is present.
* ``validation_time`` is the PEC provider's timestamp from daticert.xml - the
  earliest *third-party* evidence that the signed object existed (the p7m is
  inside postacert.eml, covered by the provider's transport signature). The
  chain is evaluated at that instant. If the transport signature itself fails,
  the validation time is marked unverified.
* No CRL/OCSP: ``revocation_checked: false``. Qualified status (eIDAS / CAD)
  is ``not_assessed``. [TO CONFIRM with counsel] before relying on any of this
  for legal effect.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .lib import cms, der, jsonio, tzrome, x509

VALIDATION_TIME_SOURCE = "daticert.xml (PEC provider timestamp; third-party, covered by transport signature)"


def load_trust_anchors(trust_dir: Path) -> list[x509.Certificate]:
    anchors = []
    for p in sorted(Path(trust_dir).glob("*.pem")):
        for d in x509.unpem(p.read_text(encoding="ascii")):
            anchors.append(x509.parse_certificate(d))
    return anchors


def validate_chain(signer: x509.Certificate, pool: list[x509.Certificate], anchors: list[x509.Certificate],
                   at: _dt.datetime | None) -> tuple[bool, str, list[str]]:
    """Path building from signer to an anchor. Returns (verified, status, path_subjects)."""
    anchor_der = {a.der for a in anchors}
    path, cur = [signer.subject.get("CN", "?")], signer
    for _ in range(6):
        if at is None:
            return False, "no_validation_time", path
        if not (cur.not_before <= at <= cur.not_after):
            return False, ("expired_at_validation_time" if at > cur.not_after else "not_yet_valid_at_validation_time"), path
        if cur.der in anchor_der:
            return True, "verified", path
        issuers = [c for c in anchors + pool if c.subject_raw == cur.issuer_raw and c.der != cur.der]
        issuer = next((c for c in issuers if cur.verify_signed_by(c)), None)
        if issuer is None:
            if cur.issuer_raw == cur.subject_raw:
                return False, "untrusted_issuer", path + ["(self-signed root not in trust list)"]
            return False, ("untrusted_issuer" if not issuers else "bad_certificate_signature"), path
        if not issuer.is_ca:
            return False, "issuer_not_ca", path
        path.append(issuer.subject.get("CN", "?"))
        cur = issuer
    return False, "path_too_long", path


def check(blob: bytes, anchors, validation_time, detached_content: bytes | None = None) -> dict:
    res = {"signature_integrity": "unparseable", "signer_chain_verified": False, "chain_status": "not_checked",
           "signer": None, "claimed_signing_time": None, "validation_time": None,
           "validation_time_source": VALIDATION_TIME_SOURCE, "revocation_checked": False,
           "qualified_status": "not_assessed", "notes": []}
    try:
        info = cms.parse(blob)
    except (der.DERError, ValueError, IndexError) as exc:
        res["notes"].append(f"CMS parse error: {exc}")
        return res
    ok, reasons = cms.verify_integrity(info, detached_content)
    res["signature_integrity"] = "ok" if ok else "failed"
    res["notes"] += reasons
    signer = info.signer_certificate()
    if info.signing_time:
        res["claimed_signing_time"] = info.signing_time.isoformat()
    if signer is not None:
        res["signer"] = {"cn": signer.subject.get("CN"), "o": signer.subject.get("O"), "email": signer.email,
                         "serial": signer.serial, "issuer_cn": signer.issuer.get("CN"),
                         "not_after": signer.not_after.isoformat(), "sha256": signer.fingerprint_sha256}
        vt = validation_time
        res["validation_time"] = vt.isoformat() if vt else None
        verified, status, path = validate_chain(signer, info.certificates, anchors, vt)
        res["signer_chain_verified"], res["chain_status"], res["chain_path"] = verified, status, path
        if info.signing_time and signer is not None:
            res["valid_at_claimed_signing_time"] = signer.not_before <= info.signing_time <= signer.not_after
            if vt and info.signing_time > vt:
                res["notes"].append("claimed signing time is AFTER the PEC timestamp: impossible, claim ignored")
    else:
        res["chain_status"] = "no_signer_certificate"
    res["_content"] = info.content
    return res


def run(env_state: dict, work_dir: Path, trust_dir: Path, out_path: Path) -> dict:
    anchors = load_trust_anchors(trust_dir)
    records = []
    for r in env_state["records"]:
        dc = r.get("daticert") or {}
        pec_time = tzrome.parse_iso(dc["data"]) if dc.get("data") else None
        entry = {"record_id": r["record_id"], "transport": None, "attachments": [], "documents": []}
        if r.get("transport"):
            signed = (work_dir / r["transport"]["signed_part"]).read_bytes()
            sig = (work_dir / r["transport"]["signature"]).read_bytes()
            t = check(sig, anchors, pec_time.astimezone(tzrome.UTC) if pec_time else None, detached_content=signed)
            t.pop("_content", None)
            entry["transport"] = t
        transport_ok = bool(entry["transport"] and entry["transport"]["signature_integrity"] == "ok")
        vt = pec_time.astimezone(tzrome.UTC) if (pec_time and transport_ok) else None
        atts = {a["name"]: a for a in r.get("attachments", [])}
        for a in r.get("attachments", []):
            name, path = a["name"], work_dir / a["path"]
            low = name.lower()
            if low.endswith(".p7m"):
                res = check(path.read_bytes(), anchors, vt)
                content = res.pop("_content", None)
                if vt is None:
                    res["notes"].append("validation time unverified: transport signature not ok")
                entry["attachments"].append({"file": name, "format": "CAdES-attached", **res})
                if content is not None:
                    out = path.with_name(path.name[:-4])
                    out.write_bytes(content)
                    entry["documents"].append({"name": name[:-4], "path": out.relative_to(work_dir).as_posix(),
                                               "source": "extracted from .p7m", "signature_file": name,
                                               "signature_integrity": res["signature_integrity"],
                                               "signer_chain_verified": res["signer_chain_verified"],
                                               "signer_cn": (res.get("signer") or {}).get("cn")})
            elif low.endswith(".p7s"):
                data_name = name[:-4]
                data = atts.get(data_name)
                content = (work_dir / data["path"]).read_bytes() if data else None
                res = check(path.read_bytes(), anchors, vt, detached_content=content)
                res.pop("_content", None)
                if data is None:
                    res["notes"].append(f"detached signature without its data file {data_name}")
                entry["attachments"].append({"file": name, "format": "CAdES-detached", "covers": data_name, **res})
            elif low.endswith(".pdf"):
                entry["documents"].append({"name": name, "path": a["path"], "source": "plain attachment",
                                           "signature_file": None, "signature_integrity": "not_signed",
                                           "signer_chain_verified": False, "signer_cn": None})
        sigmap = {x["covers"]: x for x in entry["attachments"] if x.get("covers")}
        for d in entry["documents"]:
            if d["name"] in sigmap:
                s = sigmap[d["name"]]
                d.update({"signature_file": s["file"], "signature_integrity": s["signature_integrity"],
                          "signer_chain_verified": s["signer_chain_verified"],
                          "signer_cn": (s.get("signer") or {}).get("cn")})
        records.append(entry)
    summary = {"transport_failed": sum(1 for e in records if not e["transport"] or
                                       e["transport"]["signature_integrity"] != "ok"),
               "attachment_signatures": sum(len(e["attachments"]) for e in records),
               "integrity_failed": sum(1 for e in records for a in e["attachments"] if a["signature_integrity"] != "ok"),
               "chain_unverified": sum(1 for e in records for a in e["attachments"] if not a["signer_chain_verified"])}
    state = {"stage": "s3_signature", "trust_anchors": [a.subject.get("CN") for a in anchors],
             "policy": {"validation_time_source": VALIDATION_TIME_SOURCE, "revocation_checked": False,
                        "qualified_status": "not_assessed",
                        "legal_value": "[TO CONFIRM with counsel] no legal conclusion is drawn from these fields"},
             "summary": summary, "records": records}
    jsonio.write(out_path, state)
    return state
