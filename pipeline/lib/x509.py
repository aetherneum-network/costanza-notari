"""X.509 v3 build/parse (RFC 5280 subset) for the synthetic TEST CA."""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
from dataclasses import dataclass, field

from . import der, rsa

OID_SHA256_RSA = "1.2.840.113549.1.1.11"
OID_RSA = "1.2.840.113549.1.1.1"
OID_CN, OID_O, OID_OU, OID_C, OID_EMAIL_ATTR = "2.5.4.3", "2.5.4.10", "2.5.4.11", "2.5.4.6", "1.2.840.113549.1.9.1"
OID_BC, OID_KU, OID_SKI, OID_AKI, OID_SAN = "2.5.29.19", "2.5.29.15", "2.5.29.14", "2.5.29.35", "2.5.29.17"

KU_DIGITAL_SIGNATURE, KU_NON_REPUDIATION, KU_KEY_CERT_SIGN, KU_CRL_SIGN = 0, 1, 5, 6


def name(cn: str, o: str | None = None, ou: str | None = None, c: str = "IT") -> bytes:
    rdns = []
    if c:
        rdns.append(der.set_of(der.seq(der.oid(OID_C), der.printable(c))))
    if o:
        rdns.append(der.set_of(der.seq(der.oid(OID_O), der.utf8(o))))
    if ou:
        rdns.append(der.set_of(der.seq(der.oid(OID_OU), der.utf8(ou))))
    rdns.append(der.set_of(der.seq(der.oid(OID_CN), der.utf8(cn))))
    return der.seq(*rdns)


def _alg_sha256_rsa() -> bytes:
    return der.seq(der.oid(OID_SHA256_RSA), der.null())


def spki(pub: rsa.PublicKey) -> bytes:
    rsapub = der.seq(der.integer(pub.n), der.integer(pub.e))
    return der.seq(der.seq(der.oid(OID_RSA), der.null()), der.bit_string(rsapub))


def key_id(pub: rsa.PublicKey) -> bytes:
    """RFC 5280 4.2.1.2 method (1): SHA-1 of the subjectPublicKey BIT STRING value."""
    return hashlib.sha1(der.seq(der.integer(pub.n), der.integer(pub.e))).digest()


def _key_usage(bits: list[int]) -> bytes:
    v = 0
    for b in bits:
        v |= 1 << (7 - b)
    unused = 0
    while unused < 7 and not (v >> unused) & 1:
        unused += 1
    return der.bit_string(bytes([v]), unused)


def _ext(oid_s: str, value: bytes, critical: bool = False) -> bytes:
    parts = [der.oid(oid_s)]
    if critical:
        parts.append(der.boolean(True))
    parts.append(der.octet_string(value))
    return der.seq(*parts)


def build_certificate(*, serial: int, issuer: bytes, subject: bytes, not_before: _dt.datetime,
                      not_after: _dt.datetime, subject_key: rsa.PublicKey, issuer_key: rsa.PrivateKey,
                      issuer_pub: rsa.PublicKey, is_ca: bool, email: str | None = None) -> bytes:
    exts = []
    if is_ca:
        exts.append(_ext(OID_BC, der.seq(der.boolean(True)), critical=True))
        exts.append(_ext(OID_KU, _key_usage([KU_KEY_CERT_SIGN, KU_CRL_SIGN]), critical=True))
    else:
        exts.append(_ext(OID_BC, der.seq(), critical=True))
        exts.append(_ext(OID_KU, _key_usage([KU_DIGITAL_SIGNATURE, KU_NON_REPUDIATION]), critical=True))
    exts.append(_ext(OID_SKI, der.octet_string(key_id(subject_key))))
    exts.append(_ext(OID_AKI, der.seq(der.implicit_prim(0, key_id(issuer_pub)))))
    if email:
        exts.append(_ext(OID_SAN, der.seq(der.implicit_prim(1, email.encode("ascii")))))
    tbs = der.seq(
        der.explicit(0, der.integer(2)),
        der.integer(serial),
        _alg_sha256_rsa(),
        issuer,
        der.seq(der.time_auto(not_before), der.time_auto(not_after)),
        subject,
        spki(subject_key),
        der.explicit(3, der.seq(*exts)),
    )
    sig = rsa.sign(issuer_key, tbs)
    return der.seq(tbs, _alg_sha256_rsa(), der.bit_string(sig))


def pem(der_bytes: bytes, label: str = "CERTIFICATE") -> str:
    b64 = base64.b64encode(der_bytes).decode()
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"


def unpem(text: str) -> list[bytes]:
    out, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("-----BEGIN"):
            cur = []
        elif line.startswith("-----END"):
            out.append(base64.b64decode("".join(cur)))
            cur = None
        elif cur is not None:
            cur.append(line)
    return out


@dataclass
class Certificate:
    der: bytes
    tbs: bytes
    serial: int
    issuer_raw: bytes
    subject_raw: bytes
    issuer: dict
    subject: dict
    not_before: _dt.datetime
    not_after: _dt.datetime
    public_key: rsa.PublicKey
    signature_alg: str
    signature: bytes
    is_ca: bool
    email: str | None = None
    extensions: dict = field(default_factory=dict)

    @property
    def fingerprint_sha256(self) -> str:
        return hashlib.sha256(self.der).hexdigest()

    def verify_signed_by(self, issuer: "Certificate") -> bool:
        if self.signature_alg != OID_SHA256_RSA:
            return False
        return rsa.verify(issuer.public_key, self.tbs, self.signature)


def _parse_name(node: der.Node) -> dict:
    out = {}
    for rdn in node.children():
        for atv in rdn.children():
            k, v = atv.children()
            key = {OID_CN: "CN", OID_O: "O", OID_OU: "OU", OID_C: "C", OID_EMAIL_ATTR: "E"}.get(
                der.parse_oid(k), der.parse_oid(k))
            out[key] = der.parse_string(v)
    return out


def parse_certificate(data: bytes) -> Certificate:
    root = der.read(data)
    tbs_n, alg_n, sig_n = root.children()
    t = tbs_n.children()
    i = 0
    if t[0].tag == 0xA0:
        i = 1
    serial = der.parse_int(t[i])
    issuer_n, validity_n, subject_n, spki_n = t[i + 2], t[i + 3], t[i + 4], t[i + 5]
    nb, na = (der.parse_time(x) for x in validity_n.children())
    alg_id, key_bits = spki_n.children()
    rsapub = der.read(key_bits.content[1:])
    n, e = (der.parse_int(x) for x in rsapub.children())
    is_ca, email, exts = False, None, {}
    for extra in t[i + 6:]:
        if extra.tag == 0xA3:
            for ext in extra.children()[0].children():
                parts = ext.children()
                eoid = der.parse_oid(parts[0])
                val = der.read(parts[-1].content)
                exts[eoid] = parts[-1].content
                if eoid == OID_BC:
                    kids = val.children()
                    is_ca = bool(kids and kids[0].tag == 0x01 and kids[0].content != b"\x00")
                elif eoid == OID_SAN:
                    for gn in val.children():
                        if gn.tag == 0x81:
                            email = gn.content.decode("ascii")
    return Certificate(
        der=data, tbs=tbs_n.raw, serial=serial, issuer_raw=issuer_n.raw, subject_raw=subject_n.raw,
        issuer=_parse_name(issuer_n), subject=_parse_name(subject_n), not_before=nb, not_after=na,
        public_key=rsa.PublicKey(n, e), signature_alg=der.parse_oid(alg_n.children()[0]),
        signature=sig_n.content[1:], is_ca=is_ca, email=email, extensions=exts,
    )
