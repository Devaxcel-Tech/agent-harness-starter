#!/usr/bin/env bash
# The one entry point for both workflows. It runs the two automatable stages — Harness and E2E — and
# stops. QA Verification is deliberately NOT automated here: it is an independent human (or an
# independent agent identity, never the one that authored the code) judging the evidence against the
# quoted acceptance criteria. A script that fills that stage in for itself has reintroduced exactly the
# self-confirmation problem this whole kit exists to prevent.
#
# USAGE
#   run-qa-workflow.sh ticket <TICKET-ID>              stages 3-4 of core/jira-workflow-contract.md
#   run-qa-workflow.sh regression [scope-id]            stages 1-2 of core/regression-workflow-contract.md
#   run-qa-workflow.sh verify <result.json> <PASS|FAIL|BLOCKED> <reviewer> [notes]
#                                                        records stage 5/3 (QA Verification) and computes finalResult
#
# CONFIG: reads <repo-root>/qa.config.yaml — flat `key: value` lines only, see qa.config.schema.json.
# This is parsed with a plain bash loop, not a YAML library, for the same reason the harness ships with
# zero third-party dependencies: a workflow that cannot run because a package was not installed is
# indistinguishable, from the outside, from a workflow that ran and found nothing wrong.
set -uo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root" || { echo "run-qa-workflow: could not enter the repo root." >&2; exit 2; }

config="$root/qa.config.yaml"
if [ ! -f "$config" ]; then
  echo "run-qa-workflow: $config does not exist." >&2
  echo "                 Copy examples/qa.config.example.yaml here and fill it in." >&2
  exit 2
fi

if ! python3 -c "" >/dev/null 2>&1; then
  echo "run-qa-workflow: python3 not found or not runnable — the result record is written by it." >&2
  exit 2
fi

declare -A cfg
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|\#*) continue ;; esac
  key="${line%%:*}"
  val="${line#*: }"
  cfg["$key"]="$val"
done < "$config"

cfg_get() {
  local v="${cfg[$1]:-}"
  if [ -z "$v" ] && [ $# -ge 2 ]; then echo "$2"; else echo "$v"; fi
}

verdict_from_rc() {
  # Mirrors the harness's own exit-code contract (harness.py): 0 is the only pass. Anything the
  # harness or the E2E runner could not resolve is BLOCKED here, never silently a PASS or folded
  # into FAIL — a check that could not run and a check that ran and found a defect are different
  # findings and must never look the same in this record.
  case "$1" in
    0) echo PASS ;;
    1) echo FAIL ;;
    *) echo BLOCKED ;;
  esac
}

run_harness_stage() {
  local cmd; cmd="$(cfg_get harness.runCommand)"
  if [ -z "$cmd" ]; then
    echo "run-qa-workflow: qa.config.yaml has no harness.runCommand." >&2
    exit 2
  fi
  local out; out="$(bash -c "$cmd" 2>&1)"; local rc=$?
  HARNESS_VERDICT="$(verdict_from_rc "$rc")"
  HARNESS_EVIDENCE="tools/qa/evidence/latest.md"
  HARNESS_DETAIL="$(printf '%s' "$out" | tail -1 | cut -c1-200)"
}

# worst-of, same ordering every other rollup in this kit uses (FAIL > BLOCKED > PENDING > PASS,
# PENDING never appearing here since no stage-level input to this function is ever PENDING).
worst_of() {
  local best="PASS" best_rank=0 v rank
  for v in "$@"; do
    case "$v" in
      FAIL) rank=3 ;; BLOCKED) rank=2 ;; PASS) rank=0 ;; *) rank=3 ;;
    esac
    if [ "$rank" -ge "$best_rank" ]; then best="$v"; best_rank="$rank"; fi
  done
  echo "$best"
}

