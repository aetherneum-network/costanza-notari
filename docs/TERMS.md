# Procedural terms - the rule implemented

> **Not legal advice.** Synthetic proof pack. Every parameter below is an assumption marked
> **[TO CONFIRM with counsel]**. Parameters live in `rules/terms.json` and `rules/holidays.json`;
> the arithmetic lives in `pipeline/terms.py` and is cross-checked against an independent
> day-by-day walker (`corpus/reference_terms.py`) on every day from June 2026 to June 2027.

## Algorithm (forward terms in days)

1. **Start.** S = the day the notification is perfected for the recipient.
   * S is taken from the PEC provider's timestamp in `daticert.xml` of the message found in the
     recipient's mailbox. **[TO CONFIRM with counsel]** the legally relevant instant is the delivery
     receipt (RdAC), which the *sender* holds; the recipient-side timestamp is a proxy.
   * *PEC after 21:00 rule* (only where `pec_after_21_rule: true`): a PEC delivered at or after 21:00
     Europe/Rome is perfected for the recipient on the next day (art. 147 c.p.c. as amended by
     D.Lgs. 149/2022). **[TO CONFIRM with counsel]** scope: applied to civil-procedure notifications
     (precetto, decreto ingiuntivo, pignoramento, insolvency), not to tax/collection/social-security notices.
   * Internal forwards (`TARGET`) of acts received by post carry **no** notification date: computed
     terms are `RECUPERARE`. If the transport signature fails, the timestamp is untrusted: `RECUPERARE`.
2. **Dies a quo non computatur** (art. 155 c.1 c.p.c.): day 1 is S + 1.
3. **Feriale suspension** (only where `feriale_suspension: true`): days from 1 to 31 August do not count
   (L. 742/1969 art. 1, as amended by D.L. 132/2014). A term that would begin inside the period begins
   on 1 September, which is day 1.
4. **Expiry**: the day on which the count reaches N.
5. **Roll-forward**: Sunday or national public holiday -> next day (art. 155 c.4 c.p.c.; art. 2963 c.c.
   for substantive terms); Saturday -> Monday only where `saturday_rollover: true` (art. 155 c.5 c.p.c.,
   procedural acts). Repeated until a working day.

Holidays: 1 Jan, 6 Jan, Easter Monday (computed, Meeus/Jones/Butcher), 25 Apr, 1 May, 2 Jun, 15 Aug,
**4 Oct from 2026** **[TO CONFIRM with counsel: statute reference and effective year]**, 1 Nov, 8 Dec,
25 Dec, 26 Dec. Local patron-saint days are **not** modelled **[TO CONFIRM with counsel]**.

## Term table (as implemented)

| id | act | days | Aug. suspension | Sat. roll-over | 21:00 rule | basis | assumption |
|---|---|---|---|---|---|---|---|
| T-001 | atto di precetto | 10 | no | yes | yes | art. 480 c.p.c. | [TO CONFIRM] no suspension; Saturday roll-over |
| T-002 | decreto ingiuntivo (opposizione) | 40 | yes | yes | yes | art. 641 c.p.c. | [TO CONFIRM] non-labour matter |
| T-003 | pignoramento mobiliare (opp. atti esecutivi) | 20 | no | yes | yes | art. 617 c.2 c.p.c. | [TO CONFIRM] start event; enforcement excluded from suspension |
| T-004 | sentenza di liquidazione giudiziale (reclamo) | 30 | no | yes | yes | art. 51 CCII; art. 9 CCII | [TO CONFIRM] |
| T-005 | avviso di accertamento (ricorso) | 60 | yes | yes | no | art. 21 D.Lgs. 546/1992 | [TO CONFIRM] adesione not modelled |
| T-006 | cartella di pagamento (pagamento) | 60 | no | no | no | art. 25 DPR 602/1973 | [TO CONFIRM] treated as substantive |
| T-007 | intimazione di pagamento | 5 | no | no | no | art. 50 c.2 DPR 602/1973 | [TO CONFIRM] |
| T-008 | avviso di addebito (opposizione) | 40 | no | yes | no | art. 24 c.6 D.Lgs. 46/1999 | [TO CONFIRM] labour matter: no suspension |
| T-009 | diffida / messa in mora | as stated | no | no | no | contractual | [TO CONFIRM] receipt = PEC delivery |
| T-010 | piano di rateizzazione | dates stated | no | no | no | art. 19 DPR 602/1973 | [TO CONFIRM] lapse clause = conditional |

A relative term stated in the text ("entro quaranta giorni dalla notifica") wins; the statutory default
of the table is used only when the text states no term (or there is no text at all). A term clause that is
there but cannot be read with certainty - months or weeks, *giorni lavorativi / liberi / utili*, a term
running from the notification of another act, a number the two readers of `pipeline/termclauses.py` do not
agree on - is never replaced by the default: the deadline is `RECUPERARE` (`rules/term_clauses.json`; how
such terms are counted is **[TO CONFIRM with counsel]** and not modelled). Hearing dates and stated due dates are
`actionable`; their date is taken from the text as is.

## Hand-worked examples (asserted by `tests/test_terms.py`)

| # | act | PEC delivered (Europe/Rome) | working | deadline |
|---|---|---|---|---|
| E1 | precetto (10) | Mon 2026-10-05 10:15 | day 1 = 06/10, day 10 = Thu 15/10 | **2026-10-15** |
| E2 | decreto ingiuntivo (40, susp.) | Mon 2026-07-20 11:00 | 21-31/07 = 11 days; Sep 1 = day 12; day 40 = 29/09 (Tue) | **2026-09-29** |
| E3 | decreto ingiuntivo (40, susp.) | Mon 2026-08-10 09:00 | starts 01/09 = day 1; day 40 = Sat 10/10 -> Monday | **2026-10-12** |
| E4 | avviso di accertamento (60, susp.) | Tue 2026-06-30 16:00 | July = 31 days; day 60 = 29/09 | **2026-09-29** |
| E5 | cartella (60, no Sat. roll-over) | Tue 2026-10-06 10:00 | 06/10 + 60 = Sat 05/12, not rolled | **2026-12-05** |
| E6 | same arithmetic, procedural | Tue 2026-10-06 10:00 | Sat 05/12 -> Mon 07/12 | 2026-12-07 |
| E7 | intimazione (5) | Thu 2026-12-03 10:00 | +5 = Tue 08/12 (Immacolata) -> 09/12 | **2026-12-09** |
| E8 | precetto (10), 21:00 rule | Fri 2026-10-09 21:30 | perfected 10/10; +10 = Tue 20/10 | **2026-10-20** |
| E9 | cartella (60) | Thu 2027-08-05 10:00 | +60 = Mon 04/10/2027 (4 Oct holiday) -> 05/10 | **2027-10-05** [TO CONFIRM] |

Known simplifications: backward terms (e.g. appearance 70 days *before* a hearing) are not computed;
a term expiring on 31 July that rolls into August is not re-examined against the suspension
**[TO CONFIRM with counsel]**.
