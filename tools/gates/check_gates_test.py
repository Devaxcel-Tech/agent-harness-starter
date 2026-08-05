#!/usr/bin/env python3
"""Fault injection for every gate in this kit (the "who checks the checkers" suite).

WHY THIS FILE IS NOT OPTIONAL.

**A gate nobody has watched fail is a comment.** It is very easy to write a check that always passes —
a typo in a glob, an exception swallowed, a condition inverted — and a gate that always passes is
indistinguishable from a codebase that is always correct. You cannot tell the difference by reading
the output, because the output is identical.

So each case below **makes the violation real** in a throwaway copy of a repository: it creates the
malformed row, deletes the required field, edits the shared file, adds the source file. Then it
asserts the gate's **exact exit code**.

EXACT CODES, NOT ZERO-VS-NONZERO. This matters more than it looks. Exit 1 ("the property is broken")
and exit 3 ("I could not check the important part") are different claims, and a suite that accepted
any failure would pass while a gate conflated them — which is the confusion the exit codes exist to
prevent.

NEGATIVE CASES ARE AS IMPORTANT AS POSITIVE ONES. A gate that fires on everything gets disabled within
a week. Each gate here has at least one case proving it stays quiet when it should.

Run: python3 tools/gates/check_gates_test.py
Exit 0 = every case behaved as specified. Exit 1 = a gate does not do what it claims.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
GATES = ["check_decisions.py", "check_vendored_drift.py", "check_mutation_applicability.py"]

results: list[tuple[str, bool, str]] = []

GOOD_ROW = """
## DEC-1 — Should the cache be write-through or write-behind?

