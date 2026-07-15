#!/usr/bin/env python3
"""check_model_refs — fail loud on un-allowlisted occurrences of the vault 01-conventions name.

Any file that names 01-conventions (bare or as its full vault path) as the living documentation
model is a stale reference. This scanner keeps that guard permanent: exit 0 when clean, exit 1
(with `<file>:<lineno>: <message>` lines) when any un-allowlisted hit remains.

Frozen bench evidence (tools.textutil.is_frozen_bench_evidence) is skipped: those surfaces embed
past PRs' file contents verbatim by design, so this living-text guard must not read them.

Usage: check_model_refs.py [--scan-root DIR]
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.textutil import is_frozen_bench_evidence

# Every line containing this substring is a potential hit
_PATTERN = "01-conventions"

# Directories that are never scanned
_SKIP_DIRS = frozenset({".git", ".venv", "node_modules"})

# File extensions that cannot contain a text reference
_BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".pyc"})

# Files skipped entirely (relative to scan-root, forward-slash separated).
# These contain the literal by construction (this scanner + its test) or as a
# legitimate absence-guard (the router test).
_SKIP_FILES = frozenset({
    "tools/check_model_refs.py",
    "tests/test_check_model_refs.py",
    "tests/test_skill_factory_router.py",
})

# Lines containing any of these substrings are individually allowlisted.
# Used for the origin note in documentation-model.md (lineage; must stay).
_ALLOWLISTED_LINE_SUBSTRINGS = frozenset({
    "Relocated from the vault `01-conventions`",
})


def _rel(path, root):
    return str(path.relative_to(root)).replace("\\", "/")


def scan(scan_root):
    """Yield (rel_path, lineno, line) for every un-allowlisted hit."""
    root = pathlib.Path(scan_root).resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in parts):
            continue
        if path.suffix in _BINARY_SUFFIXES:
            continue
        rel = _rel(path, root)
        if rel in _SKIP_FILES:
            continue
        if is_frozen_bench_evidence(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _PATTERN not in line:
                continue
            if any(s in line for s in _ALLOWLISTED_LINE_SUBSTRINGS):
                continue
            yield rel, lineno, line.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail loud on un-allowlisted 01-conventions occurrences."
    )
    ap.add_argument(
        "--scan-root",
        default=str(pathlib.Path(__file__).resolve().parents[1]),
        help="root directory to scan (default: repo root)",
    )
    args = ap.parse_args(argv)
    errors = False
    for rel, lineno, line in scan(args.scan_root):
        print(f"{rel}:{lineno}: un-allowlisted '01-conventions' reference: {line!r}")
        errors = True
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
