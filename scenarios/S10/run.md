# S10 - Host off overnight

*Company (synthetic): Fornace Aurelia S.r.l. - Lesson L9 "Heartbeats: order, time zone, two kinds of run".*

**Failure reproduced.** The last full run processed window 2026-10-19 (at 2026-10-20 01:05 UTC). The
host is off from 2026-10-20 22:00 UTC to 2026-10-21 06:00 UTC, so the nightly trigger of 03:05 CEST
(= 01:05 UTC, the one of the two local triggers that falls in the target UTC hour) never fires, and
window 2026-10-20 is not processed.

**Pass criterion.** The first run afterwards - a *light* trigger at 08:30 CEST - detects the missed
window, performs it as full work (judgement for 2026-10-20 written with `catch_up: true`), refreshes
the data, and says so: `CATCH-UP: host was off; recovered 1 missed window(s): 2026-10-20`. A later
light run the same day recovers nothing and writes no judgement; the next night processes only
2026-10-21. Deliveries per window come from the main corpus (`input/deliveries.json`).

```
python scenarios/S10/make_input.py
python scenarios/S10/check.py
```
