#!/usr/bin/env python3
"""check_task — fail loud when a Ready task Issue isn't self-contained enough to build.

A task at the bottom of the upper pipeline must stand alone: the lower-pipeline builder implements from
the Issue body ALONE and never opens Obsidian (RFC 0005). This checks the *necessary* conditions for
that — deterministic, fail-loud, and meant to inform the human "promote to Ready" gate (it is NOT a
sufficiency judge: whether the inlined context is *enough* to build stays an LLM-as-judge, deferred to
the v2 eval harness).

Three checks over the build-critical body sections (Goal, Acceptance criteria, Context & links, Test
expectations) — frontmatter is provenance and is ignored:
  1. slice present     — "Context & links" carries real content (the technical-RFC slice), not an
                         empty placeholder.
  2. no Obsidian pointer — no `[[wikilink]]` or `obsidian://` URL in a build-critical section (the dev
                         can't follow it).
  3. cited paths exist — every backtick-quoted repo *file* path resolves in the target repo (at
                         `--base-ref` if given, else the working tree). A path = has '/', no spaces,
                         and a file extension on its last segment. Bare filenames, command spans, git
                         refs (`origin/main`), scoped packages (`@scope/pkg`), host/URL fragments, and
                         host paths (`~/…`, `/…`) are skipped (ambiguous or not-a-file → no false
                         failures). Two further rules keep this fail-loud without flagging legitimate
                         citations (the #24/#31 false-positive tally):
                           a. own deliverable — a path cited on a line starting with a `Deliverable:`
                              or `Creates:` marker (optionally bulleted/bolded, e.g. "- **Deliverable:**
                              `tools/x.py`") is exempt: the task is naming the file IT will create, so
                              it can't exist yet. The same path cited elsewhere in the body, off a
                              marker line, is a plain reference and is still checked.
                           b. subtree-relative citation — when root-relative resolution fails, the path
                              is retried as a suffix against every file in the repo tree (e.g.
                              `references/closing.md` matching `skills/factory/references/closing.md`).
                              Exactly one match resolves it; zero or two-or-more still errors (the
                              latter names every candidate — genuinely ambiguous).

A fourth, advisory pass — the pin-collision check — runs alongside the three above but never fails the
gate: `pin_collision_warnings` extracts candidate literals from the draft's acceptance criteria
(backtick-quoted spans of length ≥3 containing at least one non-letter character — catches `.05`,
`70% 46%`, `inset:-40%`; skips prose words), then greps the target repo's declared test surface
(`test_paths` from `.yr/factory.toml`, default `tests/`, plus `qa/` when present) at the same ref/tree
`check_task` reads. A file that contains a criteria literal, when the draft body never names that file
anywhere, yields a WARNING line naming both — a standing test may already pin the very literal a fresh
draft's criteria are about to change out from under it (website#122 run `122-888903`: four
undispositioned pin suites made a build unwinnable). Exit stays 0 for this pass alone (the lens-tier /
check_supersession advisory precedent — reading warnings before promoting is attended practice, not
wiring); the CLI's `--strict` flag upgrades a non-empty warning list to exit 1.

Usage: check_task.py <task.md> [--repo-root DIR] [--base-ref REF] [--strict]
Exit 0 if self-contained (and, absent --strict, regardless of pin-collision warnings); 1 (with
`<file>: <message>` lines) on a self-containedness failure, or (with --strict) on any pin-collision
warning too.
"""
import argparse
import pathlib
import re
import subprocess
import sys
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.textutil import split_frontmatter

BUILD_CRITICAL = ("goal", "acceptance criteria", "context & links", "test expectations")
_WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
_EXT_RE = re.compile(r"/[^/]*\.[A-Za-z0-9]+$")   # last path segment carries a file extension
# a line naming the task's own deliverable — optional bullet/bold, then `Deliverable:` / `Creates:`
_DELIVERABLE_RE = re.compile(r"^\s*[-*\s]*(?:deliverable|creates)\s*\**\s*:", re.IGNORECASE)
DEFAULT_TEST_PATHS = ["tests/"]


def _strip_comments(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)


