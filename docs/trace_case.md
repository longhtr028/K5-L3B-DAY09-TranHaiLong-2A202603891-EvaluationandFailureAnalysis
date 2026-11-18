# C-002 · the ticket overwrote the order record

The ledger contains one payment of 20,000 VND. The independent claim label expects no payment. In run `E-seeded_regression-20261118-3f8d`, claim C-002 at seed 11 ends as resolved and tells the customer that the refund was issued.

| Event | Seeded regression | Fixed control at the same seed |
|---|---|---|
| 1 · handoff | Delegates three read-only tools in the owner scope. | Same tool permissions. |
| 2 · investigator | Reads order O-202 with a two-day delay. | Same order, same delay. |
| 3 · first divergence | `model_override` sets `delay_days` to 5, the customer's ticket value. | `quote` records zero entitlement. |
| Final outcome | Event 4 quotes 20,000. Event 6 confirms that amount. The ledger matches the reply and the wrong entitlement. | Event 4 explains the denial. The ledger contains zero refunds. |

**Diagnosis.** FM-03 occurs at event 3. The approval was valid for this claim, so a zero-bypass count alone cannot establish that the payment was owed. The trace identifies the value replacement. It gives no evidence about a live model's reasoning or how often customers would encounter it.

**Regression test.** The test replays both shapes, checks the original DB fact, and asserts the step grader, ledger grader and Day 8 verdict. All three return false for the seeded trial and true for the control. The item carries the source trace reference in its provenance. [Regression test](../src/tests/test_lab9_regressions.py) · [Seeded report](../src/reports/eval_seeded_regression.json) · [Control report](../src/reports/eval_fixed.json)

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
python -m pytest -q -o addopts= -k c002_ticket_delay
```
