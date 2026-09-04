#!/usr/bin/env python3
"""Validate every result.json under evidence.root against core/result.schema.json's shape and rollup
rule.

WHAT THIS GUARDS AGAINST. `run-qa-workflow.sh` computes `finalResult` itself, honestly, at write time —
but a hand-edited result file (someone "fixing" a FAIL to a PASS after the fact, or filling PENDING in
early to make a dashboard look green) produces a file that is syntactically identical to a real one. This
gate recomputes the rollup independently and reports a mismatch as VIOLATED — the one check in this kit
whose entire job is catching a result record that lies about its own inputs.

EXIT CODES: see harness.py, imported from the sibling Agent Development Harness installation. 2 is not
a pass. 3 (INCOMPLETE) is used here for a directory that holds no result.json at all yet — that is a
legitimate pre-first-run state, not a violation, but it is also not something this gate verified.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gates"))
try:
    from harness import CANNOT_RUN, INCOMPLETE, VERIFIED, VIOLATED, repo_root, report  # noqa: E402
except ImportError:
    print(
        "check_result_contract: could not import tools/gates/harness.py. This kit is built AROUND the "
        "Agent Development Harness and expects it installed first.",
        file=sys.stderr,
    )
    sys.exit(2)

ROOT = repo_root()

# ── Tailor if your qa.config.yaml points evidence.root somewhere else ───────────────────────────────
EVIDENCE_ROOT = Path("reports/qa-workflow")

REQUIRED_TOP = {"schemaVersion", "workflow", "scope", "generatedAt", "stages", "finalResult"}
REQUIRED_STAGE_KEYS = {"harness": {"verdict", "evidencePath"}, "e2e": {"verdict", "evidencePath"}}
STAGE_VERDICTS = {"PASS", "FAIL", "BLOCKED"}
E2E_VERDICTS = {"PASS", "FAIL", "BLOCKED", "CANNOT_AUTOMATE", "NOT_EXECUTED"}
VERIFICATION_VERDICTS = {"PASS", "FAIL", "BLOCKED", "PENDING"}
FINAL_VERDICTS = {"PASS", "FAIL", "BLOCKED", "PENDING"}
ROLLUP_ORDER = {"FAIL": 3, "BLOCKED": 2, "PENDING": 1, "PASS": 0}

# E2E's five-word vocabulary collapses to the three-word stage vocabulary for rollup purposes: a case
# marked CANNOT_AUTOMATE or NOT_EXECUTED did not fail, but it also did not verify anything, so it must
# not silently behave like PASS in the rollup either.
E2E_TO_ROLLUP = {"CANNOT_AUTOMATE": "BLOCKED", "NOT_EXECUTED": "BLOCKED"}


def rollup(*verdicts: str) -> str:
    return max(verdicts, key=lambda v: ROLLUP_ORDER.get(v, 3))


def validate_one(path: Path) -> list[str]:
    rel = path.relative_to(ROOT)
    violations: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{rel}: could not be read/parsed as JSON: {exc}"]

    missing_top = REQUIRED_TOP - data.keys()
    if missing_top:
        violations.append(f"{rel}: missing top-level field(s) {sorted(missing_top)}")
        return violations  # nothing further is safe to inspect

    stages = data.get("stages", {})
    for name, required in REQUIRED_STAGE_KEYS.items():
        stage = stages.get(name)
        if not isinstance(stage, dict) or required - stage.keys():
            violations.append(f"{rel}: stages.{name} missing required field(s) {sorted(required)}")
            continue
        allowed = E2E_VERDICTS if name == "e2e" else STAGE_VERDICTS
        if stage["verdict"] not in allowed:
            violations.append(f"{rel}: stages.{name}.verdict {stage['verdict']!r} not one of {sorted(allowed)}")

    verification = stages.get("qaVerification")
    if not isinstance(verification, dict) or "verdict" not in verification:
        violations.append(f"{rel}: stages.qaVerification missing 'verdict'")
    elif verification["verdict"] not in VERIFICATION_VERDICTS:
        violations.append(
            f"{rel}: stages.qaVerification.verdict {verification['verdict']!r} not one of "
            f"{sorted(VERIFICATION_VERDICTS)}"
        )
    elif verification["verdict"] != "PENDING" and not verification.get("reviewer"):
        violations.append(
            f"{rel}: stages.qaVerification.verdict is {verification['verdict']!r} but 'reviewer' is "
            "empty. A verdict with no recorded independent reviewer cannot be told apart from one the "
            "authoring agent wrote for itself — the exact failure this stage exists to prevent."
        )

    if violations:
        return violations

    final = data.get("finalResult")
    if final not in FINAL_VERDICTS:
        return [f"{rel}: finalResult {final!r} not one of {sorted(FINAL_VERDICTS)}"]

    harness_v = stages["harness"]["verdict"]
    e2e_v = E2E_TO_ROLLUP.get(stages["e2e"]["verdict"], stages["e2e"]["verdict"])
    verification_v = verification["verdict"]
    expected = rollup(harness_v, e2e_v, verification_v)
    if final != expected:
        violations.append(
            f"{rel}: finalResult is {final!r} but the stage verdicts "
            f"(harness={harness_v}, e2e={stages['e2e']['verdict']}, qaVerification={verification_v}) "
            f"roll up to {expected!r}. A result record whose headline verdict disagrees with its own "
            "inputs is worse than a missing record — it looks trustworthy and is not."
        )

    return violations


def main() -> int:
    search_root = ROOT / EVIDENCE_ROOT
    if not search_root.is_dir():
        return report(
            "qa workflow result contract",
            INCOMPLETE,
            unproven=[f"{EVIDENCE_ROOT} does not exist yet — no QA workflow run has produced a result."],
            note="Legitimate before the first run. Not a pass: nothing was verified.",
        )

    files = sorted(search_root.rglob("result.json"))
    if not files:
        return report(
            "qa workflow result contract",
            INCOMPLETE,
            unproven=[f"{EVIDENCE_ROOT} exists but holds no result.json yet."],
            note="Legitimate before the first run. Not a pass: nothing was verified.",
        )

    violations: list[str] = []
    for f in files:
        violations.extend(validate_one(f))

    if violations:
        return report("qa workflow result contract", VIOLATED, violations=violations)

    return report(
        "qa workflow result contract",
        VERIFIED,
        verified=[f"{len(files)} result record(s), every one well-formed and honestly rolled up"],
    )


if __name__ == "__main__":
    sys.exit(main())
