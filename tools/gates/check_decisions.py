#!/usr/bin/env python3
"""Validate the decision register — the questions the team cannot answer without an owner.

WHAT A DECISION REGISTER IS, AND THE PROBLEM IT SOLVES.

When someone building a feature hits a question the design does not settle, they have two options.
They can pick the sensible-looking answer and move on, or they can stop and get a ruling. Almost
everyone picks the first, because it is faster and the choice usually looks obvious.

The cost arrives later. **Once a guess is in the code it is indistinguishable from a decision.** Six
months on, nobody can tell which lines reflect a deliberate choice and which reflect somebody's
Tuesday afternoon. Changing them is frightening, because you cannot tell what you might be undoing.

The register keeps those two categories apart. A blocked question becomes a numbered row with the
options written down, and work routes around it instead of through it.

This matters far more with AI agents than with people. An agent will always produce a confident
answer — that is what it is for — so "stop and ask" has to be a mechanical rule with a gate behind
it, not an instinct you hope it has.

WHAT THIS GATE ENFORCES, and the reason for each.

  1. SCHEMA — every row carries every required field. A half-written row is a decision nobody can
     act on, which is the same as no row.
  2. UNIQUE, PERMANENT IDs — a number is never reused and never renumbered. Renumbering on closure
     dangles every citation of the old number, and frees the number for a different question.
  3. AN ISSUE LINK ON EVERY OPEN ROW — **this is the delivery mechanism.** A row in a file nobody
     opens has told nobody anything. The tracker's assignment notification is what actually reaches a
     human. This is the field most often missing, and the one whose absence is most expensive.
  4. CANDIDATE ANSWERS — the options, labelled. A question is not an answer; a decider must be able
     to see what they are choosing between without reconstructing it.
  5. WHAT DIFFERS IN THE CODE — **the entry condition, and the cleverest rule here.** Name what
     would be physically different under each option. If you cannot, this is a TASK, not a decision,
     and it does not belong in a decision register. Without this test the register slowly fills with
     to-do items and stops being read.
  6. A CLOSED ROW CITES ITS RULING — a row closes by pointing at a durable, findable decision.
     "We agreed in a meeting" cannot close a row, because a later reader cannot look it up.
  7. NO DANGLING CITATIONS — if a document anywhere cites a decision id, a row with that id must
     exist. A decision cited but never recorded is the precise failure the register exists to stop.
     Note the convention this forces, which caught a bug in this very file: prose that DISCUSSES an
     id must write it unnumbered (`DEC-<n>`), because a real number in a comment is a citation the
     scan will rightly demand a row for.

TAILOR, DO NOT WEAKEN. `ID_PREFIX`, the `REQUIRED_FIELDS_*` lists and `STATUSES` are meant to be edited
to fit your project. Removing a check because a row fails it is not tailoring — it is deleting the finding.

EXIT CODES: 0 verified · 1 violated · 2 could not run. See harness.py; 2 is not a pass.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import CANNOT_RUN, VERIFIED, VIOLATED, repo_root, report  # noqa: E402

ROOT = repo_root()

# ── Tailor these to your project ─────────────────────────────────────────────────────────────────
REGISTER = Path("docs/DECISIONS.md")
ID_PREFIX = "DEC"
STATUSES = {"OPEN", "RESOLVED"}
REQUIRED_FIELDS_OPEN = ["Status", "Issue", "Candidate answers", "What differs in the code"]
REQUIRED_FIELDS_RESOLVED = ["Status", "Ruling"]

# Where to look for citations of a decision id. Directories that are not this repo's to fix are
# excluded — a submodule's numbering is its own, and reporting it here is noise that trains people to
# ignore the gate.
CITATION_GLOBS = ["*.md", "docs/**/*.md", "tools/**/*.py", "tools/**/*.sh", ".github/**/*.yml"]
EXCLUDE_PARTS = {".git", "node_modules", "vendor", "dist", "build", "target", ".venv"}

# The gates' OWN fault-injection suites are excluded, and this is the one exemption in the gate.
# Their job is to construct malformed input — including a citation of an id that deliberately does
# NOT exist, to prove this very scan fires. Holding them to "every id must resolve" would make the
# suite and the gate mutually unsatisfiable.
#
# It is deliberately narrow: `tools/gates/*_test.py` only. It is NOT a general escape hatch, and the
# temptation to widen it is exactly how a citation scan stops meaning anything. If a normal source
# file needs an id that has no row, the answer is a row — or an unnumbered `DEC-<n>` in prose.
CITATION_EXEMPT_SUFFIXES = ("_test.py",)
CITATION_EXEMPT_DIRS = ("tools/gates",)

ROW_RE = re.compile(rf"^##\s+({ID_PREFIX}-\d+)\s+—\s+(.+?)\s*$", re.M)
FIELD_RE = re.compile(r"^-\s+\*\*(?P<label>[^:*]+):\*\*\s*(?P<value>.*)$")
CITATION_RE = re.compile(rf"\b{ID_PREFIX}-(\d+)\b")
# A real code locus, not a vague gesture — and NOT merely "something in backticks with a dot in it".
# Adversarial testing defeated the first version of this pattern with `` `.` ``: a single backticked
# dot satisfied the most important field in the register. The requirement is now that a locus has
# substance on BOTH sides of the separator, so `src/cache.ts`, `Cache.write` and `pkg/mod` all pass
# while `.`, `x.` and `..` do not.
#
# This regex is a floor, not a proof: it cannot tell a real path from a plausible-looking fake, and it
# is not meant to. Its job is to stop the field being satisfied by a gesture. Whether the locus is the
# RIGHT one is a question for review.
LOCUS_RE = re.compile(r"`[^`]*[A-Za-z0-9_)\]][./][A-Za-z0-9_(\[][^`]*`")


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbers.

    WHY: the register template ships an EXAMPLE row inside a fence so people can copy it. Without
    this, that example parses as a real row — so a fresh adopter starts with a phantom decision, and
    the day they add a real row with that number they get a duplicate-id error from a code sample.
    The same reasoning applies to citations: an id inside a fence is documentation of the format, not
    a reference to a decision.

    Lines are replaced rather than removed so every reported line number still points at the right
    place in the file.
    """
    # BOTH fence syntaxes. Markdown allows ``` and ~~~, and handling only the first was a real defect
    # found by adversarial testing: an example row inside a ~~~ fence parsed as a REAL row, so a
    # template using tildes would have given every adopter a phantom decision. The lesson generalises —
    # when a parser skips "the" delimiter, check whether the format has more than one.
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence is None and (stripped.startswith("```") or stripped.startswith("~~~")):
            fence = stripped[:3]
            out.append("")
            continue
        if fence is not None:
            out.append("")
            if stripped.startswith(fence):
                fence = None
            continue
        out.append(line)
    return "\n".join(out)


