#!/usr/bin/env python3
"""Recommend which model tier (fast/standard/deep) a task belongs in — advisory only.

WHY THIS EXISTS. See core/model-router-contract.md for the full decision order and rationale. Short
version: harness/E2E stages are shell commands with no token cost to route; the agentic reasoning around
them (interpreting output, authoring E2E coverage, QA Verification's evidence-vs-criteria reconciliation)
is where routing a task to a cheaper or more capable model actually changes what a QA cycle costs. This
script never calls a model, never switches a running session's model, and is never invoked by
tools/run-qa-workflow.sh — it is a standalone recommendation a human or a skill session runs by hand,
before starting the reasoning-heavy part of a step.

NO THIRD-PARTY DEPENDENCIES, same reasoning as every other tool in this kit.

USAGE
  route-task.py <task-type> [<file> ...] [--note <text>]

<task-type> must be one of core/model-router-contract.md §3's fixed task types. Files are repo-relative
paths already touched or about to be touched. --note is free text for keyword risk-matching before any
file exists yet (e.g. routing a ticket about auth before a single file has been opened).

Prints:
  TIER=fast|standard|deep
  AGENT=<router.tiers.<tier>.agent from qa.config.yaml>
  REASON=<one-line explanation of what decided it>

Exit 0 whenever a tier was produced — the fail-safe 'deep' default (missing/unrecognized task type) is a
produced decision, not a script failure. Exit 2 only for a genuine can't-run condition: bad arguments,
qa.config.yaml missing, router.enabled not 'true', or router.enabled true but a tier's agent mapping is
unset — routing cannot honestly recommend an agent it was never told the name of.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gates"))
try:
    from harness import repo_root  # noqa: E402
except ImportError:
    print(
        "route-task: could not import tools/gates/harness.py. This kit is built AROUND the Agent "
        "Development Harness and expects it installed first — see agent-harness-starter's README.",
        file=sys.stderr,
    )
    sys.exit(2)

# Fixed per core/model-router-contract.md §3 — not project-configurable. A project needing a task type
# this table does not cover is a contract growth, not a per-project override.
TASK_TYPE_BASELINE = {
    "result-read": "fast",
    "unit-property-mutation-analysis": "standard",
    "e2e-authoring-debugging": "standard",
    "bug-investigation": "deep",
    "architecture-security-review": "deep",
}

TIER_RANK = {"fast": 0, "standard": 1, "deep": 2}

# Tailor this if a project's 'standard' tasks routinely touch more files without added risk — see
# core/model-router-contract.md §4 rule 4. This is the ONLY place file count enters the decision, and
# only as a tie-breaker on an already-'standard' tier, never as a first cause.
LARGE_FILE_COUNT_THRESHOLD = 15


def parse_flat_yaml(text: str) -> dict[str, str]:
    """Same parser tools/run-qa-workflow.sh and check_qa_config.py use: one `key: value` per line."""
    cfg: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        cfg[key.strip()] = value.strip()
    return cfg


def top_level_module(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if parts else path


def check_risk(files: list[str], note: str, risk_paths: list[str], risk_keywords: list[str]) -> str | None:
    for f in files:
        for pattern in risk_paths:
            if fnmatch.fnmatch(f, pattern):
                return f"riskHit: file '{f}' matched router.riskPaths glob '{pattern}'"
    haystack = " ".join(files + [note]).lower()
    for kw in risk_keywords:
        kw = kw.strip().lower()
        if kw and kw in haystack:
            return f"riskHit: '{kw}' (router.riskKeywords) found in touched files/note"
    return None


def decide(task_type: str, files: list[str], note: str, risk_paths: list[str], risk_keywords: list[str]) -> tuple[str, str]:
    risk_reason = check_risk(files, note, risk_paths, risk_keywords)
    if risk_reason:
        return "deep", risk_reason

    if task_type not in TASK_TYPE_BASELINE:
        return "deep", (
            f"fail-safe default: taskType '{task_type}' is not one of "
            f"{sorted(TASK_TYPE_BASELINE)} — an unrecognized task cannot be honestly called cheap"
        )

    tier = TASK_TYPE_BASELINE[task_type]
    reason = f"taskType '{task_type}' baseline tier: {tier}"

    modules = {top_level_module(f) for f in files}
    if tier == "standard" and len(modules) > 1:
        tier = "deep"
        reason = f"{reason}; escalated to deep — files span {len(modules)} modules ({sorted(modules)})"

    if tier == "standard" and len(files) >= LARGE_FILE_COUNT_THRESHOLD:
        tier = "deep"
        reason = f"{reason}; escalated to deep — {len(files)} files >= LARGE_FILE_COUNT_THRESHOLD ({LARGE_FILE_COUNT_THRESHOLD})"

    return tier, reason


def main() -> int:
    args = sys.argv[1:]
    note = ""
    if "--note" in args:
        i = args.index("--note")
        try:
            note = args[i + 1]
        except IndexError:
            print("route-task: --note requires a text argument.", file=sys.stderr)
            return 2
        del args[i : i + 2]

    if not args:
        print("usage: route-task.py <task-type> [<file> ...] [--note <text>]", file=sys.stderr)
        return 2

    task_type, files = args[0], args[1:]

    root = repo_root()
    config_path = root / "qa.config.yaml"
    if not config_path.is_file():
        print(f"route-task: {config_path} does not exist.", file=sys.stderr)
        return 2

    cfg = parse_flat_yaml(config_path.read_text(encoding="utf-8"))

    if cfg.get("router.enabled", "").lower() != "true":
        print(
            "route-task: router.enabled is not 'true' in qa.config.yaml — routing is opt-in. "
            "See core/model-router-contract.md §6.",
            file=sys.stderr,
        )
        return 2

    risk_paths = [p.strip() for p in cfg.get("router.riskPaths", "").split(",") if p.strip()]
    risk_keywords = [k.strip() for k in cfg.get("router.riskKeywords", "").split(",") if k.strip()]

    tier, reason = decide(task_type, files, note, risk_paths, risk_keywords)

    agent_key = f"router.tiers.{tier}.agent"
    agent = cfg.get(agent_key, "")
    if not agent:
        print(
            f"route-task: router.enabled is 'true' but {agent_key} is unset in qa.config.yaml — "
            "cannot recommend an agent for a tier that was never mapped to one.",
            file=sys.stderr,
        )
        return 2

    print(f"TIER={tier}")
    print(f"AGENT={agent}")
    print(f"REASON={reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
