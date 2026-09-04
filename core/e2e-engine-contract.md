# E2E engine contract

What a project's E2E suite (Playwright or otherwise) must expose for either workflow to drive it. This
is an interface, not an implementation — nothing here names a project. A project satisfying this
contract plugs into both workflows without either workflow's tooling changing.

## 1. Config/data vs. engine separation

The suite must separate **what to check** from **how to check it**:

- Environment URLs, roles/credentials, selectors, and per-feature check lists live in data files a
  non-engineer can edit (YAML/JSON) — never inline in test code.
- Test files are generic engines driven by that data — adding a new checked feature means adding a data
  row, not editing a `.spec.ts`.

This is the contract, not a specific shape — a project may organize its data files however fits its
domain. What must hold is that neither workflow's orchestrator ever needs to edit a `.spec.ts` to add
coverage.

## 2. Case ID convention — this is how traceability works

Every checked case has a stable ID, and the test name **starts with it**:

```
<REGISTRY>-<AREA>-<NN>   e.g. PEW-DOC-02, PROJ-1234, SMOKE-LOGIN-01
```

Workflow 1 (ticket) filters the suite to cases whose ID matches the ticket ID, or whose data file
declares `linkedTicket: PROJ-1234`. Workflow 2 (regression) runs by suite/tag, independent of any ticket.
An engine that cannot select a subset by ID or tag cannot satisfy either workflow's "run only what's in
scope" requirement.

## 3. Status vocabulary — exactly these five words, nothing else

| Status | When |
|---|---|
| `PASS` | Every clause of the expected result was verified. |
| `FAIL` | A clause did not hold. |
| `BLOCKED` | Cannot proceed for an external reason: environment, config, permissions, missing test data, a dependency being down. |
| `CANNOT_AUTOMATE` | Not mechanisable at all in this engine (device camera, native push, a real elapsed multi-day window). Run manually and record the same way. |
| `NOT_EXECUTED` | Intentionally skipped, or a verdict withdrawn pending re-execution. |

**A case that finishes without recording one of these five is `FAIL`.** An aborted run must never be
mistaken for a pass — that is the one rule every project's recorder must enforce mechanically, not by
convention.

## 4. Evidence layout

```
<evidence-root>/<workflow>/<scope>/<module>/<CASE-ID>-NN-<label>.png   screenshots
<evidence-root>/<workflow>/<scope>/<module>/<CASE-ID>.webm             recording, if captured
<evidence-root>/<workflow>/<scope>/results/<CASE-ID>.json              verdict + evidence paths
<evidence-root>/<workflow>/<scope>/INDEX.md                            browsable index
```

`<evidence-root>` and `<scope>` are project config (`qa.config.yaml` → `evidence.root`); `<workflow>` is
`ticket` or `regression`. A screenshot or recording not written through this layout does not exist for
traceability purposes, whatever the test wrote to disk otherwise.

## 5. What the engine does NOT need to know

Nothing about Jira, Confluence, or any tracker/publisher. The E2E stage's only job is to produce
case-level verdicts and evidence in the shape above; linking that back to a ticket and publishing a
report are the orchestrator's job, driven by `qa.config.yaml`, not the suite's.

## 6. Zero tests selected must not look like a pass

Some runners exit `0` even when their filter matched nothing to run — observed directly in this kit's
own validation against a real Playwright suite whose fallback project (no role credentials configured)
matches zero test files and still exits `0`. `run-qa-workflow.sh` scans command output for a short list
of recognizable "zero tests" phrasings and overrides a PASS to BLOCKED when it sees one — the same
no-dependency output-scanning idiom the Agent Development Harness's own `run-qa.sh` uses to catch a
crashed gate. **This is a heuristic, not a guarantee**: it cannot recognize every runner's phrasing. A
project whose runner's zero-match message is not in that list should make its `e2e.*Command` wrapper
exit non-zero on zero-match itself, rather than relying on the heuristic to catch it.

## 7. Auth and environment setup are project-owned

However a project authenticates test sessions (Cognito, a session cookie, a mocked backend) is entirely
that project's concern and never belongs in this kit. The only requirement is that `qa.config.yaml`
names one command that stands up a runnable session for the suite, so the orchestrator does not need to
know how.

## 8. Scripted engines vs. agent-driven engines

Everything above assumes an engine that can be invoked as a shell command and trusted to self-report an
exit code — true of Playwright and most CLI test runners. It is not true of an agent-driven engine like
Claude in Chrome: there is no process to invoke and wait on, because the "engine" is an LLM session
interactively controlling a real browser through MCP tools. That is a different *kind* of engine, not a
different project, so it gets a different invocation path rather than a project-specific exception:

- **Scripted engine** (`e2e.ticketCommand` / `e2e.regressionCommand` configured): run exactly as
  described in §§1-7. `tools/run-qa-workflow.sh` invokes it and reads the exit code.
- **Agent-driven engine** (no command — declared only in `e2e.engines`, e.g. `claude-in-chrome`):
  `tools/run-qa-workflow.sh` never invokes it. It cannot: there is nothing to shell out to. Instead, a
  separate skill session (see `examples/skills/qa-browser-explore/SKILL.md`) drives the browser against
  scenario data (config/data-separated per §1, same as any other engine) and writes one
  `results/<CASE-ID>.json` per case it attempts, per `core/case-result.schema.json`, using the §4
  evidence layout. `tools/aggregate-e2e-results.py` then reads whatever that session left behind and
  rolls it up — worst-of the case verdicts — into that engine's contribution to the stage verdict. If an
  agent-driven engine is declared in `e2e.engines` but no case-result files exist yet for this scope, its
  contribution is `BLOCKED` ("no session recorded"), never a silent pass and never silently dropped from
  the rollup.

Both kinds converge on the same evidence layout and the same five-word vocabulary; the only difference is
*how* a verdict is produced, never *what shape* it ends up in. A project may declare `playwright` alone
(today's default and behavior, unchanged), `claude-in-chrome` alone, or both — `e2e.engines` in
`qa.config.yaml` is the one place that choice lives.
