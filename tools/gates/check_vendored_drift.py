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

A malformed manifest is a could-not-run, not a crash and not a pass. The structure is validated up
front (`manifest_structure_error`), so a manifest that is the wrong shape — top level not an object, a
`verbatim`/`templated` block not a map, a hash that is not a string, a templated value that is not an
object — reaches ONE clean exit-2 verdict instead of raising partway through and exiting 1, which would
read as a real drift. Annotation keys are tolerated only at the top level; inside the maps every key is
a real vendored path and is checked as one.

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


def _unprobeable(rel: str, exc: OSError) -> int:
    """A file the manifest lists but the OS refused to read (name too long, permission denied) is a
    could-not-run for that entry — never a silent pass and never a drift. Reported as CANNOT_RUN so a
    verdict is never invented for a file the gate could not actually look at.
    """
    return report(
        "vendored drift",
        CANNOT_RUN,
        violations=[
            f"{MANIFEST}: {rel!r} is declared vendored but could not be read: {exc}.\n"
            "      The gate reached no verdict for it. Fix the path or the permission and re-run."
        ],
    )


def manifest_structure_error(m: object) -> str | None:
    """Return a human message if the manifest is not a shape this gate can interpret, else None.

    Structure is validated ONCE, up front, so a malformed manifest becomes a single clean could-not-run
    rather than a crash partway through the comparison. Every shape rejected here would otherwise raise
    — `.items()` on a non-dict, `expected[:16]` on a non-string hash — and exit 1, which reads as a real
    drift when in truth nothing was compared. That is precisely the could-not-run-as-a-violation this
    whole harness exists to remove, so the gate must never do it to its own manifest.

    Note: annotation keys (`_comment`, `_note`) are only ignored at the TOP LEVEL, because the gate
    reads named top-level keys and never iterates them. Inside `verbatim`/`templated` every key is a
    real vendored path — there is no skip-by-name, so a genuinely vendored file called `_headers` or
    `__init__.py` is checked like any other rather than silently dropped.
    """
    if not isinstance(m, dict):
        return (f"{MANIFEST}: the top level is a {type(m).__name__}, not an object. A manifest is a "
                "JSON object with `verbatim` and/or `templated` maps.")
    for block in ("verbatim", "templated"):
        if block in m and not isinstance(m[block], dict):
            return (f"{MANIFEST}: `{block}` is a {type(m[block]).__name__}, not an object. It must map "
                    "each vendored path to its check.")
    for rel, expected in m.get("verbatim", {}).items():
        if not isinstance(expected, str):
            return (f"{MANIFEST}: verbatim entry {rel!r} maps to a {type(expected).__name__}, not a "
                    "string. Each verbatim entry is `\"path\": \"<sha256>\"`.")
    for rel, spec in m.get("templated", {}).items():
        if not isinstance(spec, dict):
            return (f"{MANIFEST}: templated entry {rel!r} maps to a {type(spec).__name__}, not an "
                    "object. Each templated entry is `\"path\": {\"rule\": \"…\"}`.")
    # Every path must stay inside the repository. An absolute path or one climbing out with `..` would
    # be hashed as-is, and the gate would then certify "this repo's vendored files are unchanged" while
    # having compared a file outside the repo — a verdict that is untrue about what it checked.
    for block in ("verbatim", "templated"):
        for rel in m.get(block, {}):
            if rel.startswith("/") or "\\" in rel or ".." in rel.split("/"):
                return (f"{MANIFEST}: entry {rel!r} is not a repo-relative path. Vendored paths must "
                        "stay inside the repository (no leading `/`, no `..`).")
    # Templated checking is impossible without a marker to search for, so it must be a non-empty string
    # whenever there are templated entries. Guarded here rather than at use, where `marker in text`
    # raises TypeError on a non-string (a crash reported as a drift).
    if m.get("templated") and not (isinstance(m.get("upstream_marker"), str) and m["upstream_marker"]):
        return (f"{MANIFEST}: `templated` entries need a non-empty string `upstream_marker` to check the "
                "substitution against, and none is set. Nothing can be compared.")
    return None


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

    structure_error = manifest_structure_error(m)
    if structure_error:
        return report("vendored drift", CANNOT_RUN, violations=[structure_error])

    upstream = m.get("upstream", "(unrecorded)")
    revision = m.get("revision", "(unrecorded)")
    marker = m.get("upstream_marker")
    drift: list[str] = []
    checked = 0

    for rel, expected in sorted(m.get("verbatim", {}).items()):
        f = ROOT / rel
        try:
            present = f.is_file()
            actual = sha256(f) if present else None
        except OSError as exc:
            return _unprobeable(rel, exc)
        if not present:
            drift.append(
                f"MISSING — {rel}\n"
                "      The manifest says this repo vendors it and it is not here. Either it was deleted\n"
                "      (remove its manifest row and say why, in the same change) or a copy is incomplete."
            )
            continue
        checked += 1
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

    # `manifest_structure_error` has already guaranteed a non-empty string `marker` whenever there are
    # templated entries, so the substitution check below can rely on it.
    for rel, spec in sorted(m.get("templated", {}).items()):
        f = ROOT / rel
        try:
            present = f.is_file()
            text = f.read_text(encoding="utf-8", errors="replace") if present else None
        except OSError as exc:
            return _unprobeable(rel, exc)
        if not present:
            drift.append(f"MISSING — {rel} (templated: {spec.get('rule', '?')})")
            continue
        checked += 1
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
