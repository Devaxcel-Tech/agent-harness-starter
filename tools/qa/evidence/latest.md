# QA evidence

Generated 2026-08-06T14:24:44Z · commit `c258191`

| Control | Verdict | Detail |
|---|---|---|
| `check_decisions.py` | PASS | decision register: VERIFIED |
| `check_loop_obligations.py` | PASS | loop obligations: VERIFIED |
| `check_mutation_applicability.py` | PASS | mutation applicability: VERIFIED |
| `check_vendored_drift.py` | PASS | vendored drift: VERIFIED |
| gate fault injection | PASS | all 47 cases behaved as specified — every gate fires on a real violation, stays quiet when it should, and reports could-not-run ra |

## How to read this

- **COULD NOT RUN** and **INCOMPLETE** are not passes. They mean no verdict was reached.
- A control with nothing to measure yet is PENDING with its trigger, never a pass.
- This file is the record. Commit it — evidence must outlive the terminal.
