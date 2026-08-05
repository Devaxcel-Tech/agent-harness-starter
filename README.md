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

## The seven controls

| Control | The failure it removes |
|---|---|
| Four exit codes | A check that never ran reporting as a pass |
| Gate fault suites | A gate that cannot fail, indistinguishable from correct code |
| Decision register | A guess in the code becoming indistinguishable from a decision |
| Trigger gates | "Not applicable" silently becoming "unmeasured" |
| Drift protection | Copied shared files rotting with nothing noticing |
| CI ordering laws | One check's failure hiding another's verdict |
| Independence controls | An author's tests confirming the author's misunderstanding |

## Quickest useful path

```bash
# 0. Turn on branch protection. Without it every control below only advises.
#    Verify:  gh api repos/<org>/<repo>/branches/main/protection

# 1. Copy the kit in
cp -r tools/gates tools/qa .githooks .gitleaks.toml docs/DECISIONS.md <your-repo>/
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
tools/gates/check_gates_test.py               fault injection for all three (22 cases)
tools/gates/expected-gates.txt                gates that must exist
tools/qa/run-qa.sh                            runs the floor, writes durable evidence
docs/DECISIONS.md                             empty register + schema
docs/pattern-handbook.html/.pdf               why each control exists
docs/adoption-guide.html/.pdf                 how to install it, in stages
.githooks/pre-commit                          discovers and runs every gate
examples/workflows/                           gates + secret-scan templates
.gitleaks.toml                                secret-scanning config
examples/vendored.json                        drift manifest template
examples/agents/                              four review lenses
examples/tool-servers.json.example            tool-server config template
examples/session-start.sh                     grounding hook
examples/CODEOWNERS.example                   review routing
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

`ID_PREFIX`, `REQUIRED_FIELDS`, `SOURCE_GLOBS` and `CONFIG_CANDIDATES` are meant to be edited for your
project and language. Adding a field is tailoring. Removing a check because something fails it is
deleting the finding — the two look identical in a diff, so say which you are doing.
