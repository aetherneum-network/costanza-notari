"""Deterministic TEST PKI. NOT FOR PRODUCTION - keys derive from a public seed.

    Aetherneum TEST Root CA ─┬─ Aetherneum TEST Firme CA ─┬─ lawyers (Moscardini, Olivieri, Mariscotti*)
                             │                            ├─ agency signer, court signer
                             └─ PEC gestori (transport signatures)
    Esempio UNTRUSTED Test CA ── Lupatelli   (not in the trust list -> chain unverifiable)

    * Mariscotti's certificate expires 2026-07-31 (tests validity at validation time).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from pipeline.lib import rsa, x509

UTC = dt.timezone.utc
O_SYN = "Aetherneum University (synthetic, TEST ONLY)"


@dataclass
class Identity:
    key: rsa.PrivateKey
    cert_der: bytes
    chain: list  # intermediate certs to embed (DER)


def _d(y, m, d):
    return dt.datetime(y, m, d, tzinfo=UTC)


def build(seed: int) -> dict:
    ids: dict[str, Identity] = {}
    root_k = rsa.generate("root-ca", seed)
    root_n = x509.name("Aetherneum TEST Root CA - NOT FOR PRODUCTION", o=O_SYN)
    root = x509.build_certificate(serial=1, issuer=root_n, subject=root_n, not_before=_d(2025, 1, 1),
                                  not_after=_d(2031, 1, 1), subject_key=root_k.public, issuer_key=root_k,
                                  issuer_pub=root_k.public, is_ca=True)
    ids["root"] = Identity(root_k, root, [])
    int_k = rsa.generate("firme-ca", seed)
    int_n = x509.name("Aetherneum TEST Firme CA - NOT FOR PRODUCTION", o=O_SYN)
    inter = x509.build_certificate(serial=2, issuer=root_n, subject=int_n, not_before=_d(2025, 1, 1),
                                   not_after=_d(2030, 1, 1), subject_key=int_k.public, issuer_key=root_k,
                                   issuer_pub=root_k.public, is_ca=True)
    ids["firme-ca"] = Identity(int_k, inter, [])
    unt_k = rsa.generate("untrusted-ca", seed)
    unt_n = x509.name("Esempio UNTRUSTED Test CA", o="Esempio Certificazioni (synthetic, TEST ONLY)")
    unt = x509.build_certificate(serial=1, issuer=unt_n, subject=unt_n, not_before=_d(2025, 1, 1),
                                 not_after=_d(2031, 1, 1), subject_key=unt_k.public, issuer_key=unt_k,
                                 issuer_pub=unt_k.public, is_ca=True)
    ids["untrusted-ca"] = Identity(unt_k, unt, [])

    def leaf(label, cn, o, email, issuer, issuer_name, issuer_key, serial, nb, na, chain):
        k = rsa.generate(label, seed)
        c = x509.build_certificate(serial=serial, issuer=issuer_name, subject=x509.name(cn, o=o),
                                   not_before=nb, not_after=na, subject_key=k.public, issuer_key=issuer_key,
                                   issuer_pub=issuer_key.public, is_ca=False, email=email)
        ids[label] = Identity(k, c, chain)

    leaf("gestore-G1", "GESTORE PEC ESEMPIO S.P.A. - firma di trasporto (TEST)", O_SYN,
         "posta-certificata@pec.gestore-uno.example", root, root_n, root_k, 101, _d(2025, 1, 1), _d(2029, 1, 1), [])
    leaf("gestore-G2", "POSTACERTA ESEMPIO S.R.L. - firma di trasporto (TEST)", O_SYN,
         "posta-certificata@postacerta-esempio.example", root, root_n, root_k, 102, _d(2025, 1, 1), _d(2029, 1, 1), [])
    leaf("lawyer-IM", "Avv. Ilaria Moscardini (TEST)", "Studio Legale Moscardini (synthetic)",
         "ilaria.moscardini@pec.ordineavvocati-esempio.example", inter, int_n, int_k, 1001,
         _d(2025, 3, 1), _d(2028, 3, 1), [inter])
    leaf("lawyer-TO", "Avv. Tancredi Olivieri (TEST)", "Studio Olivieri (synthetic)",
         "studio.olivieri@pec.professionisti.example", inter, int_n, int_k, 1002,
         _d(2025, 3, 1), _d(2028, 3, 1), [inter])
    leaf("lawyer-DM", "Avv. Donato Mariscotti (TEST)", "Studio Legale Mariscotti (synthetic)",
         "donato.mariscotti@pec.ordineavvocati-esempio.example", inter, int_n, int_k, 1003,
         _d(2024, 8, 1), dt.datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC), [inter])
    leaf("lawyer-SL", "Avv. Serena Lupatelli (TEST)", "Studio Legale Lupatelli (synthetic)",
         "avv.serenalupatelli@pec.legalmail-esempio.example", unt, unt_n, unt_k, 77,
         _d(2025, 3, 1), _d(2028, 3, 1), [])
    leaf("agency", "Agenzia Esempio Riscossione - firma documenti (TEST)", O_SYN,
         "protocollo@pec.agenzia-riscossione.example", inter, int_n, int_k, 2001, _d(2025, 1, 1), _d(2029, 1, 1), [inter])
    leaf("court", "Cancelliere - Tribunale di Esempio (TEST)", O_SYN,
         "esecuzioni.civili@civile.tribunale.example", inter, int_n, int_k, 3001, _d(2025, 1, 1), _d(2029, 1, 1), [inter])
    return ids


def write(ids: dict, out: Path) -> None:
    (out / "trust").mkdir(parents=True, exist_ok=True)
    (out / "certs").mkdir(parents=True, exist_ok=True)
    (out / "keys").mkdir(parents=True, exist_ok=True)
    (out / "trust" / "test-root-ca.pem").write_text(x509.pem(ids["root"].cert_der), encoding="ascii", newline="\n")
    (out / "README.txt").write_text(
        "TEST PKI - NOT FOR PRODUCTION.\nKeys are derived from the public corpus seed: anyone can recompute them.\n"
        "trust/ holds the ONLY trust anchor the pipeline accepts. The UNTRUSTED CA is deliberately absent from it.\n",
        encoding="ascii", newline="\n")
    for label in sorted(ids):
        (out / "certs" / f"{label}.pem").write_text(x509.pem(ids[label].cert_der), encoding="ascii", newline="\n")
        (out / "keys" / f"{label}.TEST-ONLY.key.pem").write_text(
            x509.pem(rsa.private_key_pkcs8_der(ids[label].key), "PRIVATE KEY"), encoding="ascii", newline="\n")
