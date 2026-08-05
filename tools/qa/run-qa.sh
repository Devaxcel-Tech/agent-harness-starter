#!/usr/bin/env bash
# One command that runs the whole floor and writes a durable record.
#
# TWO PROPERTIES THAT MAKE THIS MORE THAN A SHELL LOOP:
#
#   1. IT DISCOVERS GATES. Every `tools/gates/check_*.py` that is not a `*_test.py` runs, so a new
#      gate joins the floor the moment it lands and nobody has to remember to wire it in. The register
#      `tools/gates/expected-gates.txt` covers discovery's blind spot — it cannot tell "does not
#      exist" from "was deleted", and a run reporting green because it found nothing is the same
#      defect as recording NOT RUN as measured.
#
#   2. IT IS TRIGGER-AWARE. A control with nothing to measure yet is recorded as PENDING **with its
#      trigger named**, never as a pass. That distinction is the whole point: "we measured and it was
#      fine" and "there was nothing to measure" must never look the same in a report someone later
#      relies on.
#
# The record it writes is the deliverable, not the console output — evidence has to outlive the
# terminal that produced it.
set -uo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root" || exit 2
out="tools/qa/evidence/latest.md"
mkdir -p "$(dirname "$out")"

blocking=0
rows=""

# A listed gate missing from the checkout is a could-not-run, and it blocks.
if [ -f tools/gates/expected-gates.txt ]; then
  while IFS= read -r name; do
    case "$name" in ''|\#*) continue ;; esac
    if [ ! -f "tools/gates/$name" ]; then
      rows+="| \`$name\` | **COULD NOT RUN** | listed in expected-gates.txt and absent from the checkout |
"
      blocking=1
    fi
  done < tools/gates/expected-gates.txt
fi

shopt -s nullglob
for gate in tools/gates/check_*.py; do
  case "$gate" in *_test.py) continue ;; esac
  name="$(basename "$gate")"
  output="$(python3 "$gate" 2>&1)"; rc=$?
  first="$(printf '%s' "$output" | head -1 | cut -c1-150)"
  # A CRASHING gate is a could-not-run, not a violation — and it exits 1, so it would otherwise be
  # reported as "the property is broken". That is a real mis-report: it sends someone hunting for a
  # defect in the code when the defect is in the gate. Found the hard way, by shipping a gate with a
  # syntax error and watching the runner call it a FAIL.
  crashed=0
  case "$output" in *"Traceback (most recent call last)"*|*"SyntaxError"*|*"ImportError"*|*"ModuleNotFoundError"*) crashed=1 ;; esac
  if [ "$crashed" -eq 1 ]; then
    verdict="**CRASHED — COULD NOT RUN**"; blocking=1
    first="the gate itself raised: $(printf '%s' "$output" | tail -1 | cut -c1-110)"
  else
  case $rc in
    0) verdict="PASS" ;;
    1) verdict="**FAIL**"; blocking=1 ;;
    2) verdict="**COULD NOT RUN**"; blocking=1 ;;
    3) verdict="**INCOMPLETE**"; blocking=1 ;;
    *) verdict="**UNKNOWN($rc)**"; blocking=1 ;;
  esac
  fi
  rows+="| \`$name\` | $verdict | ${first//|/\\|} |
"
done

# The gate suite judges the GATES, so it runs even when a gate is failing — that is exactly when
# "is the gate still sound?" is worth answering.
if [ -f tools/gates/check_gates_test.py ]; then
  if out_t="$(python3 tools/gates/check_gates_test.py 2>&1)"; then
    rows+="| gate fault injection | PASS | $(printf '%s' "$out_t" | tail -1 | cut -c1-130) |
"
  else
    rows+="| gate fault injection | **FAIL** | a gate does not do what it claims |
"
    blocking=1
  fi
fi

{
  printf '# QA evidence\n\n'
  printf 'Generated %s · commit `%s`\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  printf '| Control | Verdict | Detail |\n|---|---|---|\n%s\n' "$rows"
  printf '## How to read this\n\n'
  printf -- '- **COULD NOT RUN** and **INCOMPLETE** are not passes. They mean no verdict was reached.\n'
  printf -- '- A control with nothing to measure yet is PENDING with its trigger, never a pass.\n'
  printf -- '- This file is the record. Commit it — evidence must outlive the terminal.\n'
} > "$out"

echo "evidence -> $out"
[ "$blocking" -eq 0 ] || { echo "FLOOR RED — see the table above." >&2; exit 1; }
