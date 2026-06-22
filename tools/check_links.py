#!/usr/bin/env python3
"""check_links — fail loud when a pipeline artifact's `source_*` crossing-links don't resolve.

The upper pipeline keeps product docs (intent / spec / feature-RFC) in the Obsidian vault and the
build surface (brief / task / PR) on GitHub. That split is only safe if a crossing-link that does NOT
resolve stops the workflow *visibly and loudly* (Jose's principle). This checks exactly the `source_*`
frontmatter fields of one artifact — NOT the whole vault (the vault has many intentional dangling
wikilinks; scope is the pipeline's crossing-links only).

Resolution by the link's target home:
  - `[[wikilink]]`              → resolved against the vault filesystem (an explicit vault-relative
                                  path, or a unique basename match). Unresolved / ambiguous / an
                                  unfilled `<placeholder>` → error. This is the fail-loud guarantee.
  - `#NN` / `owner/repo#NN` / `http(s)://…` → a GitHub-side ref. Format-checked here; network-resolved
                                  only when a resolver is supplied (the CLI wires `gh`; `--no-gh` skips
                                  it). The builder never follows `source_*` (tasks are self-contained),
                                  so format is the floor and live resolution the bonus.

Usage: check_links.py <artifact.md> [--vault-root DIR] [--no-gh]
Exit 0 if every crossing-link resolves; 1 (with `<file>: <message>` lines) otherwise.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.textutil import split_frontmatter

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT", "/srv/obsidian/vaults/obsidian")
_ISSUE_RE = re.compile(r"^([\w.-]+/[\w.-]+)?#\d+$")


def _classify(value):
    """Return (kind, target) for a raw source_* value."""
    v = value.strip()
    if "<" in v or ">" in v:
        return "placeholder", v
    if v.startswith("[[") and v.endswith("]]"):
        return "wikilink", v[2:-2].strip()
    if v.startswith("http://") or v.startswith("https://"):
        return "url", v
    if _ISSUE_RE.match(v):
        return "issue", v
    return "unknown", v


def _resolve_wikilink(target, vault_root):
    """(ok, detail) — resolve a wikilink target against the vault filesystem.

    Resolves by explicit vault-relative path when the target contains '/', else by a UNIQUE basename
    match (zero → unresolved, many → ambiguous: we never silently pick one). Matches inside dot-dirs
    (.trash, .obsidian) don't count.
    """
    target = target.split("#", 1)[0].split("|", 1)[0].strip()
    if not target:
        return False, "empty wikilink target"
    name = target if target.endswith(".md") else target + ".md"
    if "/" in target:
        p = vault_root / name
        return (p.is_file(), str(p))
    matches = [m for m in vault_root.rglob(name)
               if not any(part.startswith(".") for part in m.relative_to(vault_root).parts)]
    if len(matches) == 1:
        return True, str(matches[0])
    if not matches:
        return False, f"no file named {name!r} in vault"
    return False, f"ambiguous: {len(matches)} files named {name!r}"


def check_links(text, *, vault_root, resolve_ref=None):
    """Return error messages (list[str]) for unresolved source_* crossing-links; [] ⇒ all resolve.

    `resolve_ref(kind, target) -> bool` (optional) network-resolves #issue/URL refs; without it those
    are only format-checked. `vault_root` is a pathlib.Path to the Obsidian vault.
    """
    meta, _ = split_frontmatter(text)
    errors = []
    for key, value in meta.items():
        if not key.startswith("source_"):
            continue
        for v in (value if isinstance(value, list) else [value]):
            v = (v or "").strip()
            if v == "":
                errors.append(f"{key}: empty crossing-link — a source_* must resolve or be removed")
                continue
            kind, target = _classify(v)
            if kind == "placeholder":
                errors.append(f"{key}: {v} looks like an unfilled placeholder")
            elif kind == "wikilink":
                ok, detail = _resolve_wikilink(target, vault_root)
                if not ok:
                    errors.append(f"{key}: unresolved wikilink [[{target}]] — {detail}")
            elif kind in ("issue", "url"):
                if resolve_ref is not None and not resolve_ref(kind, target):
                    errors.append(f"{key}: unresolved {kind} {target!r}")
            else:
                errors.append(f"{key}: unrecognized crossing-link {v!r} "
                              f"(expected [[wikilink]], #issue, owner/repo#issue, or http(s) URL)")
    return errors


def _gh_resolver(kind, target):
    """Resolve a GitHub-side ref via `gh` (best-effort; only full URLs / owner/repo#NN are resolvable)."""
    try:
        if kind == "url":
            api = target.replace("https://github.com/", "").replace("/issues/", "/issues/") \
                        .replace("/pull/", "/pulls/")
            return subprocess.run(["gh", "api", f"repos/{api}"],
                                  capture_output=True).returncode == 0
        if kind == "issue" and "/" in target:           # owner/repo#NN
            repo, num = target.split("#", 1)
            return subprocess.run(["gh", "issue", "view", num, "--repo", repo],
                                  capture_output=True).returncode == 0
    except FileNotFoundError:
        return True       # gh absent → don't fail loud on a missing tool; format check already passed
    return True           # bare #NN has no repo context → format-only


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail loud on unresolved source_* crossing-links.")
    ap.add_argument("file", help="the pipeline artifact (markdown with frontmatter)")
    ap.add_argument("--vault-root", default=DEFAULT_VAULT, help="Obsidian vault root for wikilinks")
    ap.add_argument("--no-gh", action="store_true", help="skip gh resolution of #issue/URL refs (offline)")
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    resolve = None if args.no_gh else _gh_resolver
    errors = check_links(text, vault_root=pathlib.Path(args.vault_root), resolve_ref=resolve)
    for e in errors:
        print(f"{args.file}: {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
