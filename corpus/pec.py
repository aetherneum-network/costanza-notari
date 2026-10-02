"""Build Italian-PEC-shaped messages (synthetic) byte by byte.

Structure of the message as found in the recipient's mailbox (DPR 68/2005,
DM 2 Nov 2005 technical rules - shape only):

    multipart/signed (transport S/MIME signature of the PEC provider, smime.p7s)
    └── multipart/mixed
        ├── multipart/alternative   "Messaggio di posta certificata" (text + html)
        ├── daticert.xml            certification data (application/xml)
        └── postacert.eml           the original message (message/rfc822)
                └── multipart/mixed: body + attachments (.pdf / .pdf.p7m / .pdf.p7s)

Everything is CRLF and written by hand so that the signed bytes are exactly
the bytes on disk - the only way a detached signature can be re-verified.
"""
from __future__ import annotations

import base64
import datetime as dt
import email.utils
import hashlib
import quopri
from email.header import Header
from xml.sax.saxutils import escape

CRLF = b"\r\n"


def _hdr(s: str) -> str:
    try:
        s.encode("ascii")
        return s
    except UnicodeEncodeError:
        return Header(s, "utf-8").encode()


def _addr(display: str | None, addr: str) -> str:
    if not display:
        return addr
    return f"{_hdr(display) if not display.isascii() else chr(34) + display + chr(34)} <{addr}>"


def _crlf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _qp(text: str) -> bytes:
    return _crlf(quopri.encodestring(text.replace("\r\n", "\n").encode("utf-8")))


def _b64(data: bytes) -> bytes:
    return _crlf(base64.encodebytes(data))


def _boundary(tag: str, seed: str) -> str:
    return f"----=_{tag}_{hashlib.sha256(seed.encode()).hexdigest()[:24]}"


def _part(headers: list[str], body: bytes) -> bytes:
    return CRLF.join(h.encode("ascii") for h in headers) + CRLF + CRLF + body


def _multipart(boundary: str, parts: list[bytes], preamble: bytes = b"") -> bytes:
    out = preamble
    for p in parts:
        out += b"--" + boundary.encode() + CRLF + p + CRLF
    return out + b"--" + boundary.encode() + b"--" + CRLF


def inner_message(*, from_display: str, from_addr: str, to_addr: str, subject: str, when: dt.datetime,
                  msgid: str, body: str, attachments: list[tuple[str, str, bytes]], reply_to: str | None = None) -> bytes:
    b = _boundary("INNER", msgid)
    headers = [f"Date: {email.utils.format_datetime(when)}",
               f"From: {_addr(from_display, from_addr)}",
               f"To: {to_addr}"]
    if reply_to:
        headers.append(f"Reply-To: {reply_to}")
    headers += [f"Subject: {_hdr(subject)}", f"Message-ID: {msgid}", "MIME-Version: 1.0",
                f'Content-Type: multipart/mixed; boundary="{b}"']
    parts = [_part(["Content-Type: text/plain; charset=UTF-8", "Content-Transfer-Encoding: quoted-printable"],
                   _qp(body))]
    for name, ctype, data in attachments:
        parts.append(_part([f'Content-Type: {ctype}; name="{name}"', "Content-Transfer-Encoding: base64",
                            f'Content-Disposition: attachment; filename="{name}"'], _b64(data)))
    return CRLF.join(h.encode("ascii") for h in headers) + CRLF + CRLF + _multipart(b, parts)


def daticert(*, mittente: str, destinatario: str, oggetto: str, gestore: str, when: dt.datetime,
             identificativo: str, msgid: str, tipo: str = "posta-certificata") -> bytes:
    off = when.strftime("%z")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<postacert tipo="{tipo}" errore="nessuno">\n'
        "  <intestazione>\n"
        f"    <mittente>{escape(mittente)}</mittente>\n"
        f'    <destinatari tipo="certificato">{escape(destinatario)}</destinatari>\n'
        f"    <risposte>{escape(mittente)}</risposte>\n"
        f"    <oggetto>{escape(oggetto)}</oggetto>\n"
        "  </intestazione>\n"
        "  <dati>\n"
        f"    <gestore-emittente>{escape(gestore)}</gestore-emittente>\n"
        f'    <data zona="{off}">\n'
        f"      <giorno>{when.strftime('%d/%m/%Y')}</giorno>\n"
        f"      <ora>{when.strftime('%H:%M:%S')}</ora>\n"
        "    </data>\n"
        f"    <identificativo>{escape(identificativo)}</identificativo>\n"
        f"    <msgid>{escape(msgid)}</msgid>\n"
        "  </dati>\n"
        "</postacert>\n")
    return _crlf(xml.encode("utf-8"))


