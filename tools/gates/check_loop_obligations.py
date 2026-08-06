#!/usr/bin/env python3
"""The task-loop skill must still carry every obligation the handbook states (stdlib only).

WHAT THIS PROVES, AND THE BOUNDARY IT DOES NOT CROSS.

The loop is a markdown prompt, and **no check can guarantee that an agent follows a prompt.** That
has to be said first, because a gate over a process invites exactly the overclaim the rest of this
kit exists to remove — a control that reads like proof and is not. Two honest halves:

  STATIC (the default; belongs in CI on every push)
    The skill CONTAINS every obligation in `tools/gates/loop-obligations.expected`. A future edit
    cannot silently delete a step, a tool call or a hard rule: the row stops resolving and this goes
    red. This is a real mechanical guarantee, and it is the one that matters in practice, because the
    realistic failure is not an agent defying its instructions — it is the prompt quietly losing a
    step across a dozen edits until nobody remembers it was ever required.

  SELF-TEST (`--self-test <trace-dir>`)
    A `task-loop --self-test` run walks every stage against a fixture with all outward side effects
    disabled, writing one artifact per stage. This mode asserts those ARTIFACTS EXIST AND ARE
    NON-EMPTY — not the agent's claim to have produced them. An empty artifact fails: a stage that
    reported itself done without doing anything is the thing being looked for.

WHAT IS STILL NOT COVERED, stated rather than left to be discovered: a passing self-test says the
loop CAN execute every stage, never that yesterday's live run DID. Auditing a real run means reading
back its issue comments, PR body and evidence file, which needs API access this script deliberately
does not take.

WHY THE REGISTER IS AUTHORED FROM THE HANDBOOK. A register scraped out of the skill is a mirror: it
agrees with the skill even after the skill has drifted from the documented process, so it can never
disagree and never has anything to say. Authoring rows from a separate document keeps the two
independent. See the register's own header — including what to do if you have no such document.

MATCHING NORMALISES FORMATTING, AND THAT IS A DESIGN DECISION WORTH DEFENDING. Before comparing, both
the skill and each token are lowercased, stripped of markdown emphasis (`*`, `_`, backticks) and had
every run of whitespace collapsed to one space.

The reason is concrete rather than theoretical. Written naively, this check failed three rows on its
first run — not because the skill omitted anything, but because a line wrap fell inside the phrase and
`**Do not choose the\nsensible option**` is not a substring of anything. A check that a paragraph
reflow can turn red is a check people learn to delete, and a deleted check protects nothing.

What normalisation deliberately does NOT do is make matching fuzzy. Word order, wording and content
must still match exactly; only formatting is discounted. If you find yourself wanting to relax this
further to get green, that is the signal to fix the skill instead.

EXIT CODES follow this kit's convention, and 2 is never a pass:
  0 verified (or not applicable) · 1 an obligation is missing · 2 could not reach a verdict

Run:
  python3 tools/gates/check_loop_obligations.py                     # static
  python3 tools/gates/check_loop_obligations.py --self-test <dir>   # verify a trace
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import CANNOT_RUN, VERIFIED, VIOLATED, repo_root, report  # noqa: E402

ROOT = repo_root()

# TAILOR: where your loop skill lives. Kept under examples/ here because it is a template an adopter
# copies into their own agent's skill directory, exactly like examples/agents/.
SKILL_REL = "examples/skills/task-loop/SKILL.md"
REGISTER_REL = "tools/gates/loop-obligations.expected"

ROW_RE = re.compile(r"^\[([A-Za-z0-9_-]+)\]\s*(.*)$")
FIELD_RE = re.compile(r"^(source|requires|artifact)\s*=\s*(.*)$")


def parse_register(text: str) -> tuple[list[dict], list[str]]:
    """Read the register into rows. Returns (rows, malformed) — malformed is never silently dropped.

    A register with an unparseable row is a register that is quietly checking less than it appears
    to, which is the same class of defect as a gate that cannot fail.
    """
    rows: list[dict] = []
    malformed: list[str] = []
    current: dict | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        header = ROW_RE.match(line)
        if header:
            if current is not None:
                rows.append(current)
            current = {
                "id": header.group(1),
                "title": header.group(2).strip(),
                "requires": [],
                "artifact": "none",
                "source": "",
                "lineno": lineno,
            }
            continue

        field = FIELD_RE.match(line)
        if not field:
            malformed.append(f"line {lineno}: {line[:70]!r} is neither a row header nor a field")
            continue
        if current is None:
            malformed.append(f"line {lineno}: field {field.group(1)!r} appears before any row header")
            continue

        key, value = field.group(1), field.group(2).strip()
        if key == "requires":
            current["requires"] = [t.strip() for t in value.split("|") if t.strip()]
        else:
            current[key] = value

    if current is not None:
        rows.append(current)
    return rows, malformed


def normalise(text: str) -> str:
    """Lowercase, drop markdown emphasis, collapse whitespace — see the module docstring.

    Applied identically to the skill and to every token, so the comparison stays exact on words and
    order while ignoring how the text happens to be laid out.
    """
    return re.sub(r"\s+", " ", re.sub(r"[*_`]", "", text.lower())).strip()


def check_static(rows: list[dict], skill_text: str) -> tuple[list[str], list[str]]:
    haystack = normalise(skill_text)
    violations: list[str] = []
    ok: list[str] = []

    for row in rows:
        if not row["requires"]:
            # A row requiring nothing always passes and therefore checks nothing. Treat it as a
            # defect in the register rather than a quiet free pass.
            violations.append(
                f"[{row['id']}] {row['title']}\n"
                f"        The row requires no tokens, so it can never fail and checks nothing.\n"
                f"        Give it concrete tokens, or delete the row and say why in the change."
            )
            continue

        missing = [t for t in row["requires"] if normalise(t) not in haystack]
        if missing:
            violations.append(
                f"[{row['id']}] {row['title']}\n"
                f"        {SKILL_REL} no longer contains: " + ", ".join(repr(m) for m in missing) + "\n"
                f"        source: {row['source'] or '(none recorded)'}\n"
                f"        THE SKILL IS THE DEFECT — restore the step, the tool call or the rule.\n"
                f"        Never narrow this row to go green; the row is the only thing that noticed."
            )
        else:
            ok.append(f"[{row['id']}] {row['title']}")
    return ok, violations


def check_self_test(rows: list[dict], trace_dir: Path) -> tuple[list[str], list[str]]:
    expected = sorted({r["artifact"] for r in rows if r["artifact"] and r["artifact"] != "none"})
    violations: list[str] = []
    ok: list[str] = []

    for name in expected:
        path = trace_dir / name
        if not path.is_file():
            owed = ", ".join(r["id"] for r in rows if r["artifact"] == name)
            violations.append(
                f"{name} was never written (owed by {owed}).\n"
                f"        A stage that leaves no artifact and a stage that was skipped are\n"
                f"        indistinguishable from outside, so the artifact IS the assertion."
            )
        elif path.stat().st_size == 0:
            violations.append(
                f"{name} exists but is empty.\n"
                f"        An empty artifact is a stage that reported itself done without doing "
                f"anything."
            )
        else:
            ok.append(f"{name} ({path.stat().st_size} bytes)")
    return ok, violations


def main() -> int:
    args = sys.argv[1:]
    trace_dir: Path | None = None

    if args:
        if args[0] == "--self-test":
            if len(args) < 2:
                return report(
                    "loop obligations", CANNOT_RUN,
                    violations=["--self-test needs a trace directory: `--self-test <dir>`."],
                )
            trace_dir = Path(args[1])
        else:
            return report(
                "loop obligations", CANNOT_RUN,
                violations=[f"unknown argument {args[0]!r}. Use no argument, or `--self-test <dir>`."],
            )

    skill = ROOT / SKILL_REL
    register = ROOT / REGISTER_REL

    # NOT APPLICABLE, and it states its trigger — the same shape as the mutation gate. An adopter who
    # has not taken the loop should not be nagged; an adopter who takes it must not get a free pass.
    if not skill.is_file() and not register.is_file():
        return report(
            "loop obligations", VERIFIED,
            verified=[f"NOT APPLICABLE — no {SKILL_REL} and no register, so there is no loop to check."],
            note=(
                "THIS IS THE TRIGGER: the moment either file lands, this gate starts checking that the "
                "skill carries every registered obligation. If you adopt the loop, adopt the register "
                "with it — a process document nothing checks drifts silently, which is the failure the "
                "register exists to catch."
            ),
        )

    if not register.is_file():
        return report(
            "loop obligations", CANNOT_RUN,
            violations=[
                f"{SKILL_REL} exists but {REGISTER_REL} does not.\n"
                f"      There are obligations to check and nothing stating what they are, so this "
                f"reaches no verdict.\n"
                f"      Author the register from your process document — never from the skill, which "
                f"would make it a mirror."
            ],
        )

    if not skill.is_file():
        return report(
            "loop obligations", CANNOT_RUN,
            violations=[
                f"{REGISTER_REL} exists but {SKILL_REL} does not.\n"
                f"      The register names obligations and there is no skill carrying them."
            ],
        )

    try:
        register_text = register.read_text(encoding="utf-8")
        skill_text = skill.read_text(encoding="utf-8")
    except OSError as exc:
        return report("loop obligations", CANNOT_RUN, violations=[f"could not read a file: {exc}"])

    if not skill_text.strip():
        return report(
            "loop obligations", CANNOT_RUN,
            violations=[f"{SKILL_REL} is empty. Every obligation would report missing, which is noise, "
                        f"not a finding."],
        )

    rows, malformed = parse_register(register_text)

    if malformed:
        return report(
            "loop obligations", CANNOT_RUN,
            violations=[f"{REGISTER_REL} is malformed, so it is checking less than it appears to:"]
                       + [f"      {m}" for m in malformed],
        )

    if not rows:
        return report(
            "loop obligations", CANNOT_RUN,
            violations=[
                f"{REGISTER_REL} contains no rows.\n"
                f"      An empty register passes trivially against any skill whatsoever, which is "
                f"indistinguishable from a skill that carries everything."
            ],
        )

    if trace_dir is not None:
        if not trace_dir.is_dir():
            return report(
                "loop obligations", CANNOT_RUN,
                violations=[f"trace directory {str(trace_dir)!r} does not exist. With no trace there "
                            f"is nothing to verify — and nothing verified is not a pass."],
            )
        ok, violations = check_self_test(rows, trace_dir)
        label, subject = "self-test", "artifact(s) from a --self-test run"
    else:
        ok, violations = check_static(rows, skill_text)
        label, subject = "static", "registered obligation(s)"

    if violations:
        return report("loop obligations", VIOLATED, violations=violations)

    return report(
        "loop obligations", VERIFIED,
        verified=[f"{label}: {len(ok)} {subject} present, from {len(rows)} row(s)."],
        note=(
            "This proves the skill still CARRIES every registered obligation. It does not prove any "
            "live run OBEYED them — no static check reaches that, and reporting otherwise would be "
            "the faked pass this kit exists to prevent. Never cite this as evidence the process was "
            "followed."
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
