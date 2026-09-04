#!/usr/bin/env python3
"""Roll up one engine's case-result files into a single stage-level verdict.

WHY THIS EXISTS. A scripted engine (Playwright) reports a verdict via its process exit code —
tools/run-qa-workflow.sh reads that directly and never needs this script. An agent-driven engine
(Claude in Chrome) has no exit code: there is no process to invoke and wait on, only a session that
writes results/<CASE-ID>.json files as it goes, per core/case-result.schema.json. This script is how
those files become a verdict, without tools/run-qa-workflow.sh needing to know anything engine-specific.

NO THIRD-PARTY DEPENDENCIES, same reasoning as check_qa_config.py: this is called from a bash script
that itself has none, and a JSON-Schema library is not required to check a handful of required keys.

USAGE
  aggregate-e2e-results.py <scope-evidence-dir> <engine-name> [--emit-cases <path>]

<scope-evidence-dir> is <evidence.root>/<workflow>/<scope> (case files live under its results/
subdirectory). Prints three lines to stdout:

  VERDICT=PASS|FAIL|BLOCKED
  DETAIL=<one-line summary>
  CASES=<n>

Exit 0 whenever a verdict was produced — BLOCKED for "zero matching case files" is a produced verdict,
not a script failure; a caller must not treat this script's own exit code as the stage verdict, only the
VERDICT= line. Exit 2 only for a genuine can't-run condition: bad arguments, <scope-evidence-dir> missing
entirely, or a case-result file that cannot even be parsed as JSON (a malformed file is worse than a
missing one and must not be silently skipped).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CASE_VERDICTS = {"PASS", "FAIL", "BLOCKED", "CANNOT_AUTOMATE", "NOT_EXECUTED"}
# Mirrors check_result_contract.py's E2E_TO_ROLLUP: a case that could not be automated or was
# intentionally skipped did not fail, but it also verified nothing, so it must not behave like PASS.
ROLLUP_ORDER = {"FAIL": 3, "BLOCKED": 2, "CANNOT_AUTOMATE": 2, "NOT_EXECUTED": 2, "PASS": 0}
REQUIRED_KEYS = {"id", "engine", "verdict", "recordedAt"}


def worst_of(verdicts: list[str]) -> str:
    if not verdicts:
        return "BLOCKED"
    worst = max(verdicts, key=lambda v: ROLLUP_ORDER.get(v, 3))
    return "BLOCKED" if worst in ("CANNOT_AUTOMATE", "NOT_EXECUTED") else worst


def main() -> int:
    args = sys.argv[1:]
    emit_cases: Path | None = None
    if "--emit-cases" in args:
        i = args.index("--emit-cases")
        try:
            emit_cases = Path(args[i + 1])
        except IndexError:
            print("aggregate-e2e-results: --emit-cases requires a path argument.", file=sys.stderr)
            return 2
        del args[i : i + 2]

    if len(args) != 2:
        print(
            "usage: aggregate-e2e-results.py <scope-evidence-dir> <engine-name> [--emit-cases <path>]",
            file=sys.stderr,
        )
        return 2

    scope_dir = Path(args[0])
    engine = args[1]

    if not scope_dir.is_dir():
        print(f"aggregate-e2e-results: {scope_dir} does not exist.", file=sys.stderr)
        return 2

    results_dir = scope_dir / "results"
    # pathlib's glob, unlike a shell glob, does not skip dotfiles for "*" — exclude them explicitly so
    # a hidden summary/cache file dropped in this directory is never mistaken for a real case result.
    case_files = (
        sorted(f for f in results_dir.glob("*.json") if not f.name.startswith("."))
        if results_dir.is_dir()
        else []
    )

    cases: list[dict] = []
    for f in case_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"aggregate-e2e-results: {f} could not be parsed as JSON: {exc}", file=sys.stderr)
            return 2
        if data.get("engine") != engine:
            continue
        missing = REQUIRED_KEYS - data.keys()
        if missing:
            print(
                f"aggregate-e2e-results: {f} is missing required field(s) {sorted(missing)} — "
                "see core/case-result.schema.json.",
                file=sys.stderr,
            )
            return 2
        if data["verdict"] not in CASE_VERDICTS:
            print(
                f"aggregate-e2e-results: {f} has verdict {data['verdict']!r}, not one of "
                f"{sorted(CASE_VERDICTS)}.",
                file=sys.stderr,
            )
            return 2
        cases.append(data)

    if not cases:
        verdict = "BLOCKED"
        detail = (
            f"no '{engine}' case results found under {results_dir} — either no session has run for "
            "this scope yet, or the session recorded nothing."
        )
    else:
        verdict = worst_of([c["verdict"] for c in cases])
        detail = f"{len(cases)} '{engine}' case(s) rolled up to {verdict}"

    print(f"VERDICT={verdict}")
    print(f"DETAIL={detail}")
    print(f"CASES={len(cases)}")

    if emit_cases is not None:
        emit_cases.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"id": c["id"], "verdict": c["verdict"], "engine": c["engine"], **({"note": c["note"]} if c.get("note") else {})}
            for c in cases
        ]
        emit_cases.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
