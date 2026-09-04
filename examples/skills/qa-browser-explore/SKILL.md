---
name: qa-browser-explore
description: Agent-driven browser/UI checking via Claude in Chrome — the claude-in-chrome engine referenced in core/e2e-engine-contract.md §8. Drives a real browser session against a project's scenario data to produce case-level PASS/FAIL/BLOCKED verdicts and evidence, in the same shape a scripted (Playwright) engine would. Run this before qa-ticket-flow / qa-regression-flow's "run the automated stages" step when e2e.engines includes claude-in-chrome — those skills only aggregate what this one already wrote, they never drive the browser themselves.
---

# qa-browser-explore — the claude-in-chrome engine

Not a stage of its own in `core/jira-workflow-contract.md` or `core/regression-workflow-contract.md` —
it fills the same slot Playwright fills (the E2E stage), for the subset of coverage that benefits from
an agent driving a real browser rather than a deterministic script: exploratory checks, visual/console
verification, and flows that are easier to describe as intent ("open the record just fixed and confirm
no unhandled rejection fires") than to hand-script.

**This is a checklist for the agent session doing the driving, not a program `run-qa-workflow.sh`
invokes.** There is no command for it to invoke — see `core/e2e-engine-contract.md` §8 for why.

## Usage

```
qa-browser-explore <workflow> <scope-id> [ticket-id]
```

- `<workflow>`: `ticket` or `regression` — must match the run this session's evidence belongs to.
- `<scope-id>`: ticket ID for `ticket`, suite/tag name for `regression` — same value
  `run-qa-workflow.sh` was, or will be, invoked with.
- `[ticket-id]`: for `workflow=regression` scenarios that are also `linkedTicket`-scoped, otherwise
  omitted.

If `qa.config.yaml` has `router.enabled: true`, this session's `taskType` is `e2e-authoring-debugging` —
run `tools/route-task.py` before step 3 and prefer its recommended `AGENT=`. A scenario whose route or
data touches `router.riskPaths`/`router.riskKeywords` always escalates to `deep` regardless of how many
scenarios are in scope. See `core/model-router-contract.md`.

## Steps

### 1. Load scope and scenarios — never invent them

Read `e2e.claudeInChrome.scenarios` from `qa.config.yaml`. Select only the scenarios in scope:

- `ticket`: scenarios whose ID matches `<scope-id>`, or whose data declares
  `linkedTicket: <scope-id>` — same selection rule as `core/e2e-engine-contract.md` §2.
- `regression`: every scenario tagged for this `<scope-id>`'s suite/tag.

If the scenario file names a case with no data (a URL, an expected outcome) do not fill the gap from
assumption — that is a coverage gap to report at step 4, not something this skill improvises.

### 2. Stand up a session — reuse the project's own auth, never re-enter credentials here

Read the base URL from the environment variable named in `e2e.claudeInChrome.baseUrlEnv` — never write
or hardcode a literal URL in this skill or in scenario data checked into a public-facing file.

Session/auth setup is project-owned (`core/e2e-engine-contract.md` §7), identical to whatever the
project's Playwright suite already uses — a saved storage state, an SSO session the human running this
skill is already logged into, or a documented bootstrap step named in `qa.config.yaml`. **Never type a
password, token, or other credential into a field during this session.** If a scenario requires a fresh
login and no session-reuse mechanism is configured, that scenario is `BLOCKED` ("no credential path
configured for this engine") — do not enter credentials manually to work around it.

### 3. Drive each scenario, recording as you go — not only at the end

For each in-scope case:

1. Navigate/interact per the scenario's data (routes, actions, expected outcome) — never per selectors
   or code baked into this skill.
2. Observe the real signal the scenario asks about — e.g. console errors, unhandled promise rejections,
   network response codes, visible UI state — using whatever Claude-in-Chrome tools read that signal
   (console/network reading, page reading, screenshots). Do not infer a result from what "should" have
   happened; read what did.
3. Capture evidence into the layout `core/e2e-engine-contract.md` §4 defines:
   `<evidence.root>/<workflow>/<scope-id>/<module>/<CASE-ID>-NN-<label>.png`
4. Write the verdict **immediately**, not batched at the end of the session, to:
   `<evidence.root>/<workflow>/<scope-id>/results/<CASE-ID>.json`
   shaped per `core/case-result.schema.json`:
   ```json
   {
     "id": "<CASE-ID>",
     "engine": "claude-in-chrome",
     "verdict": "PASS|FAIL|BLOCKED|CANNOT_AUTOMATE|NOT_EXECUTED",
     "evidence": ["<paths from this case's screenshots>"],
     "note": "what was actually observed — cite it, don't summarize as a conclusion only",
     "recordedAt": "<UTC ISO-8601 timestamp>"
   }
   ```
   Writing as you go means a session that stops partway (browser crash, tool failure, time budget) still
   leaves honest partial evidence — a case with no file is `BLOCKED` by
   `tools/aggregate-e2e-results.py`'s own definition, never silently missing.

### 4. Never write a credential into evidence or logs

Before finishing: confirm no screenshot shows a credential, token, or API key visibly entered or
displayed (a login form mid-fill, an env var dumped to console, a URL with a token in the query string).
If one exists, delete that evidence file and re-capture, or mark the case `BLOCKED` with a note
explaining why no clean evidence could be captured — never redact-and-keep, since a partially redacted
screenshot is easy to get wrong. `evidence.root` should already be git-ignored (see the project's own
`qa.config.yaml`/`.gitignore`) for exactly this class of risk — this rule holds regardless.

### 5. Hand off — this skill does not aggregate or verify

Once every in-scope case has a `results/<CASE-ID>.json`, stop. `tools/run-qa-workflow.sh` (via
`tools/aggregate-e2e-results.py`) reads what was written here the next time it runs for this
`<workflow>`/`<scope-id>`; `qa-ticket-flow` / `qa-regression-flow` carry the rollup into QA Verification
exactly as they would for a Playwright-only run. This skill has no opinion on `finalResult`.

## What this skill does not do

It does not replace Playwright for deterministic, repeatable regression checks — those stay scripted.
It does not perform QA Verification (still an independent stage, still never the identity that authored
the code or ran this session). It does not decide what counts as in scope beyond the scenario data it
was given.
