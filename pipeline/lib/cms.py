"""CMS SignedData (RFC 5652) with CAdES-BES signed attributes (ETSI EN 319 122-1).

Build (for the synthetic corpus) and parse/verify (for the signature stage).
Integrity verification here answers exactly one question: *do these bytes
match what the signer's key signed?* It says nothing about who the signer is;
chain validation is a separate step (``pipeline.s3_signature``).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field

from . import der, rsa, x509

ID_DATA = "1.2.840.113549.1.7.1"
ID_SIGNED_DATA = "1.2.840.113549.1.7.2"
ID_SHA256 = "2.16.840.1.101.3.4.2.1"
ID_RSA = "1.2.840.113549.1.1.1"
ID_SHA256_RSA = "1.2.840.113549.1.1.11"
ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"
ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"
ATTR_SIGNING_TIME = "1.2.840.113549.1.9.5"
ATTR_SIGNING_CERT_V2 = "1.2.840.113549.1.9.16.2.47"


def _attr(oid_s: str, value: bytes) -> bytes:
    return der.seq(der.oid(oid_s), der.set_of(value))


def sign(content: bytes, signer_cert_der: bytes, signer_key: rsa.PrivateKey, *,
         signing_time: _dt.datetime, extra_certs: list[bytes] | None = None,
         detached: bool = False, tamper_encapsulated: bytes | None = None) -> bytes:
    """``tamper_encapsulated`` is a TEST-ONLY hook: it embeds different bytes
    than the ones digested, producing a signature whose integrity must fail."""
    cert = x509.parse_certificate(signer_cert_der)
    attrs = der.set_of(
        _attr(ATTR_CONTENT_TYPE, der.oid(ID_DATA)),
        _attr(ATTR_SIGNING_TIME, der.utctime(signing_time)),
        _attr(ATTR_MESSAGE_DIGEST, der.octet_string(hashlib.sha256(content).digest())),
        # SigningCertificateV2 { certs SEQUENCE OF ESSCertIDv2 { certHash } } (sha256 default)
        _attr(ATTR_SIGNING_CERT_V2, der.seq(der.seq(der.seq(der.octet_string(
            hashlib.sha256(signer_cert_der).digest()))))),
    )
    signature = rsa.sign(signer_key, attrs)  # signed over the SET OF (tag 0x31)
    signed_attrs_implicit = b"\xa0" + attrs[1:]
    sid = der.seq(cert.issuer_raw, der.integer(cert.serial))
    digest_alg = der.seq(der.oid(ID_SHA256))
    signer_info = der.seq(der.integer(1), sid, digest_alg, signed_attrs_implicit,
                          der.seq(der.oid(ID_RSA), der.null()), der.octet_string(signature))
    encap = der.seq(der.oid(ID_DATA)) if detached else der.seq(
        der.oid(ID_DATA), der.explicit(0, der.octet_string(
            content if tamper_encapsulated is None else tamper_encapsulated)))
    certs = sorted([signer_cert_der] + list(extra_certs or []))
    signed_data = der.seq(der.integer(1), der.set_of(digest_alg), encap,
                          der.tlv(0xA0, b"".join(certs)), der.set_of(signer_info))
    return der.seq(der.oid(ID_SIGNED_DATA), der.explicit(0, signed_data))


@dataclass
class SignedDataInfo:
    content: bytes | None
    certificates: list[x509.Certificate]
    signer_issuer_raw: bytes
    signer_serial: int
    digest_alg: str
    signature_alg: str
    signature: bytes
    signed_attrs_der: bytes | None
    attrs: dict = field(default_factory=dict)
    signing_time: _dt.datetime | None = None
    message_digest: bytes | None = None
    signing_cert_hash: bytes | None = None

    def signer_certificate(self) -> x509.Certificate | None:
        for c in self.certificates:
            if c.issuer_raw == self.signer_issuer_raw and c.serial == self.signer_serial:
                return c
        return None


def parse(blob: bytes) -> SignedDataInfo:
    ci = der.read(blob)
    ctype, wrapped = ci.children()
    if der.parse_oid(ctype) != ID_SIGNED_DATA:
        raise der.DERError("not SignedData")
    sd = wrapped.children()[0].children()
    idx = 3
    encap = sd[2].children()
    content = None
    if len(encap) > 1:
        content = der.octets(encap[1].children()[0])
    certs: list[x509.Certificate] = []
    if sd[idx].tag == 0xA0:
        for c in sd[idx].children():
            certs.append(x509.parse_certificate(c.raw))
        idx += 1
    if sd[idx].tag == 0xA1:  # CRLs: ignored (no revocation checking - documented)
        idx += 1
    signer_infos = sd[idx].children()
    if len(signer_infos) != 1:
        raise der.DERError("exactly one SignerInfo supported")
    si = signer_infos[0].children()
    sid = si[1]
    if sid.tag != 0x30:
        raise der.DERError("subjectKeyIdentifier sid not supported")
    issuer_n, serial_n = sid.children()
    digest_alg = der.parse_oid(si[2].children()[0])
    pos = 3
    signed_attrs_der, attrs = None, {}
    if si[pos].tag == 0xA0:
        signed_attrs_der = b"\x31" + si[pos].raw[1:]
        for a in si[pos].children():
            a_oid, a_vals = a.children()
            attrs[der.parse_oid(a_oid)] = [v.raw for v in a_vals.children()]
        pos += 1
    sig_alg = der.parse_oid(si[pos].children()[0])
    signature = si[pos + 1].content
    info = SignedDataInfo(content=content, certificates=certs, signer_issuer_raw=issuer_n.raw,
                          signer_serial=der.parse_int(serial_n), digest_alg=digest_alg,
                          signature_alg=sig_alg, signature=signature,
                          signed_attrs_der=signed_attrs_der, attrs=attrs)
    if ATTR_SIGNING_TIME in attrs:
        info.signing_time = der.parse_time(der.read(attrs[ATTR_SIGNING_TIME][0]))
    if ATTR_MESSAGE_DIGEST in attrs:
        info.message_digest = der.octets(der.read(attrs[ATTR_MESSAGE_DIGEST][0]))
    if ATTR_SIGNING_CERT_V2 in attrs:
        try:
            s = der.read(attrs[ATTR_SIGNING_CERT_V2][0]).children()[0].children()[0].children()
            h = [x for x in s if x.tag == 0x04]
            info.signing_cert_hash = h[0].content if h else None
        except (der.DERError, IndexError):
            info.signing_cert_hash = None
    return info


def verify_integrity(info: SignedDataInfo, detached_content: bytes | None = None) -> tuple[bool, list[str]]:
    """Return (ok, reasons). ok=True means: content digest matches and the RSA
    signature over the signed attributes verifies with the embedded signer cert."""
    reasons: list[str] = []
    content = info.content if info.content is not None else detached_content
    if content is None:
        return False, ["no content (detached signature without data)"]
    if info.digest_alg != ID_SHA256:
        return False, [f"unsupported digest {info.digest_alg}"]
    cert = info.signer_certificate()
    if cert is None:
        return False, ["signer certificate not embedded"]
    if info.signed_attrs_der is None:
        return False, ["no signed attributes (not CAdES-BES)"]
    if info.message_digest != hashlib.sha256(content).digest():
        reasons.append("messageDigest mismatch: content altered after signing")
    if info.signing_cert_hash is not None and info.signing_cert_hash != hashlib.sha256(cert.der).digest():
        reasons.append("signingCertificateV2 does not match embedded signer certificate")
    if info.signature_alg not in (ID_RSA, ID_SHA256_RSA):
        reasons.append(f"unsupported signature algorithm {info.signature_alg}")
    elif not rsa.verify(cert.public_key, info.signed_attrs_der, info.signature):
        reasons.append("RSA signature over signed attributes does not verify")
    return (not reasons), reasons