# The scripted (Playwright) engine — unchanged behaviour from before multi-engine support existed.
# Sets PW_VERDICT / PW_DETAIL; never touches E2E_* directly so run_e2e_stage can combine it with
# other engines' contributions.
run_playwright_engine() {
  local mode="$1" scope="$2"
  local e2e_path; e2e_path="$(cfg_get e2e.path .)"
  local cmd
  if [ "$mode" = ticket ]; then
    local template; template="$(cfg_get e2e.ticketCommand)"
    cmd="${template//\{ticketId\}/$scope}"
  else
    cmd="$(cfg_get e2e.regressionCommand)"
  fi
  if [ -z "$cmd" ]; then
    echo "run-qa-workflow: qa.config.yaml has no e2e.$([ "$mode" = ticket ] && echo ticketCommand || echo regressionCommand)." >&2
    exit 2
  fi
  local out; out="$(cd "$root/$e2e_path" && bash -c "$cmd" 2>&1)"; local rc=$?
  PW_VERDICT="$(verdict_from_rc "$rc")"

  # ZERO TESTS EXECUTED IS NEITHER A PASS NOR A FAIL — IT IS BLOCKED, and the runner's own exit code
  # cannot be trusted to say so either way. Validated against this project's real Playwright suite:
  # with no role credentials configured, its fallback project matches no test files. That specific
  # runner exits 1 in that case (so the naive mapping lands on FAIL, not the false PASS a different
  # runner version could produce — Playwright's own history includes both behaviours depending on
  # version/config). Neither FAIL nor PASS is correct: nothing was checked, so nothing failed and
  # nothing passed. The external reason (missing credentials, here) is exactly BLOCKED's definition.
  #
  # This is the same output-scanning idiom tools/qa/run-qa.sh already uses to catch a crashed gate
  # exiting nonzero and being mis-read as VIOLATED: a heuristic, stdlib/no-dependency, and named as a
  # heuristic rather than a guarantee. It overrides PASS or FAIL alike, and it cannot see every
  # runner's zero-tests phrasing — a project whose runner says something this list does not recognise
  # should make its `e2e.*Command` wrapper detect and surface that condition itself.
  case "$out" in
    *"No tests found"*|*"0 tests"*|*"Ran 0 tests"*|*"no tests ran"*|*"0 passed, 0 failed"*|*"0 examples, 0 failures"*)
      if [ "$PW_VERDICT" != BLOCKED ]; then
        out="$out
(run-qa-workflow: overriding $PW_VERDICT -> BLOCKED — the runner reported zero tests executed. A
zero-test run has verified nothing and must never be recorded as a pass OR a fail.)"
        PW_VERDICT=BLOCKED
      fi
      ;;
  esac

  PW_DETAIL="$(printf '%s' "$out" | tail -1 | cut -c1-200)"
}

run_e2e_stage() {
  local mode="$1" scope="$2"
  local ev_root; ev_root="$(cfg_get evidence.root reports/qa-workflow)"
  E2E_EVIDENCE="$ev_root/$mode/$scope"
  local scope_dir="$root/$E2E_EVIDENCE"
  mkdir -p "$scope_dir/results"

  local engines; engines="$(cfg_get e2e.engines playwright)"
  local verdicts=() details=()
  E2E_CASE_FILES=()

  case ",$engines," in
    *,playwright,*)
      run_playwright_engine "$mode" "$scope"
      verdicts+=("$PW_VERDICT"); details+=("[playwright] $PW_DETAIL")
      ;;
  esac

  case ",$engines," in
    *,claude-in-chrome,*)
      # Agent-driven — never invoked here (there is nothing to shell out to; see
      # core/e2e-engine-contract.md §8). Only aggregate what a prior qa-browser-explore session
      # already wrote under $scope_dir/results/.
      # Deliberately NOT under results/ — aggregate-e2e-results.py scans results/*.json for genuine
      # case files, and pathlib's glob (unlike a shell glob) does not skip dotfiles, so a summary file
      # left inside that directory would be re-ingested as a bogus case on the next run.
      local cases_file="$scope_dir/.cases-claude-in-chrome.json"
      local agg_out agg_rc
      agg_out="$(python3 "$(dirname "${BASH_SOURCE[0]}")/aggregate-e2e-results.py" "$scope_dir" claude-in-chrome --emit-cases "$cases_file" 2>&1)"
      agg_rc=$?
      if [ "$agg_rc" -ne 0 ]; then
        echo "run-qa-workflow: aggregate-e2e-results.py could not aggregate the claude-in-chrome engine:" >&2
        echo "$agg_out" >&2
        exit 2
      fi
      local cic_verdict cic_detail
      cic_verdict="$(printf '%s\n' "$agg_out" | sed -n 's/^VERDICT=//p')"
      cic_detail="$(printf '%s\n' "$agg_out" | sed -n 's/^DETAIL=//p')"
      verdicts+=("${cic_verdict:-BLOCKED}"); details+=("[claude-in-chrome] ${cic_detail:-aggregator produced no verdict}")
      E2E_CASE_FILES+=("$cases_file")
      ;;
  esac

  if [ "${#verdicts[@]}" -eq 0 ]; then
    echo "run-qa-workflow: e2e.engines ('$engines') named no recognized engine — expected 'playwright' and/or 'claude-in-chrome'." >&2
    exit 2
  fi

  E2E_VERDICT="$(worst_of "${verdicts[@]:-}")"
  local IFS='; '; E2E_DETAIL="${details[*]:-}"; unset IFS
}