def _sections(body):
    """Map level-2 heading (lowercased) → its content. Deeper headings stay as content."""
    sections, current, buf = {}, None, []
    for line in body.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf)
            current, buf = m.group(1).strip().lower(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def _pathify(token):
    """A backtick span → a repo *file* path to check, or None.

    A path has '/', no spaces, and a file extension on its final segment (`site/index.html`,
    `tools/x.py`, `.yr/factory.toml`; any `:NN`/`:NN-MM` line suffix is dropped first). Every real
    task citation is repo-relative, so requiring an extension skips the look-alikes that aren't repo
    files to resolve — git refs (`origin/main`), scoped npm packages (`@scope/pkg`), host/URL
    fragments (`example.com/a/b`), and host paths (`~/…`, `/…`) — killing those false positives
    without losing a genuine citation. This only filters the token shape; whether the resulting path
    must already exist is decided later — see `check_task`'s deliverable-marker and suffix-match rules.
    """
    token = _LINE_SUFFIX_RE.sub("", token.strip())
    if " " in token or "/" not in token:
        return None
    if token.startswith("@") or "://" in token:   # scoped npm package / URL — not a repo path
        return None
    if token.startswith("~/") or token.startswith("/"):   # home/absolute — a host path, not repo-relative
        return None
    if not _EXT_RE.search(token):                  # git ref, host fragment — no file extension
        return None
    return token


def _path_exists(path, repo_root, base_ref):
    if base_ref:
        return subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", f"{base_ref}:{path}"],
            capture_output=True).returncode == 0
    return (pathlib.Path(repo_root) / path).exists()


def _repo_files(repo_root, base_ref):
    """Every file path in the target repo tree, forward-slash relative — for suffix resolution.

    At `base_ref`, lists the git tree (`ls-tree -r`, empty on any git failure); otherwise walks the
    working tree, skipping `.git`. Directories are excluded — only files are citable.
    """
    if base_ref:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-tree", "-r", "--name-only", base_ref],
            capture_output=True, text=True)
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line]
    root = pathlib.Path(repo_root)
    if not root.is_dir():
        return []
    return [
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts
    ]


def _suffix_matches(path, repo_files):
    """Repo files this subtree-relative `path` could mean: exact suffix on a path-segment boundary.

    `references/closing.md` matches `skills/factory/references/closing.md` (suffix after a `/`) but not
    `other-references/closing.md` (mid-segment). Exactly one hit ⇒ resolvable; anything else ⇒ not.
    """
    suffix = "/" + path
    return sorted(f for f in repo_files if f.endswith(suffix))


# --- pin-collision advisory ---------------------------------------------------------------------------

