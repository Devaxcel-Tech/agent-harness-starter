# Adoption guide

An install sequence for `docs/pattern-handbook.md`. Each stage is checked before moving to the next —
adopting this kit with a broken prerequisite produces a result record nobody should trust.

## Prerequisite: the Agent Development Harness is already installed

This kit imports `harness.py`'s exit-code vocabulary rather than redefining it, so it expects
`<project>/tools/gates/harness.py` to exist already. If it does not:

```bash
# from agent-harness-starter/
mkdir -p <project>/tools <project>/docs <project>/.github/workflows
cp -r tools/gates tools/qa <project>/tools/
cp -r .githooks <project>/
cp .gitleaks.toml <project>/
cp docs/DECISIONS.md <project>/docs/
python3 <project>/tools/gates/check_gates_test.py   # prove the gates can fail, first
```

## 1. Copy this kit's tools in

```bash
# from agent-harness-starter/
mkdir -p <project>/tools/qa-workflow
cp tools/qa-workflow/*.sh tools/qa-workflow/*.py <project>/tools/qa-workflow/
cp qa.config.schema.json <project>/tools/qa-workflow/
```

## 2. Write the project's qa.config.yaml

```bash
cp examples/qa.config.example.yaml <project>/qa.config.yaml
```

Edit every value. The fields that need real thought, not just a rename:

| Field | Get this from |
|---|---|
| `harness.runCommand` | Usually `tools/qa/run-qa.sh`, unchanged from the harness install above |
| `e2e.path` | Wherever the project's E2E suite lives |
| `e2e.regressionCommand` / `e2e.ticketCommand` | Existing test-runner scripts — this kit does not add new ones. If the suite has no way to select cases by ticket ID yet, that is the one real gap to close: see `core/e2e-engine-contract.md` §2 for the ID convention it needs |
| `evidence.root` | A path that is git-ignored if it will hold real user data (screenshots, recordings) |
| `tracker.*` / `publisher.*` | Whichever tool the project's own agent config already uses to talk to its tracker/wiki — this kit names the adapter, the project's own tooling implements it |

Validate it:

```bash
python3 <project>/tools/qa-workflow/check_qa_config.py
```

`CANNOT_RUN` here means a required field is missing — fix `qa.config.yaml`, not the checker.

## 3. Confirm the E2E suite satisfies the engine contract

Read `core/e2e-engine-contract.md`. The one requirement most existing suites need to add, if adopting
this kit for the first time, is the case-ID-to-ticket-ID selection path (§2) — everything else
(config/data separation, the five-word status vocabulary, the evidence layout) most mature Playwright
setups already have in some form.

**Optional: add Claude in Chrome alongside Playwright.** Leave `e2e.engines` unset (defaults to
`playwright` alone) unless a project wants agent-driven exploratory/UI coverage in addition to
Playwright's scripted regression coverage. Adding it means: set `e2e.engines: playwright,claude-in-chrome`,
add `e2e.claudeInChrome.scenarios` and `e2e.claudeInChrome.baseUrlEnv`, write scenario data (same
config/data separation as any other engine), and run `examples/skills/qa-browser-explore/SKILL.md`'s
session before `run-qa-workflow.sh` for scopes that include it — see `core/e2e-engine-contract.md` §8.
This is additive; it never changes how the Playwright-only path behaves.

## 4. Run each workflow once, by hand, before trusting it

```bash
bash <project>/tools/qa-workflow/run-qa-workflow.sh regression smoke
# read the printed finalResult — it should be PENDING, with harness/e2e verdicts set honestly
bash <project>/tools/qa-workflow/run-qa-workflow.sh verify \
  <evidence.root>/regression/smoke/result.json PASS "your-name" "manual first run"
# finalResult should now be PASS (or whatever the honest rollup is)
```

If `finalResult` comes back green on a run you know should have failed something, that is the adoption
failing, not the kit — go find which stage silently passed and fix its command in `qa.config.yaml`.

## 5. Wire the two skills in

Copy `examples/skills/qa-ticket-flow/` and `examples/skills/qa-regression-flow/` into wherever the
project's agent tooling looks for skills. Edit nothing in them — if a project needs different behavior,
that need almost always belongs in `qa.config.yaml`, not a fork of the skill.

## 6. Optional: CI

Add a step that runs `check_qa_config.py` and, once results exist, `check_result_contract.py` — same
pattern as `agent-harness-starter/examples/workflows/gates.yml`. Neither blocks anything without branch
protection on the default branch, exactly like the rest of the harness.

## 7. Optional: add model/task routing

Leave `router.enabled` unset (or `false`) unless a project wants a recommendation for which model tier
should handle the agentic reasoning around these stages — it changes nothing about how the workflows run
either way. Adding it means: set `router.enabled: true`, fill in `router.riskPaths`/`router.riskKeywords`
with whatever this project actually considers high-risk (its own auth/PHI/payment paths and keywords —
this kit has no opinion on that list), map each of `router.tiers.fast.agent` /
`router.tiers.standard.agent` / `router.tiers.deep.agent` to a real agent name the project's own tooling
already knows how to run (`examples/agents/` has three to copy as a starting point), and run
`tools/route-task.py <task-type> <files...>` before the reasoning-heavy step of `qa-ticket-flow`,
`qa-regression-flow`, or `qa-browser-explore` — each names exactly where. See
`core/model-router-contract.md`. This is advisory only and purely additive; nothing about `run-qa-workflow.sh`
or the result contract changes whether or not routing is enabled.

## What "adopted" looks like

- `qa.config.yaml` at the project root, passing `check_qa_config.py`
- `tools/qa-workflow/` present, copied not reimplemented
- At least one committed `result.json` under `evidence.root`, with a real (non-PENDING) `finalResult`
- Both skills reachable by name

## When something about a project genuinely does not fit

Record it in `docs/DECISIONS.md` (this kit's own register, not the adopting project's) rather than
special-casing that project in `core/` or `tools/`. If the answer turns out to be "the schema needs a new
field," that is a schema change with its own reasoning, not a one-off exception.
