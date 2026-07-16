#!/usr/bin/env python3
"""qa/lens.py — the factory's own behavior-anchoring lens (issue #216).

Consumer content, not platform machinery: this is the factory-as-consumer's own lens,
declared via `.yr/factory.toml`'s `lens_cmd` (the seam shipped in issue #214). It reads
YR_BASE_REF (default origin/main), diffs the working tree against it, and scans only the
CHANGED test files under tests/ for four recorded species — each one a test-hygiene bug this
repo actually hit — the first three where a test checks a raw string/transport artifact instead
of the behavior it stands in for, the fourth where a test grows a private clone of a shared
test-harness fake instead of obtaining it from its shared home. Advisory only: the report is
markdown on stdout, and the exit code is always 0 regardless of what it finds (a non-zero exit
here would make the lens gate, which the seam explicitly forbids).

The species list is closed at four (no rule added without a new issue reopening this file):

  1. raw-argv/transport greps — a prompt/transcript-shaped (multi-word) literal matched with a
     bare `in` against something captured off argv/transcript, standing in for an assertion on
     actual behavior (an exit code, a written artifact, a stage outcome).
  2. byte-exact fixture strings encoding transport artifacts — an expected literal keeps a
     trailing newline that the bash command-substitution `$(...)` capturing the compared value
     unconditionally strips (the 2026-07-10 #121-rebuild exhibit: `SPEC="$(printf ... "$BODY")"`
     silently drops trailing whitespace, so a fixture that still expects it never reflects what
     the transport actually delivers).
  3. marker substrings unanchored to a line — a recorded protocol marker (e.g. `VERDICT:`) tested
     with a bare `in` instead of line-anchored (`str.startswith` on a split line, or a
     `^`-anchored regex), so a prose mention of the marker would pass the same as the real thing.

Issue #246 reopened the list (it had been closed at three) to add species 4:

  4. clone-accretion — a private, from-scratch re-implementation of a shared test-harness fake (the
     `claude` stage classifier or the `gh` CLI dispatcher) defined beside `tests/harness/claude_fake.py`
     / `tests/harness/gh_fake.py` instead of being obtained from there — imported directly, or derived
     via `.replace()` (never retyped). Detected with the same full-reimplementation fingerprint the
     harness's own migration acceptance tests already use to prove no clone survives
     (tests/harness/test_shared_fake_migration.py, tests/harness/test_gh_fake_migration.py): a plain
     (non-derived) module-level string literal carrying the claude classifier's four routing literals,
     or the gh dispatcher's bash/python catch-all shape.

Each finding is heuristic and errs toward silence: the graduation evidence base this script ships
with (tests/test_qa_lens.py, independently authored) is what earns any future tightening.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SPECIES_ALTERNATIVE = {
    "raw-argv-transport-grep": (
        "assert the observable behavior (an exit code, a written artifact, a stage outcome) "
        "instead of grepping a prompt/transcript literal off captured argv/transcript content"
    ),
    "byte-exact-transport-artifact": (
        "reconstruct the expected value from the same source of truth the transport reads from, "
        "with the same trailing-newline handling — not a hand-copied literal"
    ),
    "unanchored-marker-substring": (
        "line-anchor the marker check (str.startswith on a split line, or a ^-anchored regex) "
        "instead of a bare `in` containment test"
    ),
    "clone-accretion": (
        "obtain the fake from tests/harness/claude_fake.py or tests/harness/gh_fake.py — import the "
        "shared constant directly, or derive a variant via .replace() — instead of retyping a private "
        "copy of it"
    ),
}

_TRANSPORT_NAME_RE = re.compile(r"argv|transcript", re.IGNORECASE)
_MARKER_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,40}:$")

# tests/harness/{claude_fake,gh_fake}.py ARE the shared home the clone-accretion species is defined
# relative to — the species detects a SECOND definition beside them, so the shared home's own
# constants (which of course carry the fingerprint below) are excluded from this species by path.
_HARNESS_HOME_FILES = {"tests/harness/claude_fake.py", "tests/harness/gh_fake.py"}

# the exact fingerprints tests/harness/test_shared_fake_migration.py and
# tests/harness/test_gh_fake_migration.py already use to prove no private clone of either shared fake
# survives anywhere in tests/ — reused here rather than re-derived, so this species agrees with the
# harness's own clone census by construction.
_CLAUDE_ROUTING_LITERALS = ("*REVIEWER*", '*"REQUESTED CHANGES"*', "*TESTER*", '*"tests FAIL"*')


def _is_claude_classifier_reimplementation(text):
    return 'case "$args" in' in text and all(lit in text for lit in _CLAUDE_ROUTING_LITERALS)


def _is_bash_gh_reimplementation(text):
    return ('case "$1" in' in text and 'pr)' in text
            and 'echo "unhandled gh $*" >&2; exit 9' in text)


def _is_python_gh_reimplementation(text):
    return 'argv[:2] == ["api", "graphql"]' in text and "sys.exit(9)" in text


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    species: str

    @property
    def alternative(self):
        return SPECIES_ALTERNATIVE[self.species]


def _link_parents(tree):
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node


def _is_negated(node, boundary):
    """True if a UnaryOp(Not) sits between `node` and `boundary` (exclusive/inclusive of
    boundary) — catches `not (X in Y)` and `not any(X in Y for ...)`, which `ops=[In]` alone
    (excluding the direct `X not in Y` form, already a different op) doesn't."""
    cur = getattr(node, "parent", None)
    while cur is not None:
        if isinstance(cur, ast.UnaryOp) and isinstance(cur.op, ast.Not):
            return True
        if cur is boundary:
            return False
        cur = getattr(cur, "parent", None)
    return False


