# Pattern handbook — why each stage exists

Each stage removes one specific way a QA process quietly stops meaning anything. Read this before
adopting the kit; `adoption-guide.md` is the same material as an install sequence.

## Why two workflows and not one

A ticket-scoped workflow answers "did this change do what it claimed." A regression workflow answers "is
everything that already shipped still true." Collapsing them into one process means every regression run
either needs a ticket invented for it (so the traceability field means nothing, since there is no real
requirement behind it) or the ticket-scoped workflow loses its acceptance-criteria anchor to accommodate
runs that have none. Keeping them separate, sharing the harness and E2E stages, keeps both anchors real.

## Why the Harness stage is separate from the E2E stage

The harness proves what the code **is** — structurally, independent of intent: no undocumented guess
masquerading as a decision, no drifted copy of a shared file, no gate that can never fail. The E2E stage
proves what the code **does** when driven like a user would. A codebase can pass one and fail the other
in either direction: clean structure with a broken feature, or a working feature built on a guess nobody
recorded. Reporting them as one merged verdict would make it impossible to tell which failed.

## Why QA Verification is its own stage, not folded into E2E

A green E2E run proves the suite executed and its assertions held — for whatever the suite's author
believed to check. If that author misread the requirement, the suite agrees with the misreading
perfectly, and a merged "E2E passed" verdict reports that agreement as success. Verification is the one
stage where a reader compares evidence against the **quoted** requirement, performed by someone who did
not write the code or the test — the same independence principle the Agent Development Harness applies
to review, applied here to the one place a self-confirming green is most expensive to miss: the final
verdict.

## Why PENDING is a real state and not folded into PASS or skipped

A `result.json` written the instant Harness and E2E finish, with `qaVerification` silently defaulted to
PASS, is indistinguishable from one where a human actually looked at the evidence. The entire value of an
independent verification stage evaporates the moment a tool can produce its own placeholder pass. PENDING
exists so an unreviewed result and a reviewed one can never be confused by whatever reads the record next
— a dashboard, a release gate, a person skimming Jira.

## Why the result contract is a schema, not a format convention

"Everyone knows the shape" is how a report format drifts silently, one project at a time, until nothing
downstream can parse every project's version. `core/result.schema.json` plus `check_result_contract.py`
make the shape a checked property instead of a convention — including the rollup rule itself, which is
exactly the kind of thing a hand-edited record is most likely to quietly violate.

## Why the E2E engine contract stops short of prescribing a folder-per-project structure

Every project's domain shapes its data differently — a Vue app's roles and selectors are not a Flutter
app's widget tree, and a backend's contract tests are neither. The contract fixes what every workflow
consumer needs to rely on (case IDs, the five-word status vocabulary, an evidence layout it can locate
deterministically) and leaves everything else — how data files are organized, what a "module" means —
to the project. Prescribing more than that would recreate the coupling this kit exists to remove.

## Why config is one flat file and not a directory of YAML

A nested config format needs a real parser to read correctly, and a real parser is a dependency this kit
either vendors (drifts, needs updating) or requires installed (a CANNOT_RUN waiting to happen). Flat
dotted keys can be read with a five-line loop in any language a project's tooling already has — which is
also why the schema is enforced by a hand-written check rather than a JSON-Schema library: the property
being protected (this kit runs without needing anything installed) would be undermined by the tool that
checks it needing something installed.

## Why the model router is advisory, and never switches a model itself

This kit has no way to force a model choice — it has no runtime that owns the session a human or agent is
already working in, only a script that can be run before one starts. Building `route-task.py` to *call* a
model API to make its own recommendation, or to try to intercept and redirect an in-flight session, would
add a real dependency (credentials, a network call, a new failure mode indistinguishable from "the router
is broken" versus "the task is broken") to solve a problem a printed recommendation already solves at zero
risk. The cost of an ignored recommendation is a wasted opportunity to save money; the cost of a router
that can silently fail *and* silently downgrade a security review to a cheap model because its own call
timed out is a real defect masquerading as a cost optimization. Advisory-only is the deliberately smaller
blast radius.

## Why risk detection always wins, and file/line count is never a first cause

A large low-risk change and a one-line change to an auth path are not equivalent just because one touches
more lines — this is the same reasoning `core/e2e-engine-contract.md` applies to zero-tests-executed
looking like a pass: a signal that is easy to compute (line count, file count) is not the same signal as
the one that actually matters (does this change PHI/auth/payment handling), and conflating them produces
a router that is cheap to fool. Fixing risk detection as the rule nothing else can override, and confining
file count to a tie-breaker that can only escalate an already-`standard` task, keeps the one criterion this
kit's own adopting project called out explicitly — "don't route on line count alone" — true by
construction, not by convention a future edit could quietly erode.
