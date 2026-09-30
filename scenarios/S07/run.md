# S07 - One rule changed

*Company (synthetic): Tessiture Monteverde S.r.l. (the debtor) - Lesson L7 "Rules live in an ordered file; code only extracts".*

**Setup.** 12 notices (4 cartelle, 2 intimazioni, 1 instalment plan, 2 assessments - one State, one
local IMU -, 1 diffida, 1 registry communication, 1 reminder) are classified twice from the same
upstream state: with the committed rules, and with `rules/area.json` patched on **one** rule -
`R-014` (cartella_pagamento) now maps to `tax` instead of `collection` (the Appendix A example).
The fix goes into the rule, never into the output.

**Pass criterion.** Exactly the four cartelle change, field `area`, `collection -> tax`, attributed to
`R-014` before and after; the other 8 records (including the intimazioni and the plan, which share the
`collection` area through another rule) are unchanged. The diff is written to
`build/scenarios/S07/classification_diff.json`.

```
python scenarios/S07/make_input.py
python scenarios/S07/check.py
```
