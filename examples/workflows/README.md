# CI workflow templates

**Copy these into `.github/workflows/` in your own repository.** They are not active here.

They live under `examples/` for the same reason every other template in this kit does: this is a
starter kit, and its job is to hand you working files to copy, not to run them itself.

| File | What it does |
|---|---|
| `gates.yml` | Runs `tools/qa/run-qa.sh` (which discovers every gate) plus the gate fault suite, and uploads the evidence record as an artifact. |
| `secret-scan.yml` | Full-history and working-tree secret scanning, blocking, with output redacted. |

## Two details worth not losing when you copy them

**Every step after the first carries `if: ${{ !cancelled() }}`.** Most CI systems skip the rest of a
job as soon as one step fails, so without this a later check is reported *skipped* — and a reader
cannot tell a check that passed from one that never ran. Removing those guards is the single easiest
way to quietly break the signal.

**The fault suite runs even when a gate is failing.** That is deliberate: when a gate is red, *"is the
gate still sound?"* is exactly the question worth answering.