- **Status:** OPEN
- **Issue:** https://example.invalid/org/repo/issues/1
- **What is owed:** which write strategy the cache uses.
- **Why the work stopped:** the two differ in failure behaviour, not just speed.
- **What was done instead:** nothing cached; every read hits the store.
- **Candidate answers:** (a) write-through (b) write-behind with a flush interval
- **What differs in the code:** (a) `src/cache/write.ts` writes synchronously (b) it enqueues to `src/cache/queue.ts`
- **Ruling:** —
"""


def sandbox() -> Path:
    """A throwaway repo containing only what a gate needs to reach a verdict."""
    tmp = Path(tempfile.mkdtemp(prefix="harness-gate-"))
    (tmp / ".git").mkdir()  # repo_root() walks up for this
    (tmp / "tools" / "gates").mkdir(parents=True)
    (tmp / "docs").mkdir()
    for g in [*GATES, "harness.py"]:
        shutil.copy2(KIT / "tools" / "gates" / g, tmp / "tools" / "gates" / g)
    (tmp / "docs" / "DECISIONS.md").write_text("# Decision register\n" + GOOD_ROW)
    return tmp


def run(root: Path, gate: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(root / "tools" / "gates" / gate)],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return p.returncode, p.stdout + p.stderr


def case(name: str, gate: str, mutate, expect: int, expect_text: str | None = None) -> None:
    tmp = sandbox()
    try:
        mutate(tmp)
        rc, out = run(tmp, gate)
        ok = rc == expect
        detail = f"exit {rc}" if ok else f"exit {rc}, expected {expect}"
        if ok and expect_text and expect_text.lower() not in out.lower():
            ok, detail = False, f"exit {rc}, but never mentioned {expect_text!r}"
        results.append((name, ok, detail))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def set_field(root: Path, label: str, value: str) -> None:
    p = root / "docs" / "DECISIONS.md"
    lines = p.read_text().splitlines()
    out = [f"- **{label}:** {value}" if l.strip().startswith(f"- **{label}:**") else l for l in lines]
    p.write_text("\n".join(out) + "\n")


def drop_field(root: Path, label: str) -> None:
    p = root / "docs" / "DECISIONS.md"
    p.write_text("\n".join(
        l for l in p.read_text().splitlines() if not l.strip().startswith(f"- **{label}:**")
    ) + "\n")


# ── decision register: it must FIRE ──────────────────────────────────────────────────────────────
case("register absent is could-not-run, not a pass", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").unlink(), 2, "does not exist")

case("a row with no issue link is rejected", "check_decisions.py",
     lambda t: set_field(t, "Issue", "will file one later"), 1, "delivery mechanism")

case("a row with no candidate answers is rejected", "check_decisions.py",
     lambda t: set_field(t, "Candidate answers", "not sure yet"), 1, "labelled options")

case("a row that names no code difference is rejected (the entry condition)", "check_decisions.py",
     lambda t: set_field(t, "What differs in the code", "quite a lot would change"), 1,
     "task, not a\n      decision")

case("a missing required field is rejected", "check_decisions.py",
     lambda t: drop_field(t, "Issue"), 1, "missing required field")

case("an unknown status is rejected", "check_decisions.py",
     lambda t: set_field(t, "Status", "MAYBE"), 1, "not one of")

case("a duplicate id is rejected", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text(
         "# reg\n" + GOOD_ROW + GOOD_ROW), 1, "duplicate identifier")

case("RESOLVED with no ruling is rejected", "check_decisions.py",
     lambda t: (set_field(t, "Status", "RESOLVED"), set_field(t, "Ruling", "—")), 1,
     "no ruling recorded")

case("a decision cited but never recorded is rejected", "check_decisions.py",
     lambda t: (t / "README.md").write_text("See DEC-99 for the caching choice.\n"), 1,
     "not a row")

# ── decision register: it must STAY QUIET ────────────────────────────────────────────────────────
case("a well-formed open row passes", "check_decisions.py", lambda t: None, 0)

case("an EMPTY register passes and says it validated zero rows", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text("# Decision register\n\nNo rows yet.\n"), 0,
     "zero rows")

case("a RESOLVED row citing a real ruling passes", "check_decisions.py",
     lambda t: (set_field(t, "Status", "RESOLVED"),
                set_field(t, "Ruling", "ADR-004, 2026-01-09")), 0)

# ── vendored drift ───────────────────────────────────────────────────────────────────────────────
def with_manifest(root: Path, *, edit: bool = False, template_leak: bool = False,
                  missing: bool = False) -> None:
    shared = root / "shared.md"
    shared.write_text("upstream content\n")
    tmpl = root / "templated.md"
    tmpl.write_text("this repo is downstream-repo\n")
    import hashlib
    h = hashlib.sha256(shared.read_bytes()).hexdigest()
    (root / "tools" / "gates" / "vendored.json").write_text(json.dumps({
        "upstream": "example/upstream", "revision": "abc123",
        "upstream_marker": "UPSTREAM-SLUG",
        "verbatim": {"shared.md": h},
        "templated": {"templated.md": {"rule": "slug substituted"}},
    }))
    if edit:
        shared.write_text("upstream content\nlocal tweak\n")
    if template_leak:
        tmpl.write_text("this repo is UPSTREAM-SLUG\n")
    if missing:
        shared.unlink()

case("no manifest is NOT APPLICABLE and passes", "check_vendored_drift.py", lambda t: None, 0,
     "not applicable")

case("a locally edited shared file is rejected", "check_vendored_drift.py",
     lambda t: with_manifest(t, edit=True), 1, "drifted locally")

case("a half-substituted template is rejected", "check_vendored_drift.py",
     lambda t: with_manifest(t, template_leak=True), 1, "half-substituted")

case("a shared file listed and missing is rejected", "check_vendored_drift.py",
     lambda t: with_manifest(t, missing=True), 1, "missing")

case("an unchanged shared file passes", "check_vendored_drift.py",
     lambda t: with_manifest(t), 0)

case("an unreadable manifest is could-not-run, not a pass", "check_vendored_drift.py",
     lambda t: (t / "tools" / "gates" / "vendored.json").write_text("{ not json"), 2, "unreadable")

# ── mutation applicability ───────────────────────────────────────────────────────────────────────
case("no source is NOT APPLICABLE, and names the trigger", "check_mutation_applicability.py",
     lambda t: None, 0, "trigger")

case("source with no mutation config is rejected", "check_mutation_applicability.py",
     lambda t: (t / "src").mkdir() or (t / "src" / "a.ts").write_text("export const x = 1;\n"),
     1, "unobtainable")

case("source WITH mutation config passes", "check_mutation_applicability.py",
     lambda t: ((t / "src").mkdir(), (t / "src" / "a.ts").write_text("export const x = 1;\n"),
                (t / "stryker.config.json").write_text("{}")), 0)

case("a TEST file alone does not trip it (mutating a test is meaningless)",
     "check_mutation_applicability.py",
     lambda t: ((t / "src").mkdir(), (t / "src" / "a.test.ts").write_text("test('x',()=>{});\n")),
     0, "not applicable")

# ── Regressions found by ADVERSARIAL TESTING of this kit, each pinned here ───────────────────────
# Every case below corresponds to a defect that existed and shipped-then-was-caught. They are the most
# valuable cases in the file, because each one is a hole somebody already fell into.

case("a TILDE-fenced example row is not parsed as a real row", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text(
         "# reg\n~~~\n## DEC-5 — an example inside a tilde fence\n\n- **Status:** OPEN\n~~~\n"), 0,
     "zero rows")

case("a BACKTICK-fenced example row is not parsed as a real row", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text(
         "# reg\n```\n## DEC-6 — an example inside a backtick fence\n\n- **Status:** OPEN\n```\n"), 0,
     "zero rows")

case("a VACUOUS code locus does not satisfy the entry condition", "check_decisions.py",
     lambda t: set_field(t, "What differs in the code", "(a) `.` (b) `x.`"), 1,
     "names no concrete code locus")

case("a real dotted symbol IS accepted as a locus", "check_decisions.py",
     lambda t: set_field(t, "What differs in the code", "(a) `Cache.write` sync (b) `Queue.push`"), 0)

def put_source(root, rel: str, body: str = "export const f = 1;\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)

case("source in an UNCONVENTIONAL directory is still found", "check_mutation_applicability.py",
     lambda t: put_source(t, "internal/service/a.ts"), 1, "unobtainable")

case("source in ANY supported language is found, not just TypeScript",
     "check_mutation_applicability.py",
     lambda t: put_source(t, "cmd/main.go", "package main\n"), 1, "unobtainable")

case("a dependency directory is NOT counted as product source",
     "check_mutation_applicability.py",
     lambda t: put_source(t, "node_modules/pkg/index.js"), 0, "not applicable")

case("the HARNESS's own scripts are not counted as product source",
     "check_mutation_applicability.py",
     lambda t: put_source(t, "tools/helper.py", "x = 1\n"), 0, "not applicable")

# ── verdict ──────────────────────────────────────────────────────────────────────────────────────
print("gate fault injection — every case makes the violation real\n")
failed = 0
for name, ok, detail in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  ({detail})")
    failed += 0 if ok else 1

print()
if failed:
    print(f"{failed} of {len(results)} case(s) did not behave as specified.", file=sys.stderr)
    print("A gate does not do what it claims. Fix the GATE, never this suite.", file=sys.stderr)
    sys.exit(1)

print(f"all {len(results)} cases behaved as specified — every gate fires on a real violation, "
      "stays quiet when it should, and reports could-not-run rather than passing when it cannot "
      "reach a verdict.")
sys.exit(0)