def outer_message(*, gestore_addr: str, gestore_name: str, mittente: str, destinatario: str, subject: str,
                  when: dt.datetime, identificativo: str, orig_msgid: str, inner: bytes, daticert_xml: bytes,
                  sign, tampered_daticert: bytes | None = None) -> bytes:
    """``sign(content_bytes) -> DER detached CMS``. ``tampered_daticert`` (test hook)
    replaces the certification data *after* signing: transport integrity must fail."""
    alt_b = _boundary("ALT", identificativo)
    mix_b = _boundary("MIX", identificativo)
    sig_b = _boundary("SIG", identificativo)
    txt = (f"Messaggio di posta certificata\n\nIl giorno {when.strftime('%d/%m/%Y')} alle ore "
           f"{when.strftime('%H:%M:%S')} ({when.strftime('%z')}) il messaggio\n\"{subject}\" è stato inviato da "
           f"\"{mittente}\"\nindirizzato a:\n{destinatario}\nIl messaggio originale è incluso in allegato.\n"
           f"Identificativo messaggio: {identificativo}\n")
    html = "<html><body><p>" + escape(txt).replace("\n", "<br/>") + "</p></body></html>\n"
    alt = _part([f'Content-Type: multipart/alternative; boundary="{alt_b}"'], _multipart(alt_b, [
        _part(["Content-Type: text/plain; charset=UTF-8", "Content-Transfer-Encoding: quoted-printable"], _qp(txt)),
        _part(["Content-Type: text/html; charset=UTF-8", "Content-Transfer-Encoding: quoted-printable"], _qp(html)),
    ]))

    def mixed(dc: bytes) -> bytes:
        return _part([f'Content-Type: multipart/mixed; boundary="{mix_b}"'], _multipart(mix_b, [
            alt,
            _part(['Content-Type: application/xml; name="daticert.xml"', "Content-Transfer-Encoding: base64",
                   'Content-Disposition: inline; filename="daticert.xml"'], _b64(dc)),
            _part(['Content-Type: message/rfc822; name="postacert.eml"',
                   'Content-Disposition: inline; filename="postacert.eml"'], inner),
        ]))

    signed_part = mixed(daticert_xml)
    sig = sign(signed_part)
    placed = mixed(tampered_daticert) if tampered_daticert is not None else signed_part
    headers = [f"Return-Path: <{gestore_addr}>",
               f"Date: {email.utils.format_datetime(when)}",
               f'From: "Per conto di: {mittente}" <{gestore_addr}>',
               f"Reply-To: {mittente}",
               f"To: {destinatario}",
               f"Subject: {_hdr('POSTA CERTIFICATA: ' + subject)}",
               f"Message-ID: <{identificativo}>",
               f"X-Riferimento-Message-ID: {orig_msgid}",
               "X-Trasporto: posta-certificata",
               "MIME-Version: 1.0",
               f'Content-Type: multipart/signed; protocol="application/pkcs7-signature"; micalg="sha-256"; '
               f'boundary="{sig_b}"']
    body = _multipart(sig_b, [placed, _part(['Content-Type: application/pkcs7-signature; name="smime.p7s"',
                                             "Content-Transfer-Encoding: base64",
                                             'Content-Disposition: attachment; filename="smime.p7s"'], _b64(sig))],
                      preamble=b"This is an S/MIME signed message" + CRLF + CRLF)
    return CRLF.join(h.encode("ascii") for h in headers) + CRLF + CRLF + body
