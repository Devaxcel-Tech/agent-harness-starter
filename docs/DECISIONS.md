# Decision register — questions that need an owner

**This file is empty on purpose.** An empty register is a valid state: it means no blocked decision
has been recorded yet. `tools/gates/check_decisions.py` passes on an empty register and says it
validated *zero rows* — it does not report a pass as though it had checked something.

## What belongs here

A question you cannot answer from the project's design, whose answer changes what the code does.
Not a task. Not a "we should probably". The test is the **entry condition** below.

## What does not belong here

Work you know how to do but have not done. That is a backlog item. A register that fills with
to-do items stops being read, and then the one real blocked decision in it is invisible.

## The rules

1. **A number is never reused and never renumbered.** A row keeps its id for life and changes only
   its status. Renumbering on closure dangles every citation of the old number.
2. **Every open row links an issue.** This is the delivery mechanism — the tracker's assignment
   notification is what actually reaches a human. A row with no issue has told nobody anything.
3. **Every open row names what differs in the code.** If you cannot name what would physically
   differ between the options, this is a task, not a decision.
4. **A row closes by citing a ruling**, not a date and not a memory. A later reader must be able to
   look it up.
5. **Do not cite another repository's decision number.** These numbers are per-repository and they
   collide. Refer to it by subject and repository instead.

## Template — copy this

```
## DEC-1 — <the question, as a question>

- **Status:** OPEN
- **Issue:** https://github.com/<org>/<repo>/issues/<n>
- **What is owed:** <what the decision would settle, and who is blocked by it>
- **Why the work stopped:** <what you could not do without it>
- **What was done instead:** <the interim state, so a reader knows what they are looking at>
- **Candidate answers:** (a) <first option> (b) <second option>
- **What differs in the code:** (a) <concrete change, naming a `path/or.symbol`> (b) <the other>
- **Ruling:** —
```

<!-- Rows go below. Keep them in numeric order. -->
