# S03 - Queue changes between two status queries

*Company (synthetic): Tessiture Monteverde S.r.l. - Lesson L3 "Remembered state is stale state".*

**Failure reproduced.** At 08:30 three notices await a reply. At 09:02 the agent asks "what is pending?"
(answer: 3). At 09:15 another hand answers all three (task_close events appended to the ledger by a
different writer). At 09:40 the question is asked again.

**Pass criterion.** The second answer is rebuilt from the ledger in the same call: 0 pending, with a
later `as_of` (09:40 > 09:02) and a different ledger digest. The answer remembered from 09:02 (3) is
never reused.

```
python scenarios/S03/check.py
```