def parse_rows(text: str) -> list[dict]:
    """Split the register into rows. A row runs from its heading to the next heading."""
    rows: list[dict] = []
    matches = list(ROW_RE.finditer(text))
    for i, m in enumerate(matches):
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : body_end]
        fields: dict[str, str] = {}
        for line in body.splitlines():
            fm = FIELD_RE.match(line.strip())
            if fm:
                fields[fm.group("label").strip()] = fm.group("value").strip()
        rows.append(
            {
                "id": m.group(1),
                "num": int(m.group(1).split("-")[1]),
                "title": m.group(2),
                "fields": fields,
                "body": body,
                "line": text[: m.start()].count("\n") + 1,
            }
        )
    return rows


def scan_citations() -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    seen: set[Path] = set()
    for pattern in CITATION_GLOBS:
        for path in ROOT.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            rel = path.relative_to(ROOT)
            if set(rel.parts) & EXCLUDE_PARTS or rel == REGISTER:
                continue
            if path.name.endswith(CITATION_EXEMPT_SUFFIXES) and any(
                str(rel).startswith(d) for d in CITATION_EXEMPT_DIRS
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(strip_fences(text).splitlines(), 1):
                for num in CITATION_RE.findall(line):
                    hits.append((str(rel), lineno, f"{ID_PREFIX}-{num}"))
    return hits


def main() -> int:
    path = ROOT / REGISTER
    if not path.is_file():
        return report(
            "decision register",
            CANNOT_RUN,
            violations=[
                f"{REGISTER} does not exist, so there is nowhere to record a blocked decision.\n"
                "      Create it from docs/DECISIONS.md in this starter kit. An EMPTY register is a\n"
                "      valid and expected state — this gate passes on one and says it validated zero\n"
                "      rows. What is not valid is having no register at all, because then a blocked\n"
                "      question has nowhere to go and becomes a guess in the code."
            ],
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return report(
            "decision register",
            CANNOT_RUN,
            violations=[
                f"{REGISTER} is not valid UTF-8, so it could not be read to a verdict: {exc}.\n"
                "      This is a COULD-NOT-RUN, not a violation. The register may be entirely well-formed,\n"
                "      but a byte written under another host's default encoding (e.g. a Windows cp1252\n"
                "      em-dash, 0x97) cannot be decoded here, and a crash on read must never be reported\n"
                "      as a VIOLATED row. Re-save docs/DECISIONS.md as UTF-8."
            ],
        )
    except OSError as exc:
        return report(
            "decision register",
            CANNOT_RUN,
            violations=[
                f"{REGISTER} exists but could not be read: {exc}.\n"
                "      This is a COULD-NOT-RUN, not a violation — a register the gate cannot open (a\n"
                "      permission problem on a shared checkout, say) reaches no verdict. The citation\n"
                "      scan guards the same operation with `except OSError`; this read must too, so an\n"
                "      unreadable register is never a crash reported as a VIOLATED row."
            ],
        )

    text = strip_fences(raw)
    rows = parse_rows(text)
    violations: list[str] = []
    seen_ids: dict[str, int] = {}

    for row in rows:
        rid, fields = row["id"], row["fields"]
        where = f"{REGISTER}:{row['line']}"

        if rid in seen_ids:
            violations.append(
                f"{rid}: duplicate identifier (also at line {seen_ids[rid]}). Ids are never reused —\n"
                "      a row keeps its number for life and changes only its status. Reuse makes every\n"
                "      citation of that number ambiguous."
            )
            continue
        seen_ids[rid] = row["line"]

        status = fields.get("Status", "").strip().upper()
        if status not in STATUSES:
            violations.append(
                f"{rid} ({where}): status {status or '(missing)'!r} is not one of {sorted(STATUSES)}.\n"
                "      A third status means the register has drifted into free text, and a reader can\n"
                "      no longer tell blocked from settled at a glance."
            )
            continue

        required = REQUIRED_FIELDS_RESOLVED if status == "RESOLVED" else REQUIRED_FIELDS_OPEN
        missing = [f for f in required if not fields.get(f)]
        if missing:
            violations.append(f"{rid}: missing required field(s) {missing}")

        if status == "OPEN":
            issue = fields.get("Issue", "")
            if issue and not re.search(r"https?://\S+", issue):
                violations.append(
                    f"{rid}: the Issue field holds no URL. **This field is the delivery mechanism** —\n"
                    "      the tracker's assignment notification is what reaches a human. Without it\n"
                    "      this row has told nobody anything."
                )

            answers = fields.get("Candidate answers", "")
            if answers and not (re.search(r"\(a\)", answers) and re.search(r"\(b\)", answers)):
                violations.append(
                    f"{rid}: Candidate answers does not offer labelled options (a) and (b). A question\n"
                    "      is not an answer — state what is being chosen between."
                )

            differs = fields.get("What differs in the code", "")
            if differs and not LOCUS_RE.search(differs):
                violations.append(
                    f"{rid}: 'What differs in the code' names no concrete code locus (expected a\n"
                    "      backticked path or symbol). **This is the entry condition.** If you cannot\n"
                    "      name what would physically differ between the options, this is a TASK, not a\n"
                    "      decision, and it does not belong in this register."
                )

        if status == "RESOLVED":
            ruling = fields.get("Ruling", "").strip()
            if ruling in {"", "—", "-", "TBD", "n/a"}:
                violations.append(
                    f"{rid}: marked RESOLVED with no ruling recorded. A row closes by citing a durable,\n"
                    "      findable decision — a date or 'we agreed' is not something a later reader can\n"
                    "      look up."
                )

    known = set(seen_ids)
    for rel, lineno, cited in scan_citations():
        if cited not in known:
            violations.append(
                f"{rel}:{lineno}: cites {cited}, which is not a row in {REGISTER}. A decision cited but\n"
                "      never recorded is the exact failure this register exists to stop. Either add the\n"
                "      row, or — if you are referring to another repository's register — cite it by\n"
                "      SUBJECT and REPOSITORY, because these numbers are per-repo and they collide."
            )

    if violations:
        return report("decision register", VIOLATED, violations=violations)

    if not rows:
        return report(
            "decision register",
            VERIFIED,
            verified=[
                f"{REGISTER} holds ZERO rows, so nothing was validated — stated plainly rather than "
                "reported as though it had been checked."
            ],
            note=(
                "An empty register is a legitimate state: it means no blocked decision has been "
                "recorded yet. The citation scan still ran, so a decision cited anywhere with no row "
                "here would have failed."
            ),
        )

    open_n = sum(1 for r in rows if r["fields"].get("Status", "").upper() == "OPEN")
    return report(
        "decision register",
        VERIFIED,
        verified=[
            f"{len(rows)} row(s), {open_n} open — every one well-formed, every open row links an "
            "issue and names what differs in the code, every closed row cites a ruling, and every "
            "citation resolves."
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