def _str_const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _in_compares(test_node):
    """Every `Compare` node inside an assert's test expression using exactly a single `in`."""
    for node in ast.walk(test_node):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
            yield node


def _scan_raw_argv_transport_grep(path, source, asserts):
    findings = []
    for a in asserts:
        for cmp in _in_compares(a.test):
            literal = _str_const(cmp.left)
            if literal is None or len(literal.split()) < 2:      # prose-shaped: >=2 words
                continue
            if _is_negated(cmp, a):
                continue
            right = cmp.comparators[0]
            # a dict/record subscript (e.g. record["shadow_transcript"]) is a structured field
            # read, not a raw capture handle — only a bare name/attribute/call reads as "this IS
            # the captured argv/transcript text", so subscripts are excluded from the name match.
            if isinstance(right, ast.Subscript):
                continue
            right_src = ast.get_source_segment(source, right) or ""
            if _TRANSPORT_NAME_RE.search(right_src):
                findings.append(Finding(path, a.lineno, "raw-argv-transport-grep"))
    return findings


def _scan_unanchored_marker_substring(path, source, asserts):
    findings = []
    for a in asserts:
        for cmp in _in_compares(a.test):
            literal = _str_const(cmp.left)
            if literal is None or not _MARKER_RE.match(literal):
                continue
            if _is_negated(cmp, a):
                continue
            findings.append(Finding(path, a.lineno, "unanchored-marker-substring"))
    return findings


def _scan_byte_exact_transport_artifact(path, source, asserts, func_of):
    findings = []
    seg_cache = {}
    for a in asserts:
        test = a.test
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
            continue
        operands = [test.left, test.comparators[0]]
        if not any((_str_const(o) or "").endswith("\n") for o in operands if _str_const(o) is not None):
            continue
        func = func_of.get(id(a))
        if func is None:
            continue
        if id(func) not in seg_cache:
            seg = ast.get_source_segment(source, func) or ""
            seg_cache[id(func)] = "$(" in seg
        if seg_cache[id(func)]:
            findings.append(Finding(path, a.lineno, "byte-exact-transport-artifact"))
    return findings


def _scan_clone_accretion(path, tree):
    if path in _HARNESS_HOME_FILES:
        return []
    findings = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            continue
        text = node.value.value
        if (_is_claude_classifier_reimplementation(text)
                or _is_bash_gh_reimplementation(text)
                or _is_python_gh_reimplementation(text)):
            findings.append(Finding(path, node.lineno, "clone-accretion"))
    return findings


def scan_text(path, source):
    """Every finding (list[Finding]) across the four closed species in one file's source text.

    Pure and side-effect-free — the same function the corpus/fixture proofs in
    tests/test_qa_lens.py call directly, independent of git or stdout.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    _link_parents(tree)

    asserts = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    func_of = {}
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(func):
            if isinstance(n, ast.Assert) and id(n) not in func_of:
                func_of[id(n)] = func

    findings = []
    findings.extend(_scan_raw_argv_transport_grep(path, source, asserts))
    findings.extend(_scan_byte_exact_transport_artifact(path, source, asserts, func_of))
    findings.extend(_scan_unanchored_marker_substring(path, source, asserts))
    findings.extend(_scan_clone_accretion(path, tree))
    return sorted(findings, key=lambda f: (f.lineno, f.species))


def changed_test_files(base_ref, root):
    """Changed `tests/*.py` paths (repo-relative) per `git diff --name-only <base_ref>` — the
    working tree against base_ref, so it sees both committed and uncommitted changes. Any git
    failure (no such ref, not a repo) fails open to an empty list — advisory, never fatal."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [
        line.strip() for line in result.stdout.splitlines()
        if line.strip().startswith("tests/") and line.strip().endswith(".py")
    ]


def render(findings):
    """Markdown report, or "" when there's nothing to say (the runner posts a PR comment only
    when the artifact is non-empty — so silence here means no comment, not a stray empty one)."""
    if not findings:
        return ""
    lines = ["## factory lens — advisory findings (issue #216)", ""]
    for f in findings:
        lines.append(f"- `{f.path}:{f.lineno}` — **{f.species}**: {f.alternative}")
    return "\n".join(lines) + "\n"


def run(base_ref, root):
    findings = []
    for relpath in changed_test_files(base_ref, root):
        p = root / relpath
        if not p.is_file():
            continue
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(relpath, source))
    return findings


def main(argv=None):
    base_ref = os.environ.get("YR_BASE_REF") or "origin/main"
    root = Path.cwd()
    report = render(run(base_ref, root))
    if report:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
