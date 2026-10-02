# S06 - Recital dates vs actionable deadlines

*Company (synthetic): Cantine Belvedere S.p.A. (the debtor) - Lesson L6 "Not every date is a deadline".*

**Failure reproduced.** Four notices (diffida, instalment plan, writ of summons, social-security debit
notice) contain 20 date items: 17 written dates and 3 relative terms ("entro quindici/quaranta/sessanta
giorni"). Only 6 are actionable or computed. The traps: a recital "il termine originariamente fissato
al 24/10/2026" (3 days after as_of) and a condition "in caso di mancato pagamento entro il 28/10/2026"
(7 days after as_of) - a reader that treats every future date as a deadline paints both MAXIMUM.

**Pass criterion.** Every date gets the expected nature (`historical` 12, `conditional` 2,
`actionable` 3, `computed` 3); urgency colours are driven by those 6 only:
N1 MAXIMUM (31/10), N2 MEDIUM (30/11 - not the conditional 28/10), N3 LOW (12/03/2027),
N4 HIGH (10/11). The check also prints what the naive reading would have shown.

```
python scenarios/S06/make_input.py
python scenarios/S06/check.py
```
