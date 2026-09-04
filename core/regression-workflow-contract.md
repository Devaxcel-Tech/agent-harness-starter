# Workflow 2 — regression, stage by stage

The same pipeline as Workflow 1 with the ticket and code stages removed: regression asks "does
everything that already shipped still work," not "did this one change do what it claimed," so it needs
no ticket and is safe to run on a schedule against whatever is currently on the default branch.

| # | Stage | Input | Job | Output |
|---|---|---|---|---|
| 1 | Harness / Automated Checks | current branch | Same as Workflow 1 stage 3 — run `harness.runCommand`. Regression's job is to catch drift, so this runs against the tip of the default branch, not a feature branch. | Evidence file + `PASS` / `FAIL` / `BLOCKED` |
| 2 | Playwright E2E | suite/tag name (`scope.id`, e.g. a Confluence page ID, a `@regression` tag, a named registry file) — no ticket ID required | Run the full suite selected by that scope, per `e2e.regressionCommand` in `qa.config.yaml`. | Case-level verdicts + evidence, rolled up per `e2e-engine-contract.md` §3's five-word vocabulary |
| 3 | QA Verification | stage 1 & 2 evidence | Independent reviewer reconciles evidence against the regression registry (no acceptance criteria to check against — the bar is "still behaves as previously verified"). | `PASS` / `FAIL` / `BLOCKED` + reviewer identity + notes |
| 4 | Result | all of the above | Roll up worst-of(1, 2, 3); write `result.json` (`workflow: "regression"`, `scope.id` = suite/tag, `scope.ticketUrl`/`scope.prUrl` = `null`); publish per `publisher.*` config if configured. | One committed result record per run, independently re-runnable |

## Why this is independently executable (requirement: no ticket needed per run)

`scope.id` for a regression run is a suite or tag name, never a ticket ID — `result.schema.json` allows
`scope.ticketUrl` to be `null` for exactly this reason. A regression run is triggered by a schedule, a
release gate, or a manual invocation; nothing in this workflow blocks on a tracker having an open issue
to attach to.

## Reusing the ticket workflow's building blocks

Both stages here are byte-for-byte the same commands as Workflow 1's stages 3–4 — same
`harness.runCommand`, same E2E engine, just a different selection (`e2e.regressionCommand` instead of a
ticket-ID filter) and no ticket to quote criteria from. `tools/run-qa-workflow.sh` implements both modes
from the same script for this reason: divergence between the two workflows should live in *what gets
selected*, never in *how a stage runs*.
