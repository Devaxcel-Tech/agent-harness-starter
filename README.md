# Agent Development Harness — starter kit

Seven controls that let a team ship at high throughput with AI agents writing most of the code.
Language-agnostic, no third-party dependencies, drop into any git repository.

**Start with the two documents.** `docs/pattern-handbook.pdf` explains *why* each control exists and
what failure it removes. `docs/adoption-guide.pdf` is the same material as an install sequence.

## The problem

When an agent writes the code *and* its tests, a green suite proves almost nothing: if it misread the
requirement, both are wrong in the same direction and agree perfectly. Ordinary quality practice
assumes an independent human author somewhere in the loop. Remove that assumption and most of it stops
working — coverage targets reward assertion-free tests, same-family review shares the author's blind
spots, and a documented process becomes unfalsifiable.

Every control here restores one specific piece of independence that automation took away.

## The eight controls

| Control | The failure it removes |
|---|---|
| Four exit codes | A check that never ran reporting as a pass |
| Gate fault suites | A gate that cannot fail, indistinguishable from correct code |
| Decision register | A guess in the code becoming indistinguishable from a decision |
| Trigger gates | "Not applicable" silently becoming "unmeasured" |
| Drift protection | Copied shared files rotting with nothing noticing |
| CI ordering laws | One check's failure hiding another's verdict |
| Independence controls | An author's tests confirming the author's misunderstanding |
| The loop, and its register | The process losing a step across a dozen edits, unnoticed |

The last one is different in kind from the other seven. They are checks that fire when something runs
them; the loop is the thing that runs them, and `examples/skills/task-loop/` is where it lives. A gate
nobody invokes is as inert as a gate that cannot fail.

Its register (`tools/gates/loop-obligations.expected`) is worth understanding before you adopt it. The
rows are authored from the handbook, not from the skill, because **a register scraped out of the thing
it checks is a mirror** — it agrees with whatever the skill currently says, so it can never disagree
and never has anything to tell you. If you take the loop and have no separate document stating your
process, author your rows from something — an ADR set, a team guide — or know that the check is
agreeing with itself.

And the honest limit, which the gate prints on every run: it proves the skill still **carries** each
obligation. It cannot prove a live run **obeyed** them. No static check reaches that.

## Quickest useful path

```bash
# 0. Turn on branch protection. Without it every control below only advises.
#    Verify:  gh api repos/<org>/<repo>/branches/main/protection

# 1. Copy the kit in (preserving paths — the gates resolve each other by relative path)
mkdir -p <your-repo>/tools <your-repo>/docs <your-repo>/.github/workflows
cp -r tools/gates tools/qa <your-repo>/tools/
cp -r .githooks <your-repo>/
cp .gitleaks.toml <your-repo>/
cp docs/DECISIONS.md <your-repo>/docs/
cp examples/workflows/*.yml <your-repo>/.github/workflows/

# 2. Prove the gates can fail — run this FIRST, it validates the validators
python3 tools/gates/check_gates_test.py

# 3. Turn the hook on, and run the floor
git config core.hooksPath .githooks
bash tools/qa/run-qa.sh
```

## What is here

```
tools/gates/harness.py                        the exit-code contract
tools/gates/check_decisions.py                decision register gate
tools/gates/check_vendored_drift.py           shared-file drift gate
tools/gates/check_mutation_applicability.py   a worked trigger gate
tools/gates/check_loop_obligations.py         the loop still carries every obligation
tools/gates/loop-obligations.expected         the obligations, authored from the handbook
tools/gates/check_gates_test.py               fault injection for every gate
tools/gates/expected-gates.txt                gates that must exist
tools/qa/run-qa.sh                            runs the floor, writes durable evidence
docs/DECISIONS.md                             empty register + schema
docs/pattern-handbook.html/.pdf               why each control exists
docs/adoption-guide.html/.pdf                 how to install it, in stages
.githooks/pre-commit                          discovers and runs every gate
examples/skills/task-loop/SKILL.md            the loop itself — the thing that runs the gates
examples/workflows/                           gates + secret-scan templates
.gitleaks.toml                                secret-scanning config
examples/vendored.json                        drift manifest template
examples/agents/                              four review lenses + three QA-tier agent examples
examples/tool-servers.json.example            tool-server config template
examples/session-start.sh                     grounding hook
examples/CODEOWNERS.example                   review routing
```

### Optional layer: QA workflow framework

