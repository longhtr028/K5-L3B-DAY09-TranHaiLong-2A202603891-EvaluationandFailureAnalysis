# Judge calibration and disagreement audit

The positive class is a human-labeled failure. Each replay contains 100 labeled replies. Eligibility requires κ ≥ 0.60, failure precision ≥ 0.80 and failure recall ≥ 0.70.

| Criterion | TP / FP / FN / TN | κ | Precision | Recall | Observed → corrected failure prevalence | Decision |
|---|---|---:|---:|---:|---:|---|
| Tone | 24 / 4 / 6 / 66 | 0.757 | 0.857 | 0.800 | 28% → 30% | Eligible for pilot tone review. |
| Helpfulness | 9 / 0 / 21 / 70 | 0.375 | 1.000 | 0.300 | 9% → 30% | Exclude from release gating. It misses 21 of 30 human failures. |

The Rogan–Gladen correction uses sensitivity and specificity measured on these same labels. Recovering 30% on the calibration sample gives no independent evidence of performance on new replies. Financial accuracy and approvals use deterministic checks.

| Replay ID | Judge / human | Adjudication and proposed rubric change |
|---|---|---|
| H-008 | PASS / FAIL | Support the human label. Include “nha” together with familiar self-address as an example of overly casual complaints handling. |
| H-029 | PASS / FAIL | Support the human label. Read the closing sentence. Telling a customer to stop messaging is dismissive even after a polite opening. |
| H-042 | FAIL / PASS | Support the human label. A concise payment confirmation with a time estimate can be courteous without an apology. Add this positive example. |
| H-051 | FAIL / PASS | Support the human label. The service permits “refund” in a polite Vietnamese sentence. Add the accepted term to the rubric. |
| H-070 | PASS / FAIL | Support the human label. Laughing emojis trivialize a complaint. Score tone in the service context. |
| H-081 | FAIL / PASS | The replay annotation identifies a human ticket mix-up. Flag the pair for source-ticket re-adjudication before changing the reference label. Keep the published run reproducible. |
| HL-015 | PASS / FAIL | Support the human label. The reply states 55,000 VND against a 40,000 VND ledger. Require evidence for monetary claims and delegate this check to code. |
| HL-028 | PASS / FAIL | Support the human label. Repeated apologies surround an incorrect 50,000 VND confirmation. Score resolution accuracy before courtesy. The annotated ledger is 35,000 VND. |

Reproduce in `src/` with `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10` and repeat with `judge_helpful_public.csv`. The expected exit codes are 0 and 1, respectively. Before live use, freeze the revised rubric, blind a second human reviewer and calibrate on fresh tickets. [Tone replay](../src/data/eval/judge_tone_public.csv) · [Helpfulness replay](../src/data/eval/judge_helpful_public.csv)
