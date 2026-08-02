#!/usr/bin/env python3
"""qa/cardinality.py — declarative cardinality guards (it-27 § 4, issue #365).

Consumer content, not platform machinery — the same home and shape as `qa/lens.py`: this repo
declares its own rules in `qa/cardinality.toml` and carries the runner through `.yr/factory.toml`'s
`lint_cmd`. Another repo copies the shape and writes its own rules; the factory ships no rule that
assumes a language, a file layout, or a toolchain (it-27's repo-agnostic invariant).

WHY THIS EXISTS. A tech-debt round that fixes four shapes and ships no enforcement buys one
iteration of cleanliness at the cost of a full census. it-27 § 4's wall is that every prune slice
ships a guard making its own finding non-recurring, and for the duplication class the instrument is
a **cardinality guard**: count the lines matching a pattern on a named surface, assert the count
does not exceed a declared maximum. Deterministic by construction — a count against a threshold, no
judgement. Its honest limit is that it pins only shapes already NAMED, which is why discovery stays
a separate instrument.

THE TWO-PART RULE it enforces on itself (it-27 § 4):
  - derive the expected set from the tree, never enumerate the offenders; and
  - name the SURFACE the assertion reads. `paths` is that surface, and a rule that cannot name one
    cannot be declared. This is why the enumeration below is `git ls-files` — the TRACKED tree —
    rather than a filesystem walk: a walk picks up sibling checkouts under `.claude/worktrees/`
    and makes the verdict depend on what else happens to be on disk. That is not hypothetical; it
    is a live defect in another guard in this repo, and repeating it here would be writing the bug
    the instrument exists to stop.

BEHAVIOUR, and why each branch is what it is:
  - count > max  -> exit 1, naming the pattern, the count found, the maximum declared and the
    reason recorded for it (it-27's acceptance criterion for the failure), then the matching
    file:line list so the failure is actionable without re-running anything.
  - count == max -> silent pass.
  - count <  max -> ONE advisory line on stdout, exit 0. A ceiling, like a floor, otherwise stays
    green forever after a consolidation and never records that the consolidation happened — the
    exact rot this repo's `assert int(match.group(1)) > 63` README floor demonstrates. Advisory
    rather than gating because the criterion's condition is "IF a declared cardinality is
    EXCEEDED", and tightening a stale ceiling is a decision, not an error.

Stdlib only, like its sibling tools. Usage: `python3 qa/cardinality.py [config.toml]`.
"""

import fnmatch
import pathlib
import re
import subprocess
import sys
import tomllib

REQUIRED_FIELDS = ("id", "pattern", "paths", "max", "reason", "birth")
DEFAULT_CONFIG = "qa/cardinality.toml"
# Only ever used when the tree is not a git checkout (a `git archive` extraction). Kept in step with
# the reason above: never walk into a sibling checkout or a virtualenv.
_WALK_EXCLUDE = {".git", ".venv", "node_modules", ".claude", "__pycache__"}


class ConfigError(Exception):
    """A rule that cannot be trusted to mean anything. Always fatal — never a skipped rule."""


