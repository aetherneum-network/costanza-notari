"""Minimal DER (X.690) encoder/decoder.

Only what X.509 v3 certificates and CMS SignedData need. Definite lengths
only: BER indefinite-length input raises DERError, which the signature stage
reports as ``signature_integrity: "unparseable"`` rather than guessing.
"""
from __future__ import annotations

import datetime as _dt


class DERError(ValueError):
    pass


# --------------------------------------------------------------------- encode
def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _len(len(content)) + content


def seq(*items: bytes) -> bytes:
    return tlv(0x30, b"".join(items))


def set_of(*items: bytes) -> bytes:
    """DER SET OF: elements sorted by their encodings (X.690 11.6)."""
    return tlv(0x31, b"".join(sorted(items)))


def integer(n: int) -> bytes:
    if n < 0:
        raise DERError("negative integers not supported")
    body = b"\x00" if n == 0 else n.to_bytes((n.bit_length() + 8) // 8, "big")
    return tlv(0x02, body)


def oid(dotted: str) -> bytes:
    arcs = [int(x) for x in dotted.split(".")]
    body = bytearray([40 * arcs[0] + arcs[1]])
    for a in arcs[2:]:
        chunk = [a & 0x7F]
        a >>= 7
        while a:
            chunk.append(0x80 | (a & 0x7F))
            a >>= 7
        body += bytes(reversed(chunk))
    return tlv(0x06, bytes(body))


def null() -> bytes:
    return b"\x05\x00"


def boolean(v: bool) -> bytes:
    return tlv(0x01, b"\xff" if v else b"\x00")


def octet_string(b: bytes) -> bytes:
    return tlv(0x04, b)


def bit_string(b: bytes, unused_bits: int = 0) -> bytes:
    return tlv(0x03, bytes([unused_bits]) + b)


def utf8(s: str) -> bytes:
    return tlv(0x0C, s.encode("utf-8"))


def printable(s: str) -> bytes:
    return tlv(0x13, s.encode("ascii"))


def ia5(s: str) -> bytes:
    return tlv(0x16, s.encode("ascii"))


def utctime(t: _dt.datetime) -> bytes:
    t = t.astimezone(_dt.timezone.utc)
    return tlv(0x17, t.strftime("%y%m%d%H%M%SZ").encode())


def gentime(t: _dt.datetime) -> bytes:
    t = t.astimezone(_dt.timezone.utc)
    return tlv(0x18, t.strftime("%Y%m%d%H%M%SZ").encode())


def time_auto(t: _dt.datetime) -> bytes:
    """RFC 5280: UTCTime through 2049, GeneralizedTime from 2050."""
    return utctime(t) if t.year < 2050 else gentime(t)


def explicit(n: int, content: bytes) -> bytes:
    return tlv(0xA0 + n, content)


def implicit_prim(n: int, content: bytes) -> bytes:
    return tlv(0x80 + n, content)


# --------------------------------------------------------------------- decode
class Node:
    __slots__ = ("tag", "hstart", "start", "end", "buf")

    def __init__(self, tag, hstart, start, end, buf):
        self.tag, self.hstart, self.start, self.end, self.buf = tag, hstart, start, end, buf

    @property
    def raw(self) -> bytes:
        return bytes(self.buf[self.hstart:self.end])

    @property
    def content(self) -> bytes:
        return bytes(self.buf[self.start:self.end])

    @property
    def constructed(self) -> bool:
        return bool(self.tag & 0x20)

    def children(self) -> list["Node"]:
        out, pos = [], self.start
        while pos < self.end:
            n = read(self.buf, pos)
            out.append(n)
            pos = n.end
        if pos != self.end:
            raise DERError("child overrun")
        return out

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Node(tag=0x{self.tag:02x}, len={self.end - self.start})"


def read(buf: bytes, pos: int = 0) -> Node:
    if pos + 2 > len(buf):
        raise DERError("truncated TLV header")
    tag = buf[pos]
    if tag & 0x1F == 0x1F:
        raise DERError("high-tag-number form not supported")
    first = buf[pos + 1]
    p = pos + 2
    if first == 0x80:
        raise DERError("indefinite length (BER) not supported")
    if first & 0x80:
        n = first & 0x7F
        if n == 0 or n > 4 or p + n > len(buf):
            raise DERError("bad length")
        length = int.from_bytes(buf[p:p + n], "big")
        p += n
    else:
        length = first
    if p + length > len(buf):
        raise DERError("truncated content")
    return Node(tag, pos, p, p + length, buf)


def parse_int(node: Node) -> int:
    if node.tag != 0x02:
        raise DERError("expected INTEGER")
    return int.from_bytes(node.content, "big", signed=True)


def parse_oid(node: Node) -> str:
    if node.tag != 0x06:
        raise DERError("expected OID")
    b = node.content
    arcs = [b[0] // 40, b[0] % 40]
    val = 0
    for byte in b[1:]:
        val = (val << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(val)
            val = 0
    return ".".join(str(a) for a in arcs)


def parse_time(node: Node) -> _dt.datetime:
    s = node.content.decode("ascii")
    if node.tag == 0x17:
        yy = int(s[0:2])
        year = 2000 + yy if yy < 50 else 1900 + yy
        return _dt.datetime(year, int(s[2:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]),
                            int(s[10:12]), tzinfo=_dt.timezone.utc)
    if node.tag == 0x18:
        return _dt.datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]),
                            int(s[12:14]), tzinfo=_dt.timezone.utc)
    raise DERError("expected time")


def parse_string(node: Node) -> str:
    if node.tag in (0x0C,):
        return node.content.decode("utf-8")
    if node.tag in (0x13, 0x16, 0x14):
        return node.content.decode("latin-1")
    if node.tag == 0x1E:
        return node.content.decode("utf-16-be")
    raise DERError(f"unsupported string tag 0x{node.tag:02x}")


def octets(node: Node) -> bytes:
    """OCTET STRING content; tolerates constructed (0x24) segmented form."""
    if node.tag == 0x04:
        return node.content
    if node.tag == 0x24:
        return b"".join(octets(c) for c in node.children())
    raise DERError("expected OCTET STRING")
