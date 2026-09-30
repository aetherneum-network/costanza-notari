# S08 - 300-character paths and accented names

*Company (synthetic): Società Agricola Valle dell'Èrto - Lesson L8 "Platform hardening".*

**Failure reproduced.** A tree of 40 envelopes, 15 of them beyond 300 characters once placed under
`build/scenarios/S08/tree`, with accented and typographic characters (`à`, `È`, `’`, `–`). On Windows
without `LongPathsEnabled`, a standard `os.walk` silently skips the long ones.

**Pass criterion.** Counts reconcile: manifest 40 = long-path-safe enumerator 40 (and `robocopy /L`
with a Unicode log, when available); names are byte-identical after the UTF-8 JSON round trip; four
spellings of the company name (`dell'Èrto`, `DELL’ÈRTO`, `Societa' ... Erto`, NFD-decomposed) resolve to
one canonical `SOCIETÀ AGRICOLA VALLE DELL’ÈRTO S.S.` with three aliases; a handoff written with single
backslashes (`C:\Users\...`) is repaired on read and the repair is logged. The naive count is printed
for comparison, never used.

PowerShell note (L8): `-replace` is case-insensitive, so `\U` in `C:\Users` can be read as an escape;
use `-creplace` and escape the inputs. The pipeline never shells out to PowerShell.

```
python scenarios/S08/make_input.py
python scenarios/S08/check.py
```

The long tree is **materialised at check time and never committed** (git on Windows would need
`core.longpaths`, and a checkout could fail on other machines).