def load_rules(path):
    """Parse and validate the rule set. Fail-closed on ANY missing or empty required field.

    A rule with no `reason` cannot satisfy the failure criterion (which requires the failure to
    name the reason recorded for it), and a rule with no `birth` is one nobody can ever retire —
    the walls' birth-citation rule applied to guards. So neither is optional, and a malformed rule
    set refuses the whole run rather than silently enforcing the subset that happens to parse.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise ConfigError(f"{path}: no such config file")
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: not parseable as TOML — {exc}") from exc

    rules = data.get("rule")
    if not isinstance(rules, list) or not rules:
        raise ConfigError(f"{path}: declares no [[rule]] tables")

    seen = set()
    for idx, rule in enumerate(rules):
        where = f"{path}: rule #{idx + 1}"
        for field in REQUIRED_FIELDS:
            if field not in rule:
                raise ConfigError(f"{where}: missing required field `{field}`")
        rid = rule["id"]
        if not isinstance(rid, str) or not rid.strip():
            raise ConfigError(f"{where}: `id` must be a non-empty string")
        if rid in seen:
            raise ConfigError(f"{path}: duplicate rule id `{rid}` — ids key the failure message")
        seen.add(rid)
        for field in ("pattern", "reason", "birth"):
            if not isinstance(rule[field], str) or not rule[field].strip():
                raise ConfigError(f"{path}: rule `{rid}`: `{field}` must be a non-empty string")
        if not isinstance(rule["paths"], list) or not rule["paths"]:
            raise ConfigError(f"{path}: rule `{rid}`: `paths` must be a non-empty list of globs")
        for glob in rule["paths"]:
            if not isinstance(glob, str) or not glob.strip():
                raise ConfigError(f"{path}: rule `{rid}`: every entry in `paths` must be a glob")
            if glob.startswith("/") or ".." in glob:
                raise ConfigError(
                    f"{path}: rule `{rid}`: `paths` entries are repo-relative and may not be "
                    f"absolute or contain `..` — got {glob!r}"
                )
        if not isinstance(rule["max"], int) or isinstance(rule["max"], bool) or rule["max"] < 0:
            raise ConfigError(f"{path}: rule `{rid}`: `max` must be a non-negative integer")
        try:
            re.compile(rule["pattern"])
        except re.error as exc:
            raise ConfigError(f"{path}: rule `{rid}`: `pattern` is not a valid regex — {exc}") from exc
    return rules


def tracked_files(root):
    """Every in-scope path, repo-relative. Falls back to a filtered walk outside a git checkout.

    `--cached --others --exclude-standard` — tracked files PLUS untracked-but-not-ignored ones,
    and this is load-bearing rather than a convenience. The tier that carries this runner runs
    BEFORE the commit, so a file the implementer just created is untracked at scan time. A
    `git ls-files` with no `--others` would make the guard blind to exactly the new code it
    exists to check: the ninth copy of a contract, in a brand-new file, would sail through and
    only become visible one commit too late. `--exclude-standard` keeps .gitignore honoured, so
    build artifacts and virtualenvs still never enter the surface.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True).stdout
        files = [f for f in out.split("\0") if f]
        if files:
            return files, "git ls-files (tracked + untracked, .gitignore honoured)"
    except (OSError, subprocess.CalledProcessError):
        pass
    files = []
    for p in sorted(pathlib.Path(root).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in _WALK_EXCLUDE for part in rel.parts):
            continue
        files.append(str(rel))
    return files, "filesystem walk (not a git checkout)"


def matches_for(rule, files, root):
    """[(path, lineno, line)] for every line matching `rule` on `rule`'s declared surface."""
    pattern = re.compile(rule["pattern"])
    surface = [f for f in files if any(fnmatch.fnmatch(f, g) for g in rule["paths"])]
    hits = []
    for rel in surface:
        try:
            text = (pathlib.Path(root) / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue          # a binary or unreadable file cannot carry a text pattern
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append((rel, lineno, line.strip()))
    return hits


def evaluate(rules, files, root):
    """(failures, advisories) — failures are rules over their max, advisories rules under it."""
    failures, advisories = [], []
    for rule in rules:
        hits = matches_for(rule, files, root)
        if len(hits) > rule["max"]:
            failures.append((rule, hits))
        elif len(hits) < rule["max"]:
            advisories.append((rule, hits))
    return failures, advisories


def main(argv):
    root = pathlib.Path(__file__).resolve().parents[1]
    config = argv[1] if len(argv) > 1 else str(root / DEFAULT_CONFIG)
    try:
        rules = load_rules(config)
    except ConfigError as exc:
        print(f"cardinality: {exc}", file=sys.stderr)
        return 2                      # a rule set that cannot be trusted never silently passes

    files, source = tracked_files(root)
    failures, advisories = evaluate(rules, files, root)

    for rule, hits in advisories:
        print(f"cardinality: rule `{rule['id']}` declares max {rule['max']}, found {len(hits)} — "
              f"the declared max is stale; tighten it or record why the slack is intended")

    if not failures:
        return 0

    for rule, hits in failures:
        print(f"cardinality: rule `{rule['id']}` FAILED", file=sys.stderr)
        print(f"  pattern:  {rule['pattern']}", file=sys.stderr)
        print(f"  found:    {len(hits)}", file=sys.stderr)
        print(f"  maximum:  {rule['max']}", file=sys.stderr)
        print(f"  reason:   {rule['reason']}", file=sys.stderr)
        print(f"  birth:    {rule['birth']}", file=sys.stderr)
        print(f"  surface:  {', '.join(rule['paths'])}  (enumerated by {source})", file=sys.stderr)
        for rel, lineno, line in hits:
            print(f"    {rel}:{lineno}: {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
