# Workflow 1 — ticket / feature testing, stage by stage

Despite the name, "Jira" here means **whatever tracker `qa.config.yaml` names** — the stage is generic;
only the adapter behind it is tracker-specific. Each row states the stage's input, its one job, and the
output the next stage consumes. A stage that cannot produce its output halts the workflow rather than
guessing at the next stage's input.

| # | Stage | Input | Job | Output |
|---|---|---|---|---|
| 1 | Ticket | ticket ID | Fetch the ticket via `tracker.*` config. Quote the acceptance criteria — never paraphrase them; a paraphrase is where a misreading enters and becomes invisible six months later. | Quoted acceptance criteria + ticket ID, held for stage 5 |
| 2 | Developer Code | quoted criteria | Implement, test-first, per criterion. This kit does not prescribe how — a project's own dev workflow (e.g. the harness's `task-loop`) governs this stage. | A PR referencing the ticket ID |
| 3 | Harness / Automated Checks | current branch | Run the project's structural/quality gate floor (`harness.runCommand` from `qa.config.yaml` — typically the Agent Development Harness's `tools/qa/run-qa.sh`). This is independent of what the code *claims* to do; it checks what the code *is*. | Evidence file + one of `PASS` / `FAIL` / `BLOCKED`, per the harness's own exit-code contract (`VERIFIED→PASS`, `VIOLATED→FAIL`, `CANNOT_RUN`/`INCOMPLETE→BLOCKED` — neither is ever silently a pass) |
| 4 | Playwright E2E | ticket ID | Run only the cases in scope for this ticket (ID match or `linkedTicket:` — see `e2e-engine-contract.md` §2). | Case-level verdicts + evidence, rolled up to one stage verdict (worst-of the case verdicts, `CANNOT_AUTOMATE`/`NOT_EXECUTED` cases counted separately and never silently dropped) |
| 5 | QA Verification | quoted criteria + stage 3 & 4 evidence | An **independent** reviewer — never the identity that authored the code or the test — reconciles the evidence against the quoted criteria and records a verdict with reasoning. | `PASS` / `FAIL` / `BLOCKED` + reviewer identity + notes |
| 6 | Result | all of the above | Roll up worst-of(3, 4, 5) into `finalResult`; write the `result.json` (schema: `core/result.schema.json`); post it back via `publisher.*` / `tracker.*` config if configured. | One committed result record, linked to ticket + PR |

## The independence rule, stated once so it does not drift

Stage 5 exists because a green suite an agent wrote to check its own code proves the code agrees with
itself, not with the requirement. **The reviewing identity at stage 5 must differ from the authoring
identity of the code and the test.** `tools/check_result_contract.py` can check this mechanically when
both identities are recorded (git author of the branch's commits vs. `stages.qaVerification.reviewer`);
where they cannot be compared automatically, this is an advisory rule enforced by review, exactly like
the rest of the harness's controls — advisory until branch protection makes it load-bearing.

## Rollup rule

```
FAIL > BLOCKED > PENDING > PASS
```

`finalResult` is the worst of the three stage verdicts under that ordering. `PENDING` is not a stage
verdict a workflow ever finishes on — it is what `stages.qaVerification.verdict` reads before stage 5
has run, and a record with `finalResult: PENDING` is exactly as incomplete as a record with no
`finalResult` at all. Treat it that way, not as a soft pass.
