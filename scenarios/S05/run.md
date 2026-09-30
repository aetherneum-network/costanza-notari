# S05 - Lawyer writes via PEC gateway on behalf of a creditor

*Company (synthetic): Officine Lagorai S.r.l. (the debtor) - Lesson L5 "Authorship is not the file name".*

**Failure reproduced.** E1: the gateway *Servizi Notifiche Digitali Esempio S.p.A.* **transmits** a
precetto that Avv. Ilaria Moscardini **authored** (and signed, CAdES `.p7m`) on behalf of the
creditor **CARPENTERIE ROVERE S.R.L.** (the party). The act also quotes the debtor's own PEC. E2: the
same lawyer sends a diffida from her own PEC for AUTOTRASPORTI GHIAIOLA S.R.L. (transmitter = author,
party distinct; no creditor PEC declared -> channel `RECUPERARE`, not a guess). Six handoff/receipt
files carry names that point at the wrong author.

**Pass criterion.** E1: transmitter, author and party are three different entities, the channel is
the creditor's PEC, the debtor never appears in any attribution; E2 as expected; authorship of the six
files resolved from `from`/`by` = 6/6 (100 %).

```
python scenarios/S05/make_input.py
python scenarios/S05/check.py
```
