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
GATES = [
    "check_decisions.py",
    "check_vendored_drift.py",
    "check_mutation_applicability.py",
    "check_loop_obligations.py",
]

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
    (tmp / "docs" / "DECISIONS.md").write_text("# Decision register\n" + GOOD_ROW, encoding="utf-8")
    return tmp


def run(root: Path, gate: str, args: tuple[str, ...] = ()) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(root / "tools" / "gates" / gate), *args],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return p.returncode, p.stdout + p.stderr


def case(name: str, gate: str, mutate, expect: int, expect_text: str | None = None,
         args: tuple[str, ...] = ()) -> None:
    tmp = sandbox()
    try:
        mutate(tmp)
        rc, out = run(tmp, gate, args)
        ok = rc == expect
        detail = f"exit {rc}" if ok else f"exit {rc}, expected {expect}"
        if ok and expect_text and expect_text.lower() not in out.lower():
            ok, detail = False, f"exit {rc}, but never mentioned {expect_text!r}"
        results.append((name, ok, detail))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def set_field(root: Path, label: str, value: str) -> None:
    p = root / "docs" / "DECISIONS.md"
    lines = p.read_text(encoding="utf-8").splitlines()
    out = [f"- **{label}:** {value}" if l.strip().startswith(f"- **{label}:**") else l for l in lines]
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def drop_field(root: Path, label: str) -> None:
    p = root / "docs" / "DECISIONS.md"
    p.write_text("\n".join(
        l for l in p.read_text(encoding="utf-8").splitlines() if not l.strip().startswith(f"- **{label}:**")
    ) + "\n", encoding="utf-8")


# ── decision register: it must FIRE ──────────────────────────────────────────────────────────────
case("register absent is could-not-run, not a pass", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").unlink(), 2, "does not exist")

# A register saved under a non-UTF-8 host encoding (Windows cp1252 writes the em-dash as byte
# 0x97) is undecodable here. That is a COULD-NOT-RUN — a crash on read must never surface as a
# VIOLATED row. cp1252 yields 0x97 on any host, so this case is locale-independent.
case("a non-UTF-8 register is could-not-run, not a crashed violation", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text(
         "# reg\n## DEC-1 — x\n\n- **Status:** OPEN\n", encoding="cp1252"), 2, "not valid UTF-8")

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
         "# reg\n" + GOOD_ROW + GOOD_ROW, encoding="utf-8"), 1, "duplicate identifier")

case("RESOLVED with no ruling is rejected", "check_decisions.py",
     lambda t: (set_field(t, "Status", "RESOLVED"), set_field(t, "Ruling", "—")), 1,
     "no ruling recorded")

case("a decision cited but never recorded is rejected", "check_decisions.py",
     lambda t: (t / "README.md").write_text("See DEC-99 for the caching choice.\n", encoding="utf-8"), 1,
     "not a row")

# ── decision register: it must STAY QUIET ────────────────────────────────────────────────────────
case("a well-formed open row passes", "check_decisions.py", lambda t: None, 0)

case("an EMPTY register passes and says it validated zero rows", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text("# Decision register\n\nNo rows yet.\n", encoding="utf-8"), 0,
     "zero rows")

case("a RESOLVED row citing a real ruling passes", "check_decisions.py",
     lambda t: (set_field(t, "Status", "RESOLVED"),
                set_field(t, "Ruling", "ADR-004, 2026-01-09")), 0)

# ── vendored drift ───────────────────────────────────────────────────────────────────────────────
def with_manifest(root: Path, *, edit: bool = False, template_leak: bool = False,
                  missing: bool = False) -> None:
    shared = root / "shared.md"
    shared.write_text("upstream content\n", encoding="utf-8")
    tmpl = root / "templated.md"
    tmpl.write_text("this repo is downstream-repo\n", encoding="utf-8")
    import hashlib
    h = hashlib.sha256(shared.read_bytes()).hexdigest()
    (root / "tools" / "gates" / "vendored.json").write_text(json.dumps({
        "upstream": "example/upstream", "revision": "abc123",
        "upstream_marker": "UPSTREAM-SLUG",
        "verbatim": {"shared.md": h},
        "templated": {"templated.md": {"rule": "slug substituted"}},
    }), encoding="utf-8")
    if edit:
        shared.write_text("upstream content\nlocal tweak\n", encoding="utf-8")
    if template_leak:
        tmpl.write_text("this repo is UPSTREAM-SLUG\n", encoding="utf-8")
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
     lambda t: (t / "tools" / "gates" / "vendored.json").write_text("{ not json", encoding="utf-8"), 2, "unreadable")

