# Model router contract

What `tools/route-task.py` decides, what it does not, and why. Like `core/e2e-engine-contract.md`, this
is an interface, not an implementation — nothing here names a project, an Anthropic model ID, or a price.

## 1. What this is

A **recommendation**, not a switch. `tools/route-task.py` reads a task's shape (type, files touched, an
optional free-text note) plus `qa.config.yaml`'s `router.*` block, and prints which of three abstract
tiers — `fast` / `standard` / `deep` — that task belongs in, and which configured agent name is mapped to
that tier. Nothing in this kit calls a model API, switches a running session's model, or enforces the
recommendation. `tools/run-qa-workflow.sh` never invokes it — the harness and E2E stages it runs are
scripts with no model cost to route in the first place (see §7).

Tiers are named abstractly, never as a literal model ID, for the same reason `e2e.engines` is indirected
through config rather than hardcoding a browser: a model's name changes over a product's lifetime, and
`core/` must not need editing when it does. Which real model backs `fast`/`standard`/`deep` is a project
decision, expressed by which agent name `qa.config.yaml` maps each tier to.

## 2. Inputs

| Input | Required | Source |
|---|---|---|
| `taskType` | yes | one of §3's fixed task types — the caller picks the closest match, never invents a new one |
| `files` | no | paths touched or about to be touched, repo-relative |
| `note` | no | free text describing the task, for keyword risk-matching when file paths alone don't say enough (e.g. a ticket about auth before any file is touched yet) |

## 3. Task types and their baseline tier

Fixed, not project-configurable — these describe universal shapes of QA/engineering work, not anything
project-specific. A project needing a task type this table does not cover is a contract growth, same as
growing `qa.config.schema.json`, not a per-project override.

| `taskType` | Baseline tier | Matches |
|---|---|---|
| `result-read` | `fast` | Reading/summarizing a `result.json`, a case-result file, a run's tail output — confirming what already happened, not investigating why |
| `unit-property-mutation-analysis` | `standard` | Interpreting unit/property/mutation test results |
| `e2e-authoring-debugging` | `standard` | Writing or debugging Playwright or Claude-in-Chrome scenario coverage |
| `bug-investigation` | `deep` | Root-causing a failure across files, not just reading its symptom |
| `architecture-security-review` | `deep` | Architecture review, security review, or QA Verification on a scope that hit `router.riskPaths`/`router.riskKeywords` |

An unrecognized or missing `taskType` is a missing signal, not an error to guess past — see §5.

## 4. Decision order — risk always wins, file count never decides alone

Applied in this order; a later rule can only escalate, never downgrade, what an earlier one set:

1. **Risk match forces `deep`, full stop.** If any file in `files` matches a `router.riskPaths` glob, or
   any file path or the `note` text contains a `router.riskKeywords` keyword (case-insensitive substring),
   the tier is `deep` regardless of every other signal — task type, file count, module count. No later
   rule may reduce it.
2. Otherwise, start from `taskType`'s baseline tier (§3).
3. **Cross-module escalation.** If `files` spans more than one top-level module/directory and the current
   tier is `standard`, escalate to `deep` — reasoning that has to hold two modules' worth of context
   consistently is qualitatively harder than either module alone, independent of how many files that
   represents. This rule never touches `fast` (a `fast`-tier task is mechanical by task type, not by
   scope, so spanning modules does not change what kind of work it is).
4. **File count is a tie-breaker only, never a first cause.** A `standard`-tier task touching an unusually
   large number of files (default threshold: 15, tune per project — see the script's own comment) escalates
   to `deep`. This rule cannot fire before rules 1-3 have already set a tier from a real signal; it never
   evaluates on `fast` or already-`deep` tasks, and it is the only place file count enters the decision at
   all. This is the literal mechanism behind "don't route on line/file count alone": count only ever
   nudges a tier that a non-count signal already chose.

## 5. Fail-safe default

If `taskType` is missing or unrecognized, the router cannot honestly place the task in `fast` or
`standard` — both of those require the task to be recognized as mechanical or scoped. Default to `deep`
and say why in the printed reason. This mirrors the harness's own convention that an unresolved check is
never silently treated as passing: an unresolved *routing* decision is never silently treated as cheap.

## 6. Config surface (`qa.config.yaml`)

```
router.enabled: true                              # opt-in; omit or false leaves routing off entirely
router.riskPaths: src/services/auth*,src/**/*cognito*
router.riskKeywords: cognito,oauth,phi,patient,payment
router.tiers.fast.agent: qa-fast-check
router.tiers.standard.agent: qa-standard-review
router.tiers.deep.agent: qa-deep-review
```

`riskPaths`/`riskKeywords` are project-owned on purpose — this kit has no opinion on what counts as
risky for a given codebase. A healthcare project's list looks like the example above; a different
project's does not, and that is the point of leaving it in config rather than baking a keyword list into
`core/`.

## 7. Why the harness and E2E stages are out of scope for routing

`harness.runCommand`, `e2e.ticketCommand`, and `e2e.regressionCommand` are shell commands with exit
codes — no model reads or writes anything to produce their verdicts, so there is no token cost there to
route. Routing only ever applies to the agentic reasoning around those stages: interpreting their output,
authoring the E2E coverage that becomes `e2e.*Command`, and QA Verification's evidence-vs-criteria
reconciliation. `examples/skills/*.md` name exactly where in each workflow that reasoning happens and
which `taskType` fits it.

## 8. What this contract does not do

It does not measure actual token spend, does not call any API to make its decision, does not track
cost against a budget, and does not choose *between* two models of the same tier (e.g. which vendor's
fast model) — that is an even more project-specific decision than this kit takes on elsewhere. It also
does not enforce its own recommendation: a human or an orchestrating skill can ignore `AGENT=` and run a
task at whatever tier it wants. The recommendation existing and being easy to see is the entire
mechanism — see `docs/pattern-handbook.md` for why that is a deliberate limit, not an oversight.
