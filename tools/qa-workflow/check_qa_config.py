#!/usr/bin/env python3
"""Validate qa.config.yaml against qa.config.schema.json's required keys.

WHY A HAND-ROLLED CHECK AND NOT A JSON-SCHEMA LIBRARY. The harness this kit sits around holds every
gate to zero third-party dependencies, on purpose: a gate that needs `pip install` to run has acquired a
way to fail that has nothing to do with the property it checks, and that failure looks identical, from a
CI log, to the property being broken. `qa.config.yaml` is deliberately flat dotted-key text for the same
reason (see qa.config.schema.json's description) — flat text needs no library to validate either.

TAILOR, DO NOT WEAKEN. `REQUIRED_KEYS` and `CONFIG_PATH` are meant to be edited to fit a project that
needs a field this starter kit did not anticipate — that is what growing qa.config.schema.json is for.
Removing a key from this list because a project's file fails it is not tailoring, it is deleting the
finding.

EXIT CODES: see harness.py, imported from the sibling Agent Development Harness installation this kit
is built around. 2 (CANNOT_RUN) is not a pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

# This gate is meant to be copied to <project>/tools/qa-workflow/check_qa_config.py, so the Agent
# Development Harness's own gates live one directory over, at <project>/tools/gates/. Importing from
# there — rather than vendoring a second copy of the exit-code contract — is the literal meaning of
# "built around the harness": this kit adds no vocabulary of its own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gates"))
try:
    from harness import CANNOT_RUN, VERIFIED, VIOLATED, repo_root, report  # noqa: E402
except ImportError:
    print(
        "check_qa_config: could not import tools/gates/harness.py. This kit is built AROUND the Agent "
        "Development Harness and expects it installed first — see agent-harness-starter's README.",
        file=sys.stderr,
    )
    sys.exit(2)

ROOT = repo_root()

# ── Tailor to your project's copy of qa.config.schema.json if it has grown extra fields ────────────
CONFIG_PATH = Path("qa.config.yaml")
REQUIRED_KEYS = [
    "project.name",
    "project.techStack",
    "harness.runCommand",
    "e2e.path",
    "e2e.regressionCommand",
    "e2e.ticketCommand",
    "evidence.root",
]


def parse_flat_yaml(text: str) -> dict[str, str]:
    """The same parser run-qa-workflow.sh uses, in Python: one `key: value` per line."""
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


def main() -> int:
    path = ROOT / CONFIG_PATH
    if not path.is_file():
        return report(
            "qa.config.yaml",
            CANNOT_RUN,
            violations=[
                f"{CONFIG_PATH} does not exist, so neither QA workflow has anywhere to read project\n"
                "      config from. Copy examples/qa.config.example.yaml to the\n"
                "      repo root as qa.config.yaml and fill in every value."
            ],
        )

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return report(
            "qa.config.yaml",
            CANNOT_RUN,
            violations=[f"{CONFIG_PATH} exists but could not be read: {exc}."],
        )

    cfg = parse_flat_yaml(text)
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        return report(
            "qa.config.yaml",
            VIOLATED,
            violations=[
                f"missing or empty required key(s): {missing}.\n"
                "      See qa.config.schema.json for what each means."
            ],
        )

    nested = [k for k in cfg if "  " in k or k.endswith(".")]
    if nested:
        return report(
            "qa.config.yaml",
            VIOLATED,
            violations=[
                f"malformed key(s): {nested}. Keys must be flat dotted paths like 'harness.runCommand' "
                "— this file is deliberately not real YAML nesting; see qa.config.schema.json."
            ],
        )

    return report(
        "qa.config.yaml",
        VERIFIED,
        verified=[f"all {len(REQUIRED_KEYS)} required key(s) present: {sorted(REQUIRED_KEYS)}"],
    )


if __name__ == "__main__":
    sys.exit(main())
