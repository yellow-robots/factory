#!/usr/bin/env python3
"""tools/changelog.py — compile an iteration's shipped changelog (it-36 slice I, #474).

At close, an iteration's changelog fragments (one per merged task PR, written under the manifest's
`changelog_dir` by the implement stage's own act, or by an attended PR's own duty) are compiled
alongside the technical-rfc and the round record into two things: a `CHANGELOG.md` entry (landed by
a PR — the same machinery-opened, evaluator-merged PR flow every other change goes through, no new
pipeline needed) and the release body `tools/release.py ship-it` posts — human notes plus a fenced
```yr-changelog``` block at schema `yr-changelog/1` (records.toml; minted at it-36 slice D, #469).

Pure compiler, stdlib only, fixture-driven (like tools/release.py / tools/merge_shadow.py): this
module does no `gh`/network I/O of its own — a caller (an attended closing session today; a future
close-runner.sh stage tomorrow) gathers the epic's merged PRs (`gh pr list ... --json number,title,body`)
into a JSON file and hands it to the CLI. A PR whose fragment is missing (an attended PR that skipped
the duty, or one predating this slice) is compiled from its OWN TITLE instead — named as such, both in
the rendered CHANGELOG.md line and in the compiled entry's `from_title_only` flag — never silently
dropped and never fabricated goal text.

The `yr-changelog` fenced block reuses the product's own knowledge-graph event vocabulary (the spec's
own instruction): `dt`, `prj`, `act`, `evt`, `ent`, `tr`, `cost`, `intent`
(yellow-robots/schemas/changelog-v1.schema.json) — one `[[event]]` per compiled entry, `evt = "MS"`
(milestone: a shipped task), `ent` naming the source issue, `intent` carrying the fragment's own Goal
text (or the PR title, for a title-only entry).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "yr-changelog/1"
FENCE = "yr-changelog"

_SOURCE_LINE_RE = re.compile(r"^Source:\s*(\S.*)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def parse_fragment(text: str) -> dict:
    """A changelog fragment (`tools/dev-runner.sh`'s implement-stage write, or an attended PR's own
    hand-authored equivalent): `## <title>`, a free-text goal paragraph, a trailing `Source: <ref>`
    line. Missing pieces degrade gracefully (empty string) rather than raising — a malformed fragment
    still compiles, it just carries less."""
    m = _HEADING_RE.search(text)
    title = m.group(1).strip() if m else ""
    src_m = _SOURCE_LINE_RE.search(text)
    source = src_m.group(1).strip() if src_m else ""
    body = text
    if m:
        body = body[m.end():]
    body = _SOURCE_LINE_RE.sub("", body).strip()
    return {"title": title, "goal": body, "source": source, "from_title_only": False}


def read_fragments(changelog_dir: Path) -> dict[str, dict]:
    """Every `<issue>.md` fragment under `changelog_dir`, keyed by issue number (the filename stem —
    tools/dev-runner.sh's own naming convention). A directory that does not exist yields no fragments
    (never an error — an iteration with zero fragments still compiles, naming every PR from its title)."""
    out: dict[str, dict] = {}
    if not changelog_dir.is_dir():
        return out
    for path in sorted(changelog_dir.glob("*.md")):
        entry = parse_fragment(path.read_text(encoding="utf-8"))
        entry["issue"] = path.stem
        out[path.stem] = entry
    return out


def fallback_from_title(pr_number, pr_title: str) -> dict:
    """A merged PR with no matching fragment: compiled from its OWN TITLE, named as such — never
    silently dropped, never a fabricated goal."""
    return {
        "title": pr_title or f"PR #{pr_number}",
        "goal": "",
        "source": f"PR #{pr_number}",
        "from_title_only": True,
        "issue": str(pr_number),
    }


def compile_entries(fragments: dict[str, dict], merged_prs: list[dict]) -> list[dict]:
    """One compiled entry per merged PR, newest-last (the PR list's own order is preserved — the
    caller sorts however it fetched them). `merged_prs` items: `{"number": int, "title": str,
    "closes": <issue-number-or-None>}` — `closes` is the issue the PR's own "Closes #N" line names
    (tools/dev-runner.sh's PR_BODY); an attended PR with no such line has no fragment to match by
    number and falls back from its title, exactly like a genuinely fragment-less one."""
    entries = []
    for pr in merged_prs:
        number = pr.get("number")
        title = pr.get("title") or ""
        closes = pr.get("closes")
        frag = fragments.get(str(closes)) if closes is not None else None
        if frag is None:
            entry = fallback_from_title(number, title)
        else:
            entry = dict(frag)
            entry.setdefault("title", title)
        entry["pr"] = number
        entries.append(entry)
    return entries


def render_changelog_md(iteration: str, entries: list[dict]) -> str:
    """A `## <iteration>` section: one bullet per compiled entry, a title-only one named as such."""
    lines = [f"## {iteration}", ""]
    if not entries:
        lines.append("_(no changes)_")
    for e in entries:
        title = e.get("title") or f"PR #{e.get('pr')}"
        source = e.get("source") or f"PR #{e.get('pr')}"
        if e.get("from_title_only"):
            lines.append(f"- **{title}** — compiled from title only, no changelog fragment ({source})")
        else:
            goal = (e.get("goal") or "").strip()
            goal_line = goal.splitlines()[0].strip() if goal else ""
            suffix = f" — {goal_line}" if goal_line else ""
            lines.append(f"- **{title}**{suffix} ({source})")
    lines.append("")
    return "\n".join(lines)


def prepend_changelog_section(existing: str, section: str) -> str:
    """Newest-on-top: a new `## <iteration>` section lands right after CHANGELOG.md's own title line
    (the first `# ` heading), ahead of every prior section — never re-ordering what's already there."""
    if not existing.strip():
        return f"# Changelog\n\n{section}"
    lines = existing.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            head = "".join(lines[: i + 1])
            rest = "".join(lines[i + 1:]).lstrip("\n")
            return f"{head}\n{section}\n{rest}" if rest else f"{head}\n{section}"
    return f"{section}\n{existing}"


def render_yr_changelog_block(iteration: str, release: str, entries: list[dict], *,
                              now: str | None = None) -> str:
    """The fenced ```yr-changelog``` TOML block, `yr-changelog/1` (records.toml — toml-schema mode:
    presence is the fence word alone, `tools/check_trail.py::_toml_schema_present`). Reuses the
    product's own event vocabulary verbatim (yellow-robots/schemas/changelog-v1.schema.json): `dt`,
    `prj`, `act`, `evt` ("MS" — milestone), `ent` (the source issue). `tr`/`cost` are that schema's
    `["string","null"]`/nullable fields, required only for an "SC" (state-change) event — a
    milestone entry omits both rather than spell a TOML null the format has no literal for; `intent`
    (the fragment's own Goal text, or the PR title for a title-only entry) is always populated, as
    the schema asks for every DE/MS-shaped event."""
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f'schema = "{SCHEMA}"',
        f'iteration = "{iteration}"',
        f'release = "{release}"',
        "",
    ]
    for e in entries:
        goal = (e.get("goal") or "").strip()
        intent = (goal.splitlines()[0].strip() if goal else (e.get("title") or "")).replace('"', "'")
        title = (e.get("title") or "").replace('"', "'")
        lines += [
            "[[event]]",
            f'dt = "{now}"',
            'prj = "factory"',
            'act = "tools/changelog.py"',
            'evt = "MS"',
            f'ent = "#{e.get("issue") or e.get("pr")}"',
            f'intent = "{intent or title}"',
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def render_release_body(human_notes: str, iteration: str, release: str, entries: list[dict]) -> str:
    """Human notes, then the fenced ```yr-changelog``` block — the shape `tools/release.py`'s
    `ship-it` posts as the GitHub Release body."""
    block = render_yr_changelog_block(iteration, release, entries)
    notes = human_notes.strip() or f"{iteration} shipped."
    return f"{notes}\n\n```{FENCE}\n{block}```\n"


def _read_json(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="changelog.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_c = sub.add_parser("compile", help="compile fragments + a merged-PR list into CHANGELOG.md + a release body")
    p_c.add_argument("--iteration", required=True, help='e.g. "it-36"')
    p_c.add_argument("--release", required=True, help='the tag, e.g. "it/36"')
    p_c.add_argument("--changelog-dir", required=True, help="the manifest's changelog_dir")
    p_c.add_argument("--prs-file", required=True,
                     help='JSON array: [{"number": int, "title": str, "closes": int|null}, ...]')
    p_c.add_argument("--notes-file", default=None, help="human-written release notes (plain text/markdown)")
    p_c.add_argument("--changelog-md", default="CHANGELOG.md", help="the file to update (default: CHANGELOG.md)")
    p_c.add_argument("--out-release-body", default=None, help="write the release body here")
    p_c.add_argument("--test-mode", action="store_true", help="print the plan; write nothing")
    args = ap.parse_args(argv)

    changelog_dir = Path(args.changelog_dir)
    fragments = read_fragments(changelog_dir)
    merged_prs = _read_json(args.prs_file)
    entries = compile_entries(fragments, merged_prs)
    section = render_changelog_md(args.iteration, entries)
    notes = Path(args.notes_file).read_text(encoding="utf-8") if args.notes_file else ""
    release_body = render_release_body(notes, args.iteration, args.release, entries)

    if args.test_mode:
        print("TEST-MODE: no files written — the plan only")
        print(f"would update: {args.changelog_md}")
        print("--- CHANGELOG.md section ---")
        print(section)
        print("--- release body ---")
        print(release_body, end="")
        return 0

    changelog_path = Path(args.changelog_md)
    existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
    changelog_path.write_text(prepend_changelog_section(existing, section), encoding="utf-8")
    if args.out_release_body:
        Path(args.out_release_body).write_text(release_body, encoding="utf-8")
    else:
        sys.stdout.write(release_body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
