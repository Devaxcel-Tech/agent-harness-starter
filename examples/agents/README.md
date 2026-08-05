# Review subagents — four narrow lenses

Each file here defines a reviewer that looks at a change through **one** lens. The narrowness is the
point: one generalist "review this" pass consistently misses what four specialists catch, because a
generalist prompt optimises for a coherent-sounding summary rather than for finding the one problem.

Run them **in parallel** on the same diff and synthesise the findings. Format is whatever your agent
runtime expects — the content below is what matters.

## Why four, and why these four

They partition the ways a change goes wrong, with as little overlap as possible:

| Lens | Asks |
|---|---|
| security | Could this leak, escalate, or fail open? |
| architecture | Is this in the right place, and does it respect the boundaries? |
| code quality | Is it correct and maintainable, and do the tests actually test it? |
| modularity | What does this couple to, and which way do the dependencies point? |

## Two rules that make them worth running

1. **They advise; they do not approve.** An automated verdict is not a merge authority. If it becomes
   one, people learn to write changes that satisfy the reviewer rather than changes that are right.
2. **Same-family reviewers share the author's blind spots.** If your agents and your reviewers come
   from the same model family, this panel gives you *lens* diversity but not *lineage* diversity. Both
   are worth having and they are not substitutes — see the different-lineage reviewer in the Pattern
   Handbook.