`core/`, `qa.config.schema.json` and `tools/qa-workflow/` are a separate, optional layer that sits
**around** the harness above, turning its exit-code gates and a project's own Playwright (or other) E2E
suite into two repeatable QA workflows — ticket/feature testing and regression — with one shared result
contract: **PASS / FAIL / BLOCKED**. It imports the harness's exit-code vocabulary rather than redefining
it, so install the harness first.

```
core/                              contracts — never edited per project
  result.schema.json                 the canonical result shape and its PASS/FAIL/BLOCKED rollup rule
  case-result.schema.json            the shape one engine writes per case (results/<CASE-ID>.json)
  e2e-engine-contract.md             what a Playwright/Claude-in-Chrome (or other) engine must expose
  model-router-contract.md           what tools/qa-workflow/route-task.py decides, and why it never enforces it
  jira-workflow-contract.md          Workflow 1 (ticket/feature testing), stage by stage
  regression-workflow-contract.md    Workflow 2 (regression), stage by stage
qa.config.schema.json              the one file a project fills in — schema for its qa.config.yaml
tools/qa-workflow/
  run-qa-workflow.sh                 runs harness + E2E (all configured engines), writes the result record
  aggregate-e2e-results.py           rolls up one agent-driven engine's case-result files into a verdict
  route-task.py                      recommends a model tier (fast/standard/deep) for a task — advisory only
  check_result_contract.py           gate: every result record on disk is well-formed and honestly rolled up
  check_qa_config.py                 gate: qa.config.yaml satisfies the schema
examples/qa.config.example.yaml    a filled-in example (fictional project)
examples/skills/qa-ticket-flow/    orchestrator for Workflow 1
examples/skills/qa-regression-flow/  orchestrator for Workflow 2
examples/skills/qa-browser-explore/  the claude-in-chrome engine — agent-driven browser session
docs/qa-workflow-pattern-handbook.md   why each stage exists, what failure it removes
docs/qa-workflow-adoption-guide.md     how to install this layer into a project, in stages
```

Same design rule as the rest of the kit: **common core, project-specific config — never the reverse**.
Nothing under `core/` or `tools/qa-workflow/` names a project, a tracker, or a technology stack — every
project-specific fact (which issue tracker, which Playwright project, which test command) lives in one
file the project owns, `qa.config.yaml`.

```bash
# after the harness itself is installed (see Quickest useful path above)
mkdir -p <your-repo>/tools/qa-workflow
cp -r tools/qa-workflow/*.sh tools/qa-workflow/*.py <your-repo>/tools/qa-workflow/
cp qa.config.schema.json <your-repo>/tools/qa-workflow/
cp examples/qa.config.example.yaml <your-repo>/qa.config.yaml   # then edit it — see docs/qa-workflow-adoption-guide.md

python3 <your-repo>/tools/qa-workflow/check_qa_config.py
bash <your-repo>/tools/qa-workflow/run-qa-workflow.sh regression
```

## Two things to know before you start

**Nothing here blocks anything without branch protection.** Gates, hooks and review panels only
advise. Measured on the implementation this was extracted from, before protection was configured:
134 of 134 changes merged by their own author, zero approvals ever recorded, median 39 seconds from
open to merge. The harness was good and enforced nothing.

**Run the fault suite before trusting any gate.** A gate that always passes is indistinguishable from
a codebase that is always correct — the output is identical. When this kit's suite was first run
against its own gates it found two real bugs, both of which would have survived code review
indefinitely.

## Adapting it

`ID_PREFIX`, the `REQUIRED_FIELDS_*` lists, `SOURCE_EXTENSIONS` and `CONFIG_CANDIDATES` are meant to be edited for your
project and language. Adding a field is tailoring. Removing a check because something fails it is
deleting the finding — the two look identical in a diff, so say which you are doing.

## Contributing

Corrections, clearer wording, support for another language, or a control this is missing — all welcome.
Open a pull request; you do not need to ask first. If you would rather just report the problem than fix
it, open an issue.

Two things worth knowing before you send a change:

- **`tools/gates/check_gates_test.py` is the suite that proves the gates work.** Run it before and after
  your change. A gate altered without a case covering the new behaviour is a gate nobody has watched
  fail.
- **A change that makes a check quieter needs to say so.** Loosening a rule and fixing a false positive
  produce the same diff. Say which one you are doing, in the pull request body.

Anything the maintainers cannot settle from the documentation gets recorded in `docs/DECISIONS.md`
rather than guessed at.

## License

[Apache License 2.0](LICENSE). Use it, fork it, ship it in a commercial product — the licence includes
an express patent grant, so contributions carry clear terms in both directions.
