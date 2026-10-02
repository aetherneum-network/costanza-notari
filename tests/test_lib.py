import datetime as dt
import hashlib
import io
import json
import subprocess
import unittest

from tests._util import ROOT, openssl, tmpdir  # noqa: F401  (sets sys.path)
from pipeline.lib import cms, der, jsonio, pdfwrite, rsa, tzrome, x509, zipnorm

UTC = dt.timezone.utc


def _pki():
    ca = rsa.generate("t-root", 7, bits=1024)
    leaf = rsa.generate("t-leaf", 7, bits=1024)
    rn = x509.name("Unit TEST Root", o="unit tests")
    root = x509.build_certificate(serial=1, issuer=rn, subject=rn, not_before=dt.datetime(2025, 1, 1, tzinfo=UTC),
                                  not_after=dt.datetime(2030, 1, 1, tzinfo=UTC), subject_key=ca.public, issuer_key=ca,
                                  issuer_pub=ca.public, is_ca=True)
    lc = x509.build_certificate(serial=9, issuer=rn, subject=x509.name("Unit TEST Signer"),
                                not_before=dt.datetime(2025, 1, 1, tzinfo=UTC),
                                not_after=dt.datetime(2028, 1, 1, tzinfo=UTC), subject_key=leaf.public, issuer_key=ca,
                                issuer_pub=ca.public, is_ca=False, email="signer@unit.example")
    return ca, leaf, root, lc


class DerTests(unittest.TestCase):
    def test_integer_and_oid_roundtrip(self):
        for n in (0, 1, 127, 128, 255, 256, 2 ** 64 + 5):
            self.assertEqual(der.parse_int(der.read(der.integer(n))), n)
        for o in ("1.2.840.113549.1.9.16.2.47", "2.5.29.19", "2.16.840.1.101.3.4.2.1"):
            self.assertEqual(der.parse_oid(der.read(der.oid(o))), o)

    def test_set_of_is_sorted(self):
        a, b = der.integer(5), der.integer(3)
        self.assertEqual(der.set_of(a, b), der.set_of(b, a))

    def test_indefinite_length_is_refused(self):
        with self.assertRaises(der.DERError):
            der.read(b"\x30\x80\x00\x00")


