#!/usr/bin/env python3
"""Shared files copied in from an upstream repository still match what was copied.

THE PROBLEM THIS SOLVES.

Once you have more than one repository, some things want to be shared — review agent definitions,
lint configs, CI workflows, gates like these. The clean answer is to publish them as a versioned
package and have each repo consume it. Teams rarely start there, because publishing infrastructure is
work and copying a file takes seconds.

So the files get copied. And then **the copies rot silently.** Someone improves the original; the
copies keep the old behaviour; nothing anywhere reports it. The failure is quiet, and it lands in
exactly the files you would least like to be stale — the ones that decide how code gets reviewed.

Measured on the project this kit came from: an upstream change added four lines to a shared review
skill, and **three downstream copies went stale the same day**, with nothing noticing.

This gate does not fix that. It makes it **visible**, which is what you can actually have before the
publishing question is settled.

WHAT IT CATCHES, AND THE HALF IT CANNOT — read both, because the limit matters.

  CATCHES — a shared file edited HERE instead of upstream. That is the failure this repo can cause,
  and the one that quietly forks a shared asset: the next person to compare finds two versions and no
  record of which is authoritative.

  CANNOT CATCH — upstream moving ahead. Detecting that needs this repo to read upstream's tree, which
  needs network access and a credential. And the upstream repo usually cannot push the check either,
  because a well-structured upstream does not depend on its consumers.

  **So a pass means "unchanged since copied". It does NOT mean "up to date."** The gate says so in its
  own output, because a green check that gets over-read is worse than no check.

TWO CLASSES OF FILE, because they admit different checks:

  verbatim  — byte-identical to upstream. Checked by hash. Kept byte-identical ON PURPOSE rather than
              locally "improved": a file adapted for local taste is a file nobody can diff, and it
              forks quietly. Put local context in a document, never in the file.
  templated — differs from upstream by a known rule (a repo name, an org slug). A hash is meaningless,
              so instead the check confirms the substitution is COMPLETE — no upstream marker survives.
              A half-substituted config points tooling at the wrong repository, which is worse than an
              obviously missing one because it looks configured.

SETUP: create `tools/gates/vendored.json` — see `examples/vendored.json` in this kit. If the file is
absent this gate reports NOT APPLICABLE and passes, because a single-repo project has nothing to
share and should not be nagged.

EXIT CODES: 0 verified · 1 drifted or missing · 2 could not run.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import CANNOT_RUN, VERIFIED, VIOLATED, repo_root, report  # noqa: E402

ROOT = repo_root()
MANIFEST = Path("tools/gates/vendored.json")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    path = ROOT / MANIFEST
    if not path.is_file():
        return report(
            "vendored drift",
            VERIFIED,
            verified=[
                f"NOT APPLICABLE — no {MANIFEST}, so this repo declares no files copied from upstream."
            ],
            note=(
                "A single-repo project has nothing to share and nothing to drift. Create the manifest "
                "when you first copy a shared file in — see examples/vendored.json. THIS IS THE "
                "TRIGGER: the check starts enforcing the moment the manifest exists."
            ),
        )

    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return report(
            "vendored drift",
            CANNOT_RUN,
            violations=[f"{MANIFEST} is unreadable: {exc}. Nothing can be compared."],
        )

    upstream = m.get("upstream", "(unrecorded)")
    revision = m.get("revision", "(unrecorded)")
    marker = m.get("upstream_marker")
    drift: list[str] = []
    checked = 0

    for rel, expected in sorted(m.get("verbatim", {}).items()):
        # A leading underscore marks a human annotation (`_note`, `_comment`), not a file row — the
        # same JSON-comment convention examples/vendored.json uses. Iterating it as a path is how the
        # kit's own template used to crash this gate.
        if rel.startswith("_"):
            continue
        f = ROOT / rel
        if not f.is_file():
            drift.append(
                f"MISSING — {rel}\n"
                "      The manifest says this repo vendors it and it is not here. Either it was deleted\n"
                "      (remove its manifest row and say why, in the same change) or a copy is incomplete."
            )
            continue
        checked += 1
        actual = sha256(f)
        if actual != expected:
            drift.append(
                f"DRIFTED LOCALLY — {rel}\n"
                f"      copied:  {expected[:16]}…\n"
                f"      here:    {actual[:16]}…\n"
                "      This file was changed in this repo. A shared asset is authored upstream and copied\n"
                "      here unchanged, so a local edit forks it — the next person to compare finds two\n"
                "      versions and no record of which is authoritative.\n"
                "      FIX: land the change UPSTREAM, re-copy, update the manifest hash. Do NOT keep the\n"
                "      local edit and re-hash it, which is how a fork becomes permanent."
            )

    for rel, spec in sorted(m.get("templated", {}).items()):
        if rel.startswith("_"):
            continue
        if not isinstance(spec, dict):
            return report(
                "vendored drift",
                CANNOT_RUN,
                violations=[
                    f"{MANIFEST}: templated entry {rel!r} maps to a {type(spec).__name__}, not an "
                    "object.\n"
                    "      Each templated entry must be `{\"rule\": \"…\"}`. The manifest cannot be "
                    "interpreted,\n"
                    "      so this reaches no verdict — a malformed manifest is a could-not-run, never a "
                    "pass."
                ],
            )
        f = ROOT / rel
        if not f.is_file():
            drift.append(f"MISSING — {rel} (templated: {spec.get('rule', '?')})")
            continue
        checked += 1
        if not marker:
            drift.append(
                f"{rel} is declared templated, but the manifest sets no `upstream_marker`, so there is\n"
                "      nothing to check the substitution against. Add the string that must NOT survive."
            )
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if marker in text:
            drift.append(
                f"TEMPLATE HALF-SUBSTITUTED — {rel}\n"
                f"      {text.count(marker)} surviving reference(s) to {marker!r}. Rule: {spec.get('rule', '?')}\n"
                "      A partly-substituted file points its tooling at the wrong repository, which is worse\n"
                "      than an obviously missing one because it looks configured."
            )

    if drift:
        return report(
            "vendored drift",
            VIOLATED,
            violations=drift,
            note=(
                f"Manifest provenance: {upstream} @ {str(revision)[:12]}. This gate detects LOCAL "
                "divergence only — a pass means 'unchanged since copied', never 'up to date with "
                "upstream'."
            ),
        )

    return report(
        "vendored drift",
        VERIFIED,
        verified=[f"{checked} file(s) unchanged since copied from {upstream} @ {str(revision)[:12]}"],
        note=(
            "This proves NO LOCAL DIVERGENCE. It does NOT prove these files are up to date with "
            "upstream — that needs network access and a credential, and is the direction that causes "
            "real staleness. Do not read this green as 'current'."
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
