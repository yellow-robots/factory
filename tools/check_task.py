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
                         failures).

Usage: check_task.py <task.md> [--repo-root DIR] [--base-ref REF]
Exit 0 if self-contained; 1 (with `<file>: <message>` lines) otherwise.
"""
import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.textutil import split_frontmatter

BUILD_CRITICAL = ("goal", "acceptance criteria", "context & links", "test expectations")
_WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
_EXT_RE = re.compile(r"/[^/]*\.[A-Za-z0-9]+$")   # last path segment carries a file extension


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
    without losing a genuine citation.
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


def check_task(text, *, repo_root, base_ref=None, path_exists=None):
    """Return error messages (list[str]) for self-containment failures; [] ⇒ build-ready.

    `path_exists(path) -> bool` is injectable (default checks the working tree, or `base_ref` via git).
    """
    _, body = split_frontmatter(text)
    sections = _sections(body)
    exists = path_exists or (lambda p: _path_exists(p, repo_root, base_ref))
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
        for token in _BACKTICK_RE.findall(content):
            path = _pathify(token)
            if path and not exists(path):
                errors.append(f"cited path `{path}` does not exist"
                              + (f" at {base_ref}" if base_ref else ""))
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail loud when a Ready task isn't self-contained.")
    ap.add_argument("file", help="the task markdown (the authoring aid, or the Issue body saved to a file)")
    ap.add_argument("--repo-root", default=".", help="the target repo working tree")
    ap.add_argument("--base-ref", default=None, help="check cited paths at this git ref instead of the tree")
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    errors = check_task(text, repo_root=args.repo_root, base_ref=args.base_ref)
    for e in errors:
        print(f"{args.file}: {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