write_result() {
  local workflow="$1" scope="$2"
  local ev_root; ev_root="$(cfg_get evidence.root reports/qa-workflow)"
  local out_dir="$root/$ev_root/$workflow/$scope"
  mkdir -p "$out_dir"
  local out_path="$out_dir/result.json"
  local commit; commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

  # E2E_CASE_FILES (set by run_e2e_stage) may hold zero or more paths to JSON arrays of case results,
  # one per agent-driven engine that ran. Newline-joined so write_result's python heredoc can merge
  # them into stages.e2e.cases without needing to parse a bash array through an env var.
  local case_files_joined=""
  if [ "${#E2E_CASE_FILES[@]}" -gt 0 ]; then
    case_files_joined="$(printf '%s\n' "${E2E_CASE_FILES[@]:-}")"
  fi

  WORKFLOW="$workflow" SCOPE_ID="$scope" COMMIT="$commit" \
  HARNESS_VERDICT="$HARNESS_VERDICT" HARNESS_EVIDENCE="$HARNESS_EVIDENCE" HARNESS_DETAIL="$HARNESS_DETAIL" \
  E2E_VERDICT="$E2E_VERDICT" E2E_EVIDENCE="$E2E_EVIDENCE" E2E_DETAIL="$E2E_DETAIL" \
  E2E_CASE_FILES="$case_files_joined" \
  OUT_PATH="$out_path" \
  python3 - <<'PY'
import json, os, datetime
from pathlib import Path

def load_cases() -> list:
    merged = []
    for line in os.environ.get("E2E_CASE_FILES", "").splitlines():
        p = Path(line.strip())
        if not line.strip() or not p.is_file():
            continue
        try:
            merged.extend(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return merged

def rollup(*verdicts):
    order = {"FAIL": 3, "BLOCKED": 2, "PENDING": 1, "PASS": 0}
    worst = max(verdicts, key=lambda v: order.get(v, 3))
    return worst

result = {
    "schemaVersion": "1.0",
    "workflow": os.environ["WORKFLOW"],
    "scope": {
        "id": os.environ["SCOPE_ID"],
        "ticketUrl": os.environ.get("TICKET_URL") or None,
        "prUrl": os.environ.get("PR_URL") or None,
    },
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "commit": os.environ.get("COMMIT") or None,
    "stages": {
        "harness": {
            "verdict": os.environ["HARNESS_VERDICT"],
            "evidencePath": os.environ["HARNESS_EVIDENCE"],
            "detail": os.environ.get("HARNESS_DETAIL", ""),
        },
        "e2e": (lambda cases: {
            "verdict": os.environ["E2E_VERDICT"],
            "evidencePath": os.environ["E2E_EVIDENCE"],
            "detail": os.environ.get("E2E_DETAIL", ""),
            **({"cases": cases} if cases else {}),
        })(load_cases()),
        "qaVerification": {
            "verdict": "PENDING",
            "reviewer": None,
            "notes": None,
            "recordedAt": None,
        },
    },
    "finalResult": rollup(os.environ["HARNESS_VERDICT"], os.environ["E2E_VERDICT"], "PENDING"),
}

path = os.environ["OUT_PATH"]
with open(path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(f"result -> {path}")
print(f"finalResult: {result['finalResult']} (qaVerification still PENDING — run 'verify' to close it out)")
PY
  self_check
}

record_verification() {
  local path="$1" verdict="$2" reviewer="$3" notes="${4:-}"
  case "$verdict" in PASS|FAIL|BLOCKED) ;; *)
    echo "run-qa-workflow: verify verdict must be PASS, FAIL or BLOCKED — got '$verdict'." >&2
    exit 2 ;;
  esac
  if [ ! -f "$path" ]; then
    echo "run-qa-workflow: $path does not exist." >&2
    exit 2
  fi
  RESULT_PATH="$path" VERDICT="$verdict" REVIEWER="$reviewer" NOTES="$notes" python3 - <<'PY'
import json, os, datetime

def rollup(*verdicts):
    order = {"FAIL": 3, "BLOCKED": 2, "PENDING": 1, "PASS": 0}
    return max(verdicts, key=lambda v: order.get(v, 3))

path = os.environ["RESULT_PATH"]
with open(path, encoding="utf-8") as f:
    result = json.load(f)

result["stages"]["qaVerification"] = {
    "verdict": os.environ["VERDICT"],
    "reviewer": os.environ["REVIEWER"],
    "notes": os.environ.get("NOTES") or None,
    "recordedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
result["finalResult"] = rollup(
    result["stages"]["harness"]["verdict"],
    result["stages"]["e2e"]["verdict"],
    result["stages"]["qaVerification"]["verdict"],
)

with open(path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(f"result -> {path}")
print(f"finalResult: {result['finalResult']}")
if result["finalResult"] != "PASS":
    print("FLOOR NOT GREEN — see the record above.")
PY
  self_check
}

self_check() {
  # Every write runs the result-contract gate on itself, so a malformed record is caught the moment
  # it is produced rather than at the next unrelated CI run.
  #
  # The checker's exit code must reach THIS function's caller. Printing its output and unconditionally
  # `return 0`-ing afterwards means a caller reading this script's own exit code sees success even
  # when the record the script just wrote failed its own honesty check — a CI pipeline gating on this
  # script's exit status would show green while the evidence it just produced says red.
  local checker; checker="$(dirname "${BASH_SOURCE[0]}")/check_result_contract.py"
  [ -f "$checker" ] || return 0
  local out; local rc
  out="$(python3 "$checker" 2>&1)"; rc=$?
  echo "$out"
  if [ "$rc" -ne 0 ]; then
    echo "" >&2
    echo "run-qa-workflow: self-check FAILED (check_result_contract.py exit $rc) — the record just" >&2
    echo "                 written does not honestly reflect its own inputs. See output above." >&2
    return 1
  fi
  return 0
}

mode="${1:-}"
case "$mode" in
  ticket)
    ticket="${2:-}"
    [ -n "$ticket" ] || { echo "usage: run-qa-workflow.sh ticket <TICKET-ID>" >&2; exit 2; }
    run_harness_stage
    run_e2e_stage ticket "$ticket"
    write_result ticket "$ticket" || exit 1
    ;;
  regression)
    scope="${2:-full}"
    run_harness_stage
    run_e2e_stage regression "$scope"
    write_result regression "$scope" || exit 1
    ;;
  verify)
    result_path="${2:-}"; verdict="${3:-}"; reviewer="${4:-}"; notes="${5:-}"
    [ -n "$result_path" ] && [ -n "$verdict" ] && [ -n "$reviewer" ] || {
      echo "usage: run-qa-workflow.sh verify <result.json> <PASS|FAIL|BLOCKED> <reviewer> [notes]" >&2
      exit 2
    }
    record_verification "$result_path" "$verdict" "$reviewer" "$notes" || exit 1
    ;;
  *)
    echo "usage: run-qa-workflow.sh ticket <TICKET-ID> | regression [scope-id] | verify <result.json> <verdict> <reviewer> [notes]" >&2
    exit 2
    ;;
esac
