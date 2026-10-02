import unittest

from tests._util import tmpdir
from pipeline import ocr, s4_text
from pipeline.lib import pdfwrite

TEXT = ["TRIBUNALE DI ESEMPIO", "COMUNICAZIONE DI CANCELLERIA", "rinviato l'udienza al 14/01/2027"]


class TextRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir("s4")
        (self.d / "text.pdf").write_bytes(pdfwrite.build_pdf([("text", TEXT)]))
        (self.d / "scan.pdf").write_bytes(pdfwrite.build_pdf([("image", pdfwrite.scan_raster(1))]))
        (self.d / "mixed.pdf").write_bytes(pdfwrite.build_pdf([("text", TEXT), ("image", pdfwrite.scan_raster(2))]))

    def test_text_layer(self):
        r = s4_text.extract_pdf(self.d / "text.pdf", ocr.UnavailableOcr(), 25, 0.8)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["pages"][0]["method"], "text_layer")
        self.assertIn("14/01/2027", r["text"])

    def test_scan_without_ocr_is_recuperare(self):
        r = s4_text.extract_pdf(self.d / "scan.pdf", ocr.UnavailableOcr(), 25, 0.8)
        self.assertEqual(r["status"], "RECUPERARE")
        self.assertEqual(r["pages"][0]["note"], "OCR fallback: not available in this environment")
        self.assertIsNone(r["pages"][0]["confidence"])

    def test_mixed_is_partial_page_level(self):
        r = s4_text.extract_pdf(self.d / "mixed.pdf", ocr.UnavailableOcr(), 25, 0.8)
        self.assertEqual((r["status"], r["recuperare_pages"]), ("PARTIAL", [2]))

    def test_ocr_confidence_threshold(self):
        low = ocr.FixtureOcr({("scan.pdf", 0): ("ATTO DI PRECETTO", 0.62)})
        high = ocr.FixtureOcr({("scan.pdf", 0): ("ATTO DI PRECETTO", 0.93)})
        r_low = s4_text.extract_pdf(self.d / "scan.pdf", low, 25, 0.8)
        r_high = s4_text.extract_pdf(self.d / "scan.pdf", high, 25, 0.8)
        self.assertEqual((r_low["status"], r_low["text"]), ("RECUPERARE", ""))
        self.assertEqual((r_high["status"], r_high["pages"][0]["method"]), ("OK", "ocr"))
        self.assertIn("PRECETTO", r_high["text"])

    def test_default_engine_here_is_unavailable_or_real(self):
        e = ocr.default_engine()
        self.assertIn(e.name, ("none", "tesseract"))


if __name__ == "__main__":
    unittest.main()
