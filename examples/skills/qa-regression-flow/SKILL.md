---
name: qa-regression-flow
description: Workflow 2 — regression. Runs Harness then the full/tagged Playwright regression suite against the current default branch, independent of any ticket, then hands off for independent QA Verification and writes one PASS/FAIL/BLOCKED result. Use on a schedule, before a release, or any time you want proof the codebase still works without a specific ticket driving it.
---

# qa-regression-flow — Workflow 2

Runs `core/regression-workflow-contract.md` end to end. No ticket ID is required — the scope is a suite
or tag name.

## Usage

```
qa-regression-flow [scope-id]     # e.g. a suite name; defaults to "full"
```

## Steps

### 0. Route the reasoning-heavy step, if routing is configured

Same as `qa-ticket-flow` step 0: if `router.enabled: true`, run `tools/route-task.py` before starting
step 3 (reconciling per-case verdicts against the registry — steps 1-2 are a branch check and a scripted
command, no routing needed). `bug-investigation` if any case came back FAIL and its cause needs digging
into; `architecture-security-review` if the failing area is named in `router.riskPaths`/
`router.riskKeywords`; otherwise `unit-property-mutation-analysis` or `e2e-authoring-debugging` fits most
regression reconciliation. See `core/model-router-contract.md`.

### 1. Confirm you're on the branch meant to be regression-tested

Regression proves the default branch — or whatever branch you name — still behaves. Confirm the current
checkout is that branch before running; a regression result attributed to the wrong commit is worse
than no result, because it will be trusted.

### 2. Run the automated stages

```bash
bash tools/qa-workflow/run-qa-workflow.sh regression <scope-id>
```

This runs `harness.runCommand` and `e2e.regressionCommand`, and writes `result.json` under
`evidence.root/regression/<scope-id>/` with `stages.qaVerification` PENDING.

### 3. Hand off for QA Verification

Same independence rule as `qa-ticket-flow`: the reviewer must not be the identity that produced the
change under test — for regression this usually means whoever last touched the area a failing case
covers should not be the one clearing it. Reconcile the E2E stage's per-case verdicts (PASS / FAIL /
BLOCKED / CANNOT_AUTOMATE / NOT_EXECUTED) against what the registry expects; a case reported
CANNOT_AUTOMATE or NOT_EXECUTED is not proof of anything and must not be counted as if it were.

### 4. Record the verdict

```bash
bash tools/qa-workflow/run-qa-workflow.sh verify \
  <evidence.root>/regression/<scope-id>/result.json \
  <PASS|FAIL|BLOCKED> \
  "<reviewer identity>" \
  "<notes>"
```

### 5. Report

Publish per `publisher.*` if configured, and commit `result.json`. Unlike Workflow 1 there is no ticket
to comment on by default — if a FAIL traces to a specific defect, that is when a bug ticket gets filed,
linking this result record as the evidence.

## Running this without a human attached

A scheduled/unattended regression run can complete stages 1-2 unattended, but **must stop at PENDING**
rather than self-certify verification. Report the PENDING result (harness + E2E verdicts, not yet a
`finalResult`) to whoever is meant to review it, rather than inventing a verdict to make the run look
complete.