def _read_file(path, repo_root, base_ref):
    """`path`'s text at `base_ref` (via `git show`) or the working tree; None if unreadable."""
    if base_ref:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{base_ref}:{path}"],
            capture_output=True)
        return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else None
    try:
        return (pathlib.Path(repo_root) / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_test_paths(repo_root, base_ref):
    """The target repo's declared `test_paths` (`.yr/factory.toml`, at the same ref `check_task` reads),
    or `DEFAULT_TEST_PATHS` when the manifest is absent, unparseable, or doesn't declare a well-formed
    list — this advisory pass never fails closed on a manifest problem; that is `dev-runner.sh`'s job."""
    text = _read_file(".yr/factory.toml", repo_root, base_ref)
    if text is None:
        return list(DEFAULT_TEST_PATHS)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return list(DEFAULT_TEST_PATHS)
    v = data.get("test_paths")
    if isinstance(v, list) and v and all(isinstance(x, str) and x for x in v):
        return v
    return list(DEFAULT_TEST_PATHS)


def _pin_literals(criteria_text):
    """Candidate pin literals in an acceptance-criteria section: backtick spans of length ≥3 containing
    at least one non-letter character (`.05`, `70% 46%`, `inset:-40%`), in first-seen order, deduped —
    a plain-letters backtick span (a prose word, a bare identifier) is never a candidate."""
    seen = []
    for token in _BACKTICK_RE.findall(criteria_text):
        if len(token) >= 3 and any(not c.isalpha() for c in token) and token not in seen:
            seen.append(token)
    return seen


def _test_surface_files(repo_root, base_ref):
    """Repo files under the declared test surface: `test_paths` (default `tests/`) plus `qa/` when that
    directory is present in the tree — both judged at the same ref/tree `_repo_files` reads."""
    all_files = _repo_files(repo_root, base_ref)
    dirs = list(_read_test_paths(repo_root, base_ref))
    if any(f.startswith("qa/") for f in all_files) and "qa/" not in dirs:
        dirs.append("qa/")
    return [f for f in all_files if any(f.startswith(d) for d in dirs)]


def pin_collision_warnings(text, *, repo_root, base_ref=None, read_file=None):
    """Return WARNING strings (list[str]; [] ⇒ clean) — advisory only, never a self-containedness error.

    For each candidate literal in the draft's acceptance criteria (`_pin_literals`), greps the target
    repo's test surface (`_test_surface_files`) at `base_ref`/the working tree: a file containing the
    literal, when the draft body (anywhere, not just acceptance criteria) never names that file, is a
    hit — a standing test may already pin the very literal this draft's criteria are about to change out
    from under it. `read_file(path) -> str | None` is injectable (default: `_read_file`).
    """
    _, body = split_frontmatter(text)
    sections = _sections(body)
    criteria = _strip_comments(sections.get("acceptance criteria", ""))
    literals = _pin_literals(criteria)
    if not literals:
        return []
    read = read_file or (lambda p: _read_file(p, repo_root, base_ref))
    warnings = []
    for f in _test_surface_files(repo_root, base_ref):
        if f in body:
            continue
        content = read(f)
        if content is None:
            continue
        for literal in literals:
            if literal in content:
                warnings.append(f"WARNING: `{f}` contains acceptance-criteria literal `{literal}`, "
                                 f"but the task body never names {f}")
    return warnings


def check_task(text, *, repo_root, base_ref=None, path_exists=None):
    """Return error messages (list[str]) for self-containment failures; [] ⇒ build-ready.

    `path_exists(path) -> bool` is injectable (default checks the working tree, or `base_ref` via git).
    A cited path that fails `path_exists` gets two more chances before it's reported missing:
      1. deliverable marker — cited on a `Deliverable:`/`Creates:` line ⇒ exempt (the task's own
         not-yet-built output; the same string cited elsewhere without the marker is NOT exempt).
      2. subtree-relative suffix — a *unique* repo file ending in `/<path>` ⇒ resolved; zero or
         multiple hits ⇒ still an error (multiple names every candidate).
    """
    _, body = split_frontmatter(text)
    sections = _sections(body)
    exists = path_exists or (lambda p: _path_exists(p, repo_root, base_ref))
    repo_files_cache = None

    def repo_files():
        nonlocal repo_files_cache
        if repo_files_cache is None:
            repo_files_cache = _repo_files(repo_root, base_ref)
        return repo_files_cache

    errors = []

    ctx = _strip_comments(sections.get("context & links", "")).strip()
    if not ctx:
        errors.append("Context & links is empty — paste the technical-RFC slice "
                      "(the task must be self-contained)")

    for name in BUILD_CRITICAL:
        content = _strip_comments(sections.get(name, ""))
        for hit in _WIKILINK_RE.findall(content):
            errors.append(f"build-critical section '{name}' contains an Obsidian pointer {hit} — "
                          f"inline it; a dev never opens Obsidian")
        if "obsidian://" in content:
            errors.append(f"build-critical section '{name}' contains an obsidian:// link — "
                          f"inline it; a dev never opens Obsidian")
        for line in content.split("\n"):
            is_deliverable = bool(_DELIVERABLE_RE.match(line))
            for token in _BACKTICK_RE.findall(line):
                path = _pathify(token)
                if not path or exists(path) or is_deliverable:
                    continue
                candidates = _suffix_matches(path, repo_files())
                if len(candidates) == 1:
                    continue
                where = f" at {base_ref}" if base_ref else ""
                if len(candidates) > 1:
                    errors.append(f"cited path `{path}` does not exist{where} and is an ambiguous "
                                  f"subtree suffix — matches {', '.join(candidates)}")
                else:
                    errors.append(f"cited path `{path}` does not exist{where}")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail loud when a Ready task isn't self-contained.")
    ap.add_argument("file", help="the task markdown (the authoring aid, or the Issue body saved to a file)")
    ap.add_argument("--repo-root", default=".", help="the target repo working tree")
    ap.add_argument("--base-ref", default=None, help="check cited paths at this git ref instead of the tree")
    ap.add_argument("--strict", action="store_true",
                    help="upgrade pin-collision warnings to exit 1 (default: advisory, exit 0)")
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    errors = check_task(text, repo_root=args.repo_root, base_ref=args.base_ref)
    for e in errors:
        print(f"{args.file}: {e}")
    warnings = pin_collision_warnings(text, repo_root=args.repo_root, base_ref=args.base_ref)
    for w in warnings:
        print(w)
    if errors:
        return 1
    return 1 if warnings and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
