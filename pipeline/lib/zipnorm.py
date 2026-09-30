"""Make OOXML (xlsx/docx) containers byte-deterministic.

openpyxl and python-docx write zip entries stamped with the wall clock and
the host OS, and openpyxl overwrites ``dcterms:modified`` with *now* on every
save. We rewrite the container with a fixed timestamp, fixed ``create_system``
and permissions, pinned core-property dates, same entry order and compression.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import zipfile
from pathlib import Path

_CORE_DATE = re.compile(rb"(<dcterms:(created|modified)\b[^>]*>)[^<]*(</dcterms:\2>)")


def normalize(path: os.PathLike | str, when: _dt.datetime) -> None:
    p = Path(path)
    utc = when.astimezone(_dt.timezone.utc) if when.tzinfo else when
    iso = utc.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    stamp = (max(utc.year, 1980), utc.month, utc.day, utc.hour, utc.minute, utc.second // 2 * 2)
    with zipfile.ZipFile(p, "r") as src:
        entries = [(i.filename, src.read(i.filename)) for i in src.infolist()]
    tmp = p.with_name(p.name + ".norm")
    with zipfile.ZipFile(tmp, "w") as dst:
        for name, data in entries:
            if name == "docProps/core.xml":
                data = _CORE_DATE.sub(lambda m: m.group(1) + iso + m.group(3), data)
            zi = zipfile.ZipInfo(name, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0
            dst.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    os.replace(tmp, p)
