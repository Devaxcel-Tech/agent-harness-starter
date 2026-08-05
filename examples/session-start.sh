#!/usr/bin/env bash
# Session-start hook: put the agent's grounding material in place before it does anything.
#
# WHY THIS EXISTS. An agent that cannot read the design source will not stop and ask — it will infer a
# plausible design and implement that, confidently. Whatever holds your requirements (a submodule, a
# docs directory, a wiki export) has to be present at session start, not fetched on demand, because
# "fetch it if you need it" reliably becomes "did not think it was needed".
#
# TWO PROPERTIES THAT MATTER:
#   * IDEMPOTENT — it runs on every session start, so it must be safe to run repeatedly.
#   * NON-FATAL — it warns and lets the session start. A hook that blocks a session because a network
#     fetch failed will be deleted by the first person it inconveniences, and then nobody has it.
#
# Wire it into whatever your runtime calls a session-start hook.
set -uo pipefail

root="${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
cd "$root" || exit 0

# Adapt this block to however your design source is obtained.
if [ -f .gitmodules ] && grep -q 'path = docs-source' .gitmodules 2>/dev/null; then
  git submodule sync --quiet docs-source >/dev/null 2>&1 || true
  if ! git submodule update --init --remote docs-source >/tmp/design-source.log 2>&1; then
    cat >&2 <<'MSG'
WARNING: could not fetch the design source.

The session will start anyway — but GROUND YOUR WORK BEFORE WRITING CODE. If you cannot
read the requirement, do not infer it: record a blocked decision instead (docs/DECISIONS.md).
An inferred requirement is indistinguishable from a real one once it is in the code.
MSG
  fi
fi
exit 0