class RsaX509CmsTests(unittest.TestCase):
    def test_keygen_is_deterministic_and_signature_verifies(self):
        k1, k2 = rsa.generate("same", 1, bits=1024), rsa.generate("same", 1, bits=1024)
        self.assertEqual(k1, k2)
        sig = rsa.sign(k1, b"hello")
        self.assertTrue(rsa.verify(k1.public, b"hello", sig))
        self.assertFalse(rsa.verify(k1.public, b"hellO", sig))

    def test_certificate_parse(self):
        _, _, root, lc = _pki()
        c, r = x509.parse_certificate(lc), x509.parse_certificate(root)
        self.assertEqual(c.subject["CN"], "Unit TEST Signer")
        self.assertEqual(c.email, "signer@unit.example")
        self.assertFalse(c.is_ca)
        self.assertTrue(r.is_ca)
        self.assertTrue(c.verify_signed_by(r))

    def test_cms_attached_detached_and_tamper(self):
        _, leaf, _, lc = _pki()
        t = dt.datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
        blob = cms.sign(b"%PDF content", lc, leaf, signing_time=t)
        info = cms.parse(blob)
        self.assertEqual(cms.verify_integrity(info), (True, []))
        self.assertEqual(info.signing_time, t)
        det = cms.sign(b"%PDF content", lc, leaf, signing_time=t, detached=True)
        self.assertTrue(cms.verify_integrity(cms.parse(det), b"%PDF content")[0])
        self.assertFalse(cms.verify_integrity(cms.parse(det), b"%PDF c0ntent")[0])
        bad = cms.sign(b"%PDF content", lc, leaf, signing_time=t, tamper_encapsulated=b"%PDF CONTENT")
        ok, why = cms.verify_integrity(cms.parse(bad))
        self.assertFalse(ok)
        self.assertIn("messageDigest mismatch", why[0])

    def test_openssl_accepts_our_cms(self):
        ossl = openssl()
        if not ossl:
            self.skipTest("openssl not available")
        _, leaf, root, lc = _pki()
        d = tmpdir("lib-openssl")
        (d / "root.pem").write_text(x509.pem(root))
        (d / "a.p7m").write_bytes(cms.sign(b"data\n", lc, leaf, signing_time=dt.datetime(2026, 1, 2, tzinfo=UTC)))
        r = subprocess.run([ossl, "cms", "-verify", "-binary", "-inform", "DER", "-in", str(d / "a.p7m"), "-CAfile",
                            str(d / "root.pem"), "-purpose", "any", "-out", str(d / "out.bin")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((d / "out.bin").read_bytes(), b"data\n")


class PdfJsonTzZipTests(unittest.TestCase):
    def test_pdf_text_and_scan(self):
        import pypdf
        b = pdfwrite.build_pdf([("text", ["SOCIETÀ AGRICOLA VALLE DELL’ÈRTO", "importo € 3.415,20"]),
                                ("image", pdfwrite.scan_raster(3))])
        r = pypdf.PdfReader(io.BytesIO(b))
        self.assertIn("DELL’ÈRTO", r.pages[0].extract_text())
        self.assertEqual(r.pages[1].extract_text().strip(), "")
        self.assertEqual(b, pdfwrite.build_pdf([("text", ["SOCIETÀ AGRICOLA VALLE DELL’ÈRTO", "importo € 3.415,20"]),
                                                ("image", pdfwrite.scan_raster(3))]))

    def test_backslash_repair_is_logged(self):
        d = tmpdir("lib-json")
        p = d / "handoff.json"
        p.write_text('{"path": "C:\\Users\\Enzo\\x", "ok": "\\u00e8"}', encoding="utf-8")
        log = []
        obj = jsonio.load_lenient(p, log)
        self.assertEqual(obj["path"], "C:\\Users\\Enzo\\x")
        self.assertEqual(obj["ok"], "è")
        self.assertEqual(log[0]["repairs"], 3)

    def test_rome_dst(self):
        self.assertEqual(tzrome.offset_at_utc(dt.datetime(2026, 10, 25, 0, 59, tzinfo=UTC)), tzrome.CEST)
        self.assertEqual(tzrome.offset_at_utc(dt.datetime(2026, 10, 25, 1, 0, tzinfo=UTC)), tzrome.CET)
        self.assertEqual(tzrome.offset_at_utc(dt.datetime(2026, 3, 29, 1, 0, tzinfo=UTC)), tzrome.CEST)
        with self.assertRaises(ValueError):
            tzrome.rome_local_to_utc(dt.datetime(2026, 3, 29, 2, 30))  # the skipped hour

    def test_zip_normalisation_is_deterministic(self):
        from openpyxl import Workbook
        d = tmpdir("lib-zip")
        hs = []
        for i in range(2):
            wb = Workbook()
            wb.active["A1"] = "x"
            p = d / f"{i}.xlsx"
            wb.save(p)
            zipnorm.normalize(p, dt.datetime(2026, 10, 21, 7, 40, tzinfo=UTC))
            hs.append(hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(hs[0], hs[1])


class CorpusTests(unittest.TestCase):
    def test_generator_policy_matches_rules(self):
        from corpus.reference_terms import GOLD_TERMS
        terms = {t["doc_type"]: t for t in json.loads((ROOT / "rules" / "terms.json").read_text(encoding="utf-8"))["terms"]}
        for dt_, (days, susp, sat, after21) in GOLD_TERMS.items():
            t = terms[dt_]
            self.assertEqual((t["days"], t["feriale_suspension"], t["saturday_rollover"], t["pec_after_21_rule"]),
                             (days, susp, sat, after21), dt_)
        from corpus import generate
        self.assertEqual(generate.EXPECTS_DEADLINE,
                         set(json.loads((ROOT / "rules" / "terms.json").read_text(encoding="utf-8"))["expects_deadline"]))

    def test_no_real_domains_in_gold(self):
        import re
        text = (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8")
        for addr in re.findall(r"[\w.+-]+@([\w.-]+)", text):
            self.assertTrue(addr.endswith(".example"), addr)


if __name__ == "__main__":
    unittest.main()
