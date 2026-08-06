---
name: task-loop
description: The entry point for implementation work. Bare, it runs a SESSION — interviews you for goals, projects them onto work that already exists, plans each chunk for your approval, then executes unattended. With an issue number it runs ONE ticket, ground to PR, and stops. Use for both "let's work on X this evening" and "do issue 351".
---

# task-loop — implementation work, in two modes

This is the process control. Every other control in this harness is a check that fires when something
runs it; this is the thing that runs them. A gate nobody invokes is as inert as a gate that cannot
fail.

**Registered against `tools/gates/loop-obligations.expected`,** whose rows are authored from the
handbook rather than from this file, so the two can disagree. Run
`python3 tools/gates/check_loop_obligations.py` after editing this skill. If a row stops resolving,
**this skill is the defect** — restore the step. Never narrow the row.

## Usage

```
task-loop                    # SESSION — interview, scope, plan, your approval, then unattended
task-loop <issue-number>     # WORKER  — one ticket, ground to PR, then stop
task-loop "<description>"    # WORKER, ad-hoc (still produces a branch and a PR)
task-loop --self-test        # SELF-TEST — walk every stage on a fixture, ship nothing
```

**A bare invocation is a session, not "pick something for me".** Never quietly fall back to taking the
oldest open issue. Scope is *selected from work that already exists*, never invented — that guessing
is the failure this command exists to prevent.

## Hard rules — both modes, no exceptions

- **Stop at the PR.** You **do not merge** your own work. Never push to the default branch. Never
  force-push a shared branch. **STOP** when the PR is open.
- **Never weaken a check to make it pass.** This explicitly includes lowering a mutation floor,
  deleting a failing property test, narrowing a generator until it stops finding the counterexample,
  and mocking the dependency that a fault-injection test exists to break.
- **Exit codes 2 and 3 are not passes.** A check that could not run has reached no verdict. Treating
  it as green reintroduces the defect the four exit codes remove.
- **Halt rather than guess.** A clean stop with a precise question beats a plausible guess every time.
- **Never commit secrets**, keys, or `.env` files.
- **Remember what actually blocks.** None of this blocks anything without **branch protection** on the
  default branch. Everything here advises until that is switched on.

---

# SESSION mode — supervised at the top, unattended at the bottom

Stage ⑤ is the last moment a misunderstanding costs minutes instead of a day.

### ① Interview — ask, then wait

Ask these and **wait for real answers**. Do not propose a scope first: a proposal anchors the reply,
and you get your own guess edited rather than the person's intent.

1. What is this session for, in your own words?
2. How long may it run — one chunk, an evening, overnight?
3. Anything deliberately out of scope?

Then **restate the goals in your own words and get the restatement confirmed.** That restatement is
the artifact everything downstream selects against.

**Nobody to interview** (scheduled run, no human attached)? Do not guess. Use a pre-agreed scope file
if one was named, otherwise **halt and say so**. An unattended session with an unagreed scope is the
most expensive failure available to you.

### ② Project the goals onto work that already exists

Read open issues and your roadmap. For each candidate, before selecting it, read its dependencies and
its exit criterion — which must be something a test can assert. A candidate with an unmet dependency
is not selected, however well it matches the goal.

### ③ Classify every gap before filling it

Some part of the goal will have no ticket. Each gap is exactly one of two kinds, and the test has no
exceptions: **can you quote a written requirement — document, section, identifier — that settles what
to build?**

- **Yes → an implementation gap.** The design is settled and only the tracking ticket is missing.
  File it, with the exit criterion written as something a test asserts.
- **No → a design gap. STOP.** Record a row in `docs/DECISIONS.md` naming what differs in the code
  between the candidate answers, **open the issue**, and move to the next chunk. **Do not choose the
  sensible option** — you will always produce one, and once it is in the code it is indistinguishable
  from a decision somebody actually made.

### ④ Chunk by shared file scope, not by size

One issue is one chunk. Where issues must share a chunk, the criterion is **the files they touch**:
issues touching the same files belong in the *same* chunk, because sequencing inside a chunk is free
while the same pair split across concurrent chunks is a merge conflict. A change touching build files
tree-wide has a file scope of everything, so it runs alone.

### ⑤ Plan each chunk, check it twice, then get approval

Produce a **phased plan** with a **verification checkpoint** per phase. Compute the **blast radius**
first — what calls the thing you are about to change, and what breaks if it moves. That call graph is
your **test scope**; it is the difference between testing what you wrote and testing what you
affected.

Then two independent checks, **before any code** exists:

1. **Goal-backward** — would this plan, executed exactly, meet the chunk's exit criterion?
2. **`architecture-reviewer`** — does it violate a boundary? This is the cheapest place in the whole
   sequence to catch that, because nothing has been built.

**Every plan carries its own controls as plan steps.** A worker follows the plan, so a control not
written into the plan does not run — and a control that does not run is not a control.

**Then stop and present the plans for approval — once, for the whole session.** That "yes" is the
boundary. Do not begin without it, and do not ask again per chunk.

### ⑥–⑨ Unattended: execute, prove, review, report

One worker per chunk, each **in its own worktree** — `git worktree add`, and **never a branch switch
in place**. `git checkout -B` mutates the tree other sessions are using, moving their HEAD and their
working files mid-task. Create worktrees **one at a time**: simultaneous adds race on
`.git/config.lock`.

