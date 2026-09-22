---
name: qa-ticket-flow
description: Workflow 1 — ticket / feature testing. Runs a ticket's changes through Harness, then Playwright E2E scoped to that ticket, then hands off for independent QA Verification, and writes one PASS/FAIL/BLOCKED result linked back to the ticket. Use after a PR exists for a ticket, when it's time to prove the change works rather than just that it compiles.
---

# qa-ticket-flow — Workflow 1

Runs stages 3-6 of `core/jira-workflow-contract.md`. Stages 1-2 (ground the requirement, implement) are
this project's own dev workflow — for a project that also runs the Agent Development Harness's
`task-loop`, that IS stages 1-2, and this skill picks up where it stops (PR open).

## Usage

```
qa-ticket-flow <TICKET-ID>
```

## Steps

### 0. Route the reasoning-heavy step, if routing is configured

If `qa.config.yaml` has `router.enabled: true`, run `tools/route-task.py` before starting step 3 (evidence
reconciliation — the one step here with real model cost; steps 1-2 are a tracker read and a scripted
command). Pick the closest `taskType`: `unit-property-mutation-analysis` or `e2e-authoring-debugging` for
a straightforward reconciliation, `bug-investigation` if step 2 came back FAIL/BLOCKED and the cause needs
digging into, `architecture-security-review` if the ticket touches anything in `router.riskPaths`/
`router.riskKeywords`. Prefer the recommended `AGENT=` for step 3 — this is advisory, not enforced (see
`core/model-router-contract.md` §1), but ignoring it defeats the reason it exists.

### 1. Confirm the PR exists and quote the criteria

Fetch `<TICKET-ID>` via `tracker.*` in `qa.config.yaml`. Quote its acceptance criteria — never
paraphrase. If there is no open PR referencing this ticket, **halt**: there is nothing to verify yet.

### 2. Run the automated stages

```bash
bash tools/qa-workflow/run-qa-workflow.sh ticket <TICKET-ID>
```

This runs `harness.runCommand` (the gate floor) and `e2e.ticketCommand` scoped to `<TICKET-ID>`, and
writes a `result.json` under `evidence.root/ticket/<TICKET-ID>/` with `stages.qaVerification` PENDING.
**Read the printed `finalResult`.** If it is already `FAIL` or `BLOCKED` from the harness or E2E stage
alone, stop here and report that — do not proceed to verification on evidence that already failed.

### 3. Hand off for QA Verification — do not perform it yourself

**If you are the same agent identity that authored the code or the test in this PR, stop here and say
so.** Verification by the author is not verification; it is the code confirming itself. Either:

- a human reviewer reads the quoted criteria against the evidence at `evidencePath` in the result file
  and the harness's own evidence, then runs step 4 themselves; or
- a **different** agent session/identity performs steps 3-4.

Reconcile every clause of the quoted acceptance criteria against the evidence. A clause with no
corresponding case or check is a gap in coverage, not something to wave through.

### 4. Record the verdict

```bash
bash tools/qa-workflow/run-qa-workflow.sh verify \
  <evidence.root>/ticket/<TICKET-ID>/result.json \
  <PASS|FAIL|BLOCKED> \
  "<reviewer identity>" \
  "<why — cite the clause that failed, or confirm every clause held>"
```

This computes and prints the final `finalResult`.

### 5. Report and, if configured, publish

- Post the result summary as a comment on `<TICKET-ID>` via `tracker.*`.
- If `publisher.type` is not `none`, publish the evidence per `publisher.*`.
- Commit `result.json` — it is the durable record; a terminal's output is not.

## What this skill does not do

It does not merge the PR, does not decide what "done" means beyond the quoted criteria, and does not
invent E2E coverage for a criterion the suite has no case for — that gap gets reported, not silently
filled with a plausible-looking pass.
