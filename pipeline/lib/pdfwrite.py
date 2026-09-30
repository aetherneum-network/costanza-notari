"""Tiny deterministic PDF 1.4 writer (no dependencies).

* text pages: Helvetica with WinAnsiEncoding, so Italian accents (è, à, È) and
  the typographic apostrophe (’) survive extraction;
* image pages: a DeviceGray FlateDecode raster with *no* text layer - what a
  scanner produces. Text extraction returns nothing; OCR is the only way in.
"""
from __future__ import annotations

import zlib


def _pdf_string(s: str) -> bytes:
    raw = s.encode("cp1252", errors="replace")
    out = bytearray(b"(")
    for b in raw:
        if b in (0x28, 0x29, 0x5C):
            out += b"\\" + bytes([b])
        elif b < 0x20 or b > 0x7E:
            out += b"\\%03o" % b
        else:
            out.append(b)
    out += b")"
    return bytes(out)


def _text_stream(lines: list[str]) -> bytes:
    parts = [b"BT", b"/F1 10 Tf", b"13 TL", b"50 800 Td"]
    for i, line in enumerate(lines):
        if i:
            parts.append(b"T*")
        parts.append(_pdf_string(line) + b" Tj")
    parts.append(b"ET")
    return b"\n".join(parts)


def scan_raster(seed: int, width: int = 300, height: int = 420) -> tuple[int, int, bytes]:
    """Grey page with dark bars that look like lines of text on a scan."""
    import random
    rnd = random.Random(seed)
    rows = []
    for y in range(height):
        row = bytearray([236 + (y * 7 + seed) % 12]) * width
        band = (y - 30) // 14
        if 30 <= y < height - 40 and (y - 30) % 14 < 6:
            x0 = 25
            x1 = width - 25 - (rnd.randrange(0, 80) if band % 5 == 4 else 0)
            for x in range(x0, x1):
                if (x // 7 + band) % 6 != 0:
                    row[x] = 40 + (x * 13 + y * 5) % 50
        rows.append(bytes(row))
    return width, height, b"".join(rows)


def build_pdf(pages: list[tuple[str, object]], *, title: str | None = None) -> bytes:
    """pages: list of ("text", [lines]) or ("image", (w, h, gray_bytes))."""
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    catalog = add(b"")  # placeholder 1
    pages_id = add(b"")  # placeholder 2
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kids = []
    for kind, payload in pages:
        if kind == "text":
            data = zlib.compress(_text_stream(payload), 9)
            content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
            res = b"<< /Font << /F1 %d 0 R >> >>" % font
        elif kind == "image":
            w, h, gray = payload
            data = zlib.compress(gray, 9)
            img = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                      b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (w, h, len(data))
                      + data + b"\nendstream")
            draw = b"q 595 0 0 842 0 0 cm /Im1 Do Q"
            content = add(b"<< /Length %d >>\nstream\n" % len(draw) + draw + b"\nendstream")
            res = b"<< /XObject << /Im1 %d 0 R >> >>" % img
        else:
            raise ValueError(kind)
        page = add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Resources %s /Contents %d 0 R >>"
                   % (pages_id, res, content))
        kids.append(page)
    objs[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
    objs[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    info = None
    if title:
        info = add(b"<< /Title " + _pdf_string(title) + b" /Producer (costanza-notari-v2 synthetic corpus) >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    trailer = b"<< /Size %d /Root %d 0 R" % (len(objs) + 1, catalog)
    if info:
        trailer += b" /Info %d 0 R" % info
    out += b"trailer\n" + trailer + b" >>\nstartxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)