# A top-level annotation key is ignored (the gate reads named keys, never iterates them), so a manifest
# carrying a `_comment` next to a real, unchanged entry still passes. This is the ONLY place annotations
# are tolerated — inside verbatim/templated every key is a real path.
def annotated_ok(root: Path) -> None:
    shared = root / "shared.md"
    shared.write_text("upstream content\n", encoding="utf-8")
    import hashlib
    h = hashlib.sha256(shared.read_bytes()).hexdigest()
    (root / "tools" / "gates" / "vendored.json").write_text(json.dumps({
        "_comment": "notes belong up here", "upstream": "example/upstream", "revision": "abc123",
        "verbatim": {"shared.md": h},
    }), encoding="utf-8")

case("a top-level annotation key does not stop a valid manifest passing", "check_vendored_drift.py",
     annotated_ok, 0)

# ── malformed manifests are could-not-run, never a crash and never a silent pass ─────────────────
# Every shape below would raise partway through the comparison (AttributeError on a non-dict, TypeError
# slicing a non-string hash) and exit 1 — a could-not-run masquerading as a real drift. Up-front
# structure validation must turn each into a clean exit 2.
def bad_manifest(root: Path, obj) -> None:
    (root / "tools" / "gates" / "vendored.json").write_text(
        obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")

case("a top-level array manifest is could-not-run, not a crash", "check_vendored_drift.py",
     lambda t: bad_manifest(t, []), 2, "not an object")

case("a non-object verbatim block is could-not-run, not a crash", "check_vendored_drift.py",
     lambda t: bad_manifest(t, {"verbatim": []}), 2, "not an object")

# The file is PRESENT so the base gate reaches `expected[:16]` and crashes with TypeError (exit 1);
# the validator must turn that into a clean exit 2 before any file is touched.
case("a non-string verbatim hash is could-not-run, not a crash", "check_vendored_drift.py",
     lambda t: ((t / "real.md").write_text("x\n", encoding="utf-8"),
                bad_manifest(t, {"verbatim": {"real.md": 12345}})), 2, "not a string")

case("a non-object templated entry is could-not-run, not a crash", "check_vendored_drift.py",
     lambda t: bad_manifest(t, {"upstream_marker": "X", "templated": {"docs/x.md": "a rule"}}),
     2, "not an object")

case("a non-string upstream_marker is could-not-run, not a crash", "check_vendored_drift.py",
     lambda t: bad_manifest(t, {"upstream_marker": True, "templated": {"t.md": {"rule": "r"}}}),
     2, "non-empty string")

case("a path that escapes the repo is could-not-run, not a pass", "check_vendored_drift.py",
     lambda t: bad_manifest(t, {"verbatim": {"../escape.md": "0" * 64}}), 2, "repo-relative")

# An over-long path component makes is_file() raise OSError (ENAMETOOLONG). That must be a could-not-run
# for that entry, not an unhandled crash reported as a drift.
case("an unreadable (over-long) path is could-not-run, not a crash", "check_vendored_drift.py",
     lambda t: bad_manifest(t, {"verbatim": {("a" * 5000) + "/x.md": "0" * 64}}), 2, "could not be read")

# REGRESSION PIN: a vendored file whose name starts with `_` (Netlify _headers, Jekyll _config.yml,
# Sass _partial, Python __init__.py) must be checked like any other — the earlier `_`-skip silently
# passed a drifted one. Here `_headers` is present but its content does not match the recorded hash.
def drifted_underscore_file(root: Path) -> None:
    (root / "_headers").write_text("locally changed\n", encoding="utf-8")
    bad_manifest(root, {"upstream": "o/u", "revision": "r",
                        "verbatim": {"_headers": "0" * 64}})

case("a drifted `_`-prefixed vendored file is still flagged, not skipped", "check_vendored_drift.py",
     drifted_underscore_file, 1, "drifted locally")

# ── mutation applicability ───────────────────────────────────────────────────────────────────────
case("no source is NOT APPLICABLE, and names the trigger", "check_mutation_applicability.py",
     lambda t: None, 0, "trigger")

case("source with no mutation config is rejected", "check_mutation_applicability.py",
     lambda t: (t / "src").mkdir() or (t / "src" / "a.ts").write_text("export const x = 1;\n", encoding="utf-8"),
     1, "unobtainable")

case("source WITH mutation config passes", "check_mutation_applicability.py",
     lambda t: ((t / "src").mkdir(), (t / "src" / "a.ts").write_text("export const x = 1;\n", encoding="utf-8"),
                (t / "stryker.config.json").write_text("{}", encoding="utf-8")), 0)

case("a TEST file alone does not trip it (mutating a test is meaningless)",
     "check_mutation_applicability.py",
     lambda t: ((t / "src").mkdir(), (t / "src" / "a.test.ts").write_text("test('x',()=>{});\n", encoding="utf-8")),
     0, "not applicable")

# ── Regressions found by ADVERSARIAL TESTING of this kit, each pinned here ───────────────────────
# Every case below corresponds to a defect that existed and shipped-then-was-caught. They are the most
# valuable cases in the file, because each one is a hole somebody already fell into.

case("a TILDE-fenced example row is not parsed as a real row", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text(
         "# reg\n~~~\n## DEC-5 — an example inside a tilde fence\n\n- **Status:** OPEN\n~~~\n",
         encoding="utf-8"), 0, "zero rows")

case("a BACKTICK-fenced example row is not parsed as a real row", "check_decisions.py",
     lambda t: (t / "docs" / "DECISIONS.md").write_text(
         "# reg\n```\n## DEC-6 — an example inside a backtick fence\n\n- **Status:** OPEN\n```\n",
         encoding="utf-8"), 0, "zero rows")

case("a VACUOUS code locus does not satisfy the entry condition", "check_decisions.py",
     lambda t: set_field(t, "What differs in the code", "(a) `.` (b) `x.`"), 1,
     "names no concrete code locus")

case("a real dotted symbol IS accepted as a locus", "check_decisions.py",
     lambda t: set_field(t, "What differs in the code", "(a) `Cache.write` sync (b) `Queue.push`"), 0)

def put_source(root, rel: str, body: str = "export const f = 1;\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")

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

# ── loop obligations: a gate over a PROMPT ───────────────────────────────────────────────────────
#
# This gate is the odd one out — its subject is a markdown file an agent reads, not code. That makes
# fault injection MORE important, not less: there is no compiler and no test run to notice when the
# check has quietly stopped checking, so watching it fail is the only evidence it works at all.

SKILL_REL = Path("examples/skills/task-loop/SKILL.md")
REGISTER_REL = Path("tools/gates/loop-obligations.expected")

REGISTER = """
[X-1] the loop stops rather than guessing
source = handbook section 1
requires = halt and say so | never a paraphrase
artifact = grounding.md
"""
SKILL_BODY = "# task-loop\n\nQuote the requirement, **never a paraphrase**.\nNo human? Then halt and say so.\n"


def put_loop(root: Path, *, skill: str | None = SKILL_BODY, register: str | None = REGISTER) -> None:
    if skill is not None:
        (root / SKILL_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / SKILL_REL).write_text(skill, encoding="utf-8")
    if register is not None:
        (root / REGISTER_REL).write_text(register, encoding="utf-8")


def trace(root: Path, files: dict[str, str]) -> Path:
    d = root / ".trace"
    d.mkdir(exist_ok=True)
    for name, body in files.items():
        (d / name).write_text(body, encoding="utf-8")
    return d


# it must STAY QUIET
case("no skill and no register is NOT APPLICABLE, and names the trigger", "check_loop_obligations.py",
     lambda t: None, 0, "trigger")

case("a skill carrying every registered obligation passes", "check_loop_obligations.py",
     lambda t: put_loop(t), 0)

# THE REGRESSION THAT WAS FOUND ON FIRST RUN. A line wrap fell inside a required phrase and three
# rows reported missing against a skill that said exactly the right thing. A check a paragraph
# reflow can turn red is a check people delete, so formatting is normalised — pinned here so nobody
# "simplifies" the matching back to a plain substring test.
case("a required phrase split across a LINE WRAP still matches", "check_loop_obligations.py",
     lambda t: put_loop(t, skill="# task-loop\n\nQuote it, **never a\nparaphrase**.\nNo human? Then\nhalt and say so.\n"),
     0)

case("emphasis markers inside a required phrase do not break the match", "check_loop_obligations.py",
     lambda t: put_loop(t, skill="# t\n\n`never a **paraphrase**` — and then _halt and say so_.\n"), 0)

# it must FIRE
case("a skill that dropped an obligation is rejected, and blames the SKILL",
     "check_loop_obligations.py",
     lambda t: put_loop(t, skill="# task-loop\n\nQuote the requirement, never a paraphrase.\n"),
     1, "the skill is the defect")

case("a register with rows but no skill is could-not-run, not a pass", "check_loop_obligations.py",
     lambda t: put_loop(t, skill=None), 2)

case("a skill with no register is could-not-run, and warns against a mirror",
     "check_loop_obligations.py",
     lambda t: put_loop(t, register=None), 2, "mirror")

case("an EMPTY skill is could-not-run rather than 25 spurious findings", "check_loop_obligations.py",
     lambda t: put_loop(t, skill="   \n"), 2)

case("a register with zero rows is could-not-run, not a trivial pass", "check_loop_obligations.py",
     lambda t: put_loop(t, register="# only comments here\n"), 2, "no rows")

case("a malformed register is could-not-run, never a partial silent pass",
     "check_loop_obligations.py",
     lambda t: put_loop(t, register=REGISTER + "\nthis line is neither a header nor a field\n"),
     2, "malformed")

# A row that demands nothing passes against ANY skill — the same class of defect as a gate that
# cannot fail, so the gate refuses it rather than counting it as verified.
case("a row requiring no tokens is rejected as un-failable", "check_loop_obligations.py",
     lambda t: put_loop(t, register="[X-9] a row that checks nothing\nsource = s\nrequires =\nartifact = none\n"),
     1, "can never fail")

# self-test mode: the artifacts are the assertion
case("--self-test with every artifact present passes", "check_loop_obligations.py",
     lambda t: (put_loop(t), trace(t, {"grounding.md": "quoted the rule\n"})), 0,
     args=("--self-test", ".trace"))

case("--self-test with a MISSING artifact is rejected", "check_loop_obligations.py",
     lambda t: (put_loop(t), trace(t, {})), 1, "never written",
     args=("--self-test", ".trace"))

case("--self-test with an EMPTY artifact is rejected (a stage that did nothing)",
     "check_loop_obligations.py",
     lambda t: (put_loop(t), trace(t, {"grounding.md": ""})), 1, "empty",
     args=("--self-test", ".trace"))

case("--self-test pointed at a directory that does not exist is could-not-run",
     "check_loop_obligations.py",
     lambda t: put_loop(t), 2, "does not exist",
     args=("--self-test", ".no-such-trace"))

case("--self-test with no directory argument is could-not-run", "check_loop_obligations.py",
     lambda t: put_loop(t), 2, "needs a trace directory", args=("--self-test",))

case("an unknown argument is could-not-run, not ignored", "check_loop_obligations.py",
     lambda t: put_loop(t), 2, "unknown argument", args=("--wat",))


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
