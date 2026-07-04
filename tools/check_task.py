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
# a line naming the task's own deliverable — optional bullet/bold, then `Deliverable:` / `Creates:`
_DELIVERABLE_RE = re.compile(r"^\s*[-*\s]*(?:deliverable|creates)\s*\**\s*:", re.IGNORECASE)


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
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    errors = check_task(text, repo_root=args.repo_root, base_ref=args.base_ref)
    for e in errors:
        print(f"{args.file}: {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
