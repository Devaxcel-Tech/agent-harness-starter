#!/usr/bin/env python3
"""If there is code to mutate, mutation testing must be obtainable for it.

WHY THIS GATE IS UNUSUAL, AND WHY IT IS THE MOST USEFUL ONE IN THE KIT.

Most gates check that something is right. This one checks that a **measurement is possible** — and it
exists because of a specific, very common way a quality plan quietly dies.

The pattern goes like this. Someone writes "we should add mutation testing" in a document. It becomes
an item on a list. The list is reviewed occasionally and the item is still true, so it stays. Nothing
ever fails, so nothing ever forces the issue. **A to-do is not a control.** Two years later the
document still says mutation testing is the coverage metric and no package has ever been measured.

This gate is the difference. It distinguishes two states that otherwise both look fine:

    NOT APPLICABLE   There is no source, so there is nothing to measure. Passes — **and states the
                     trigger**, because "not applicable" stops being true silently the first time
                     somebody adds a source file.

    UNOBTAINABLE     There IS source, and the metric cannot be produced for it. **Fails.**

The second is the obvious value. The first is the one that matters more in practice, because that is
the transition nobody is watching for.

WHY MUTATION TESTING SPECIFICALLY, rather than line coverage: coverage measures *execution*, mutation
measures *verification*. A test that calls a function and asserts nothing scores full coverage and
kills no mutants. When an AI agent writes both the code and the tests, assertion-free tests are the
default failure mode — so coverage is precisely the wrong thing to gate on, and mutation is precisely
the right one.

TAILOR: `SOURCE_EXTENSIONS`, `TEST_SUFFIXES`, `EXCLUDE_PARTS` and `CONFIG_CANDIDATES` are meant to be
edited for your language and layout. The shape of the check does not change.

Note `EXCLUDE_PARTS` skips `examples`, `fixtures` and `testdata` by default, on the assumption they
hold sample data rather than shipped code. If your project keeps real source in one of those, remove
it from the set — otherwise you get the silent pass this gate exists to prevent.

EXIT CODES: 0 not applicable or obtainable · 1 source exists and it is unobtainable · 3 configured but
the config does not reach the source. See harness.py; 3 is not a pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import INCOMPLETE, VERIFIED, VIOLATED, repo_root, report  # noqa: E402

ROOT = repo_root()

# ── Tailor these ─────────────────────────────────────────────────────────────────────────────────
#
# THIS IS A DENY-LIST BY EXTENSION, NOT AN ALLOW-LIST BY DIRECTORY, and that is a deliberate
# correction. The first version listed `src/**`, `lib/**`, `packages/**` and `app/**`. Adversarial
# testing put a source file in `internal/service/` and the gate reported NOT APPLICABLE — a silent
# pass, on a repository full of code, from the gate whose entire purpose is catching silent passes.
#
# For a kit strangers adopt that is close to fatal: most repositories do not use those four names, so
# the default behaviour would have been to quietly do nothing while looking healthy. An allow-list of
# directories fails SILENTLY when it is wrong; a deny-list of build output fails LOUDLY, by finding
# more than you expected. Prefer the second every time.
SOURCE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".kt", ".kts",
    ".rb", ".cs", ".swift", ".scala", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".mm",
}
TEST_SUFFIXES = (".test.ts", ".spec.ts", "_test.ts", ".test.js", ".spec.js", ".d.ts")
# Any one of these existing means the tooling is present. Add your language's equivalent —
# stryker.conf.json (JS/TS), pom.xml with PIT, mutmut.ini / setup.cfg (Python), cargo-mutants.toml.
CONFIG_CANDIDATES = [
    "stryker.config.json", "stryker.conf.json", ".stryker.conf.json",
    "tools/qa/stryker.config.json", "mutmut.ini", "cargo-mutants.toml",
]
EXCLUDE_PARTS = {
    # Dependencies and build output — never this project's source.
    "node_modules", ".git", "dist", "build", "out", "target", "vendor", ".venv", "venv",
    "coverage", "generated", "__snapshots__", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", "third_party", "site-packages",
    # Sample data rather than shipped code. Remove any of these if your project keeps real source
    # there, or you get the silent pass this gate exists to prevent.
    "examples", "fixtures", "testdata",
    # THE HARNESS ITSELF, and this one is worth explaining. Inverting the scan from an allow-list of
    # product directories to a deny-list by extension fixed a silent pass — and immediately created a
    # new one in the opposite direction: the gate started counting ITS OWN Python files as product
    # source, so the harness reported that the harness was unmeasured, forever.
    #
    # Build tooling is not the product. Mutation-testing your gates is a different question, and it is
    # already answered by the gate fault suite, which is a stronger control for this purpose because it
    # asserts each gate's exact verdict rather than whether some test noticed a perturbation.
    #
    # If your product genuinely lives under one of these, remove it — and read the reported file count.
    "tools", "scripts", ".githooks",
}


def is_excluded(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_PARTS:
        return True
    # Build-tool convenience symlinks (Bazel writes bazel-*, others write similar) point outside the
    # project and are a classic way a whole-tree scan wanders into third-party code.
    return any(p.startswith("bazel-") for p in parts)


def source_files() -> list[str]:
    """Non-test source files anywhere in the repo — the ones a mutant could be planted in.

    Walks the whole tree and filters by EXTENSION, so code in an unexpected directory is found rather
    than silently skipped. Test files are excluded because mutating a test is meaningless: the tool
    perturbs the code under test and asks whether a test notices.
    """
    out: set[str] = set()
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        if p.suffix not in SOURCE_EXTENSIONS:
            continue
        rel = p.relative_to(ROOT)
        # Skip any dot-directory (.git, .github, .venv, editor state) plus the named exclusions.
        if any(part.startswith(".") for part in rel.parts[:-1]) or is_excluded(rel):
            continue
        if p.name.endswith(TEST_SUFFIXES):
            continue
        out.add(str(rel))
    return sorted(out)


def main() -> int:
    sources = source_files()

    if not sources:
        return report(
            "mutation applicability",
            VERIFIED,
            verified=["NOT APPLICABLE — 0 non-test source files matched, so there is nothing to mutate."],
            note=(
                "The metric is not missing here, it is inapplicable. **THIS IS THE TRIGGER:** the moment "
                "a source file lands, this gate turns RED until mutation testing is configured. That is "
                "deliberate — it is what stops 'not applicable' quietly becoming 'unmeasured'. If this "
                "says 0 and your repo plainly has code, the extension is missing from SOURCE_EXTENSIONS "
                "or a parent directory is in EXCLUDE_PARTS — fix that rather than accepting the result, "
                "because a scan matching nothing is indistinguishable from a project with no code."
            ),
        )

    found = [c for c in CONFIG_CANDIDATES if (ROOT / c).is_file()]
    if not found:
        shown = "\n".join(f"      {s}" for s in sources[:8])
        more = f"\n      … and {len(sources) - 8} more" if len(sources) > 8 else ""
        return report(
            "mutation applicability",
            VIOLATED,
            violations=[
                "MUTATION METRIC UNOBTAINABLE — there is source to mutate and no way to mutate it.\n\n"
                f"      {len(sources)} non-test source file(s):\n{shown}{more}\n\n"
                f"      Looked for any of: {', '.join(CONFIG_CANDIDATES)}\n\n"
                "      Nothing here has been measured by the metric that distinguishes a test which\n"
                "      VERIFIES from a test which merely EXECUTES — and until now nothing said so.\n\n"
                "      Fix by configuring a mutation tool for your language, or by recording a decision\n"
                "      that it will not be configured and why (see docs/DECISIONS.md).\n"
                "      Do NOT silence this by deleting the check, narrowing SOURCE_EXTENSIONS to match\n"
                "      nothing, or adding a config that yields no score — each converts a real gap into\n"
                "      a false green, which is the failure this whole harness exists to prevent."
            ],
        )

    return report(
        "mutation applicability",
        VERIFIED,
        verified=[
            f"{len(sources)} non-test source file(s) present, and mutation tooling is configured "
            f"({found[0]})."
        ],
        note=(
            "This proves the metric is OBTAINABLE. It does not prove it was obtained, or that it "
            "cleared a floor — running it and enforcing the floor is a separate step, and it belongs "
            "in CI. Do not read this green as 'well tested'."
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