**A halt advances to the next chunk; it does not end the session.** A session that halts on three
chunks and lands two did its job. One that guessed on three and landed five did damage nobody will
notice for weeks.

**Compact context only after a chunk is achieved, tested and _recorded_ — in that order.** It is a
precondition, not a preference: compaction discards the conversation, so anything not already in a
durable artifact is destroyed by it. Carry forward only the approved restatement, the chunk list,
where things stand, and *pointers* to plan, issue and evidence — never contents. **Then re-read, do
not remember:** re-open the cited requirement and the approved plan. A compacted rendering of a rule
is a paraphrase, and paraphrase is what this process forbids everywhere else.

---

# WORKER mode — one ticket, ground to PR

### 0. Intake, in your own tree

Restate the scope in one paragraph and post it as an issue comment. Two readings implying materially
different work → **halt, ask, stop**.

Branch — **never the default branch** — and take a worktree rather than switching in place:

```bash
git fetch origin main
git worktree add ../<repo>-<topic> -b <topic> origin/main
```

Export credentials into the **process environment** of the shell you start from. Tool servers read
them from there; a `.env` file that nothing sources leaves every server unauthenticated while looking
configured.

### 1. Ground — the step that prevents confidently-wrong work

Find the written requirement that governs the work and **quote** the exact sentence —
**never a paraphrase**. A paraphrase is where the misreading enters, and six months later it is
indistinguishable from the real thing.

Then check whether a later decision **superseded** it. Building correctly against an overridden rule
produces confidently wrong code with a citation attached, which is far harder to catch than plain
error.

If the requirement does not settle the question, you are at stage ③'s branch point. Stop.

### 2–3. Plan, and review the plan

As stage ⑤ above: phased plan, blast radius, then `architecture-reviewer` **before any code**. Fix the
plan, not the code later.

### 4. Implement — test first, with the quote in the test

```
RED       write the failing test, with the QUOTED requirement in a comment
          run it — watch it fail. A test you have not seen fail proves nothing.
GREEN     the minimum implementation that satisfies it
REFACTOR  keep it green
```

Put the **quoted requirement in the test**, not only in the commit message. Test-first by the same
agent that writes the code is still self-confirmation if the requirement was misread — the red test
encodes the same misunderstanding the green code satisfies. The quote is what makes that visible to
the next reader and to the blind-conformance author below.

Adding a module? Its metadata and registry **row before the code**, so an unregistered module fails
the build rather than an eventual review.

### 5. Prove it, in cost order

| Control | When | What a bad result means |
|---|---|---|
| **structural gates** | every commit, sub-second | something is in the wrong place, or a row is missing |
| **property** tests | when the change touches a law, not a case | you are handed the minimal counterexample |
| **mutation** | before the PR | a **surviving mutant** is a **missing assertion** — add it, and **never lower** the floor |
| **fault injection** | every fail-closed path | the dependency really failed and the system did the wrong thing |
| **blind conformance** | subtle or safety-bearing requirements | a disagreement is a **finding for a human** — **do not resolve it**, your reading is what is in question |

Not built one of these yet? **Say so rather than implying coverage.** A control whose subject does not
exist reports **PENDING** with **its trigger** named — that is a correct, honest report. Inventing a
green is a **faked pass**, and it is the precise defect this whole harness exists to remove.

Then run the orchestrator once and **commit the evidence** file. Evidence has to outlive the terminal
that produced it.

**When a gate fails there are exactly three legitimate moves:** fix the code (usually right); **fix
the gate as its own change**, with its own reasoning and its own test, never while making your change
pass; or record a decision and route around it. Lowering a threshold is **not on the list**.

Failing twice on the same root cause → one different-family diagnosis pass, then **halt** with both
diagnoses. Do not keep re-rolling.

### 6. Review — two kinds of independence

Run the narrow lenses **in parallel**, locally, where they are free. Then run a **different-family**
reviewer. These are different controls, not more of the same: the lenses give you **diversity of
attention**, the other family gives you **diversity of failure**.

Record every finding in the PR as acted-on or **dismissed with a reason**. If a pass could not run —
quota, missing tool, wrong environment — record it as **skipped** with the reason. **Never omit** it
silently: an absent review and a clean review look identical in a PR body otherwise.

### 7. Raise the PR, then stop

The PR body states what shipped, the verification results (**results, not assurances** — not
"mutation ran" but the score against its floor; not "fault injection done" but which dependency was
failed and what the system did), the quoted requirement, findings acted on or dismissed, any skipped
pass, and what you **deliberately did not do**. That last part is the one people skip and the one
that makes the rest believable — a record claiming a control that never ran is worse than one
admitting a gap, because somebody will rely on it.

Link the issue and **choose the verb deliberately**: `Closes #N` only when this PR completes every
remaining requirement of that issue, otherwise `Refs #N`. A `Closes` on partial work auto-closes the
issue on merge and the remainder becomes invisible.

**You do not merge.** **STOP.**

## Halt protocol

Leave the branch and commits in place. Say (a) exactly where you stopped, (b) the diagnosis with
evidence, (c) the specific decision needed, (d) your recommendation. In session mode, then move to the
next chunk.
