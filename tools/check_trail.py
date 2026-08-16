#!/usr/bin/env python3
"""check_trail.py — the trail-shape detector (it-30 slice 2, epic #415).

Registry-driven, presence + grammar only, content-blind: given a scope and its lane, verify that the
records `records.toml`'s `lanes` table mandates for that lane are present on their declared surfaces
and parse under their declared grammar modes. A present, well-formed record passes regardless of what
it says — genuineness belongs to independent review and the adherence bench, never to this tool.

Contract (the crossing's rulings, epic #415):
  * the lane → mandated-records mapping is DATA in `records.toml` (authored by the canon slice);
    an absent or empty `lanes` table means nothing mandated — clean exit, stated in output;
  * reads dispatch on each record row's `surfaces`: GitHub trails via `gh` (the nit_harvest pattern),
    vault docs via a filesystem `--vault-root` (the check_supersession pattern — this is walk/census
    tooling, design-side by definition);
  * findings one per line; exit 1 on findings, 0 clean (the check_supersession reporting shape);
  * advisory-tier: never wired into check_cmd, CI, or the manifest.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402
import textutil  # noqa: E402


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _marker_present(row: dict, texts: list[str]) -> bool:
    """Does any provided text carry the row's marker under the row's mode? Presence only."""
    mode = row["mode"]
    marker = row["marker"]
    for text in texts:
        lines = _lines(text)
        if mode == "prefix":
            if any(textutil.marker_line_matches(l, marker, mode=textutil.MARKER_PREFIX) for l in lines):
                return True
        elif mode == "sentinel":
            if any(textutil.marker_line_matches(l, marker, mode=textutil.MARKER_SENTINEL) for l in lines):
                return True
        elif mode == "strict-line":
            if any(l.rstrip() == marker for l in lines):
                return True
        elif mode == "verdict-line":
            if any(l.startswith(marker) for l in lines):
                return True
        elif mode == "stage-escape":
            non_empty = [l for l in lines if l.strip()]
            if non_empty and non_empty[-1].startswith(marker) and non_empty[-1][len(marker):].strip():
                return True
        elif mode == "json-schema":
            if _json_schema_present(text, marker):
                return True
    return False


def _json_schema_present(text: str, marker: str) -> bool:
    """A json-schema record is present only when some JSON OBJECT in the text carries
    `"schema" == marker` — a prose mention of the schema name is never presence. Candidates:
    the whole text, each fenced code block, and each single line."""
    candidates = [text]
    candidates += re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.S)
    candidates += text.splitlines()
    for c in candidates:
        c = c.strip()
        if not c.startswith("{"):
            continue
        try:
            obj = json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("schema") == marker:
            return True
    return False


def _missing_fields(row: dict, texts: list[str]) -> list[str]:
    """The row's declared fields that no SINGLE marker-carrying text holds in full. One record must
    be complete on its own — fields pooled across separate comments never satisfy a grammar, matching
    the real readers (the approval reader parses one comment). Grammar-level only: a field is present
    when a line starts with `<field>:` (lstripped) or carries a boundary-anchored `<field>=` — the
    two field forms the tree's grammars use; `re<field>=` never counts."""
    fields = row.get("fields") or []
    if not fields:
        return []
    carrying = [t for t in texts if _marker_present(row, [t])]
    best_missing: list[str] | None = None
    for t in carrying:
        lines = _lines(t)
        missing = [
            f for f in fields
            if not any(
                l.lstrip().startswith(f"{f}:") or re.search(rf"(^|\s){re.escape(f)}=", l)
                for l in lines
            )
        ]
        if not missing:
            return []
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing
    return best_missing or []


def check_texts(reg: dict, lane: str, texts_by_surface: dict[str, list[str]],
                lanes_map: dict | None = None, forbids_map: dict | None = None) -> list[str]:
    """The core: findings for one lane against pre-fetched surface texts. Pure — no network, no
    filesystem — so fixtures exercise every path. The lane mandates COMPILE from process.toml
    (`records.lanes` delegates there); a fixture passes its own `lanes_map`/`forbids_map`."""
    if lanes_map is None:
        lanes_map = records.lanes(reg)
        if forbids_map is None:
            forbids_map = records.lane_forbids(reg)
    lanes = lanes_map
    forbids_map = forbids_map or {}
    if not lanes:
        return []  # nothing mandated — an empty compiled mandate set
    wanted = lanes.get(lane)
    if wanted is None:
        return [f"lane {lane!r}: not in the compiled lanes (lanes: {', '.join(sorted(lanes))})"]
    findings = []
    for name in forbids_map.get(lane, []):
        row = records.get(reg, name)
        texts = [t for s in row["surfaces"] for t in texts_by_surface.get(s, [])]
        if texts and _marker_present(row, texts):
            findings.append(f"{lane}: {name}: must-not-carry record PRESENT "
                            f"(marker {row['marker']!r} — the airlock rule)")
    for name in wanted:
        row = records.get(reg, name)
        texts = [t for s in row["surfaces"] for t in texts_by_surface.get(s, [])]
        if not texts:
            findings.append(f"{lane}: {name}: no readable surface in scope "
                            f"(row surfaces: {', '.join(row['surfaces'])})")
            continue
        if not _marker_present(row, texts):
            findings.append(f"{lane}: {name}: mandated record absent "
                            f"(marker {row['marker']!r}, mode {row['mode']})")
            continue
        missing = _missing_fields(row, texts)
        if missing:
            findings.append(f"{lane}: {name}: record present but malformed — "
                            f"missing field(s): {', '.join(missing)}")
    return findings


# ── surface fetchers (the CLI's side; core stays pure) ───────────────────────────────────────────

def _gh_json(args: list[str]):
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True)
    except OSError as e:
        raise RuntimeError(f"gh unavailable: {e}")
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def _fetch_comments(repo: str, number: int) -> list[str]:
    """All comment bodies, page-safe: the gh api pagination loop (the nit_harvest pattern) — the
    `--json comments` export caps its list, and a record past the cap must never read as absent."""
    bodies: list[str] = []
    page = 1
    while True:
        batch = _gh_json(["api", f"repos/{repo}/issues/{number}/comments",
                          "-X", "GET", "-f", "per_page=100", "-f", f"page={page}"])
        bodies.extend(c.get("body") or "" for c in batch)
        if len(batch) < 100:
            return bodies
        page += 1


def fetch_issue_trail(repo: str, number: int) -> list[str]:
    data = _gh_json(["issue", "view", str(number), "--repo", repo, "--json", "body"])
    return [data.get("body") or ""] + _fetch_comments(repo, number)


def fetch_pr_trail(repo: str, number: int) -> list[str]:
    data = _gh_json(["pr", "view", str(number), "--repo", repo, "--json", "body"])
    return [data.get("body") or ""] + _fetch_comments(repo, number)


def fetch_releases(repo: str) -> list[str]:
    """One text per GitHub Release (tag-name line + body), page-safe like the comment fetcher —
    the release surface (it-31 slice 7): the YR-RELEASE record rides the Release body."""
    texts: list[str] = []
    page = 1
    while True:
        batch = _gh_json(["api", f"repos/{repo}/releases",
                          "-X", "GET", "-f", "per_page=100", "-f", f"page={page}"])
        texts.extend(f"{r.get('tag_name') or ''}\n{r.get('body') or ''}"
                     for r in batch if isinstance(r, dict))
        if len(batch) < 100:
            return texts
        page += 1


def fetch_vault_docs(vault_root: Path, rel_paths: list[str]) -> list[str]:
    """A named path that cannot be read is an ERROR, never a silent narrowing of the scope."""
    out = []
    for rel in rel_paths:
        p = vault_root / rel
        try:
            out.append(p.read_text(encoding="utf-8"))
        except OSError as e:
            raise RuntimeError(f"vault doc unreadable: {rel} ({e})")
    return out


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="trail-shape detector: presence + grammar of a lane's mandated records")
    ap.add_argument("--registry", type=Path, default=None)
    ap.add_argument("--lane", required=True, help="lane name in records.toml's lanes table")
    ap.add_argument("--repo", default="yellow-robots/factory")
    ap.add_argument("--issue", type=int, action="append", default=[], help="issue number (repeatable) — fills issue-trail/issue-body")
    ap.add_argument("--pr", type=int, action="append", default=[], help="PR number (repeatable) — fills pr-trail")
    ap.add_argument("--vault-root", type=Path, default=None)
    ap.add_argument("--vault-doc", action="append", default=[], help="vault-relative doc path (repeatable) — fills vault-doc")
    ap.add_argument("--scope-created", default=None,
                    help="ISO date the scope (issue/doc) was created; a scope predating the model's "
                         "effective date is version-scoped out (ruling 3: judge by schema version, "
                         "never accumulated date carve-outs — this is the v1.0.0 version table's one row)")
    args = ap.parse_args(argv)
    try:
        reg = records.load(args.registry)
    except records.RegistryError as e:
        print(f"check_trail: ERROR: {e}", file=sys.stderr)
        return 2
    texts: dict[str, list[str]] = {}
    try:
        for n in args.issue:
            t = fetch_issue_trail(args.repo, n)
            texts.setdefault("issue-trail", []).extend(t)
            texts.setdefault("issue-body", []).append(t[0])
        for n in args.pr:
            texts.setdefault("pr-trail", []).extend(fetch_pr_trail(args.repo, n))
        if args.vault_doc:
            if not args.vault_root:
                print("check_trail: ERROR: --vault-doc needs --vault-root", file=sys.stderr)
                return 2
            texts.setdefault("vault-doc", []).extend(fetch_vault_docs(args.vault_root, args.vault_doc))
        if args.lane == "release":
            # the release lane's scope is the repo alone — the surface is its Releases list
            texts.setdefault("release", []).extend(fetch_releases(args.repo))
    except RuntimeError as e:
        print(f"check_trail: ERROR: {e}", file=sys.stderr)
        return 2
    if args.scope_created:
        try:
            import process
            model = process.load(registry=reg)
            effective = next(a["date"] for a in model["amendment"]
                             if a["version"] == model["model"]["version"])
            if str(args.scope_created)[:10] < str(effective):
                print(f"check_trail: version-scoped — the scope predates model "
                      f"v{model['model']['version']} (effective {effective}); its mandates do not "
                      f"apply to this trail")
                return 0
        except Exception as e:  # noqa: BLE001 — scoping is best-effort; the mandates still run
            print(f"check_trail: NOTE: version scoping unavailable ({e})", file=sys.stderr)
    try:
        lanes_map = records.lanes(reg)
        forbids_map = records.lane_forbids(reg)
    except records.RegistryError as e:
        print(f"check_trail: ERROR: {e}", file=sys.stderr)
        return 2
    if not lanes_map:
        print("check_trail: nothing mandated — the compiled lane mandates are empty")
        return 0
    findings = check_texts(reg, args.lane, texts, lanes_map=lanes_map, forbids_map=forbids_map)
    for f in findings:
        print(f)
    if findings:
        return 1
    print(f"check_trail: ok — lane {args.lane!r} clean over "
          f"{sum(len(v) for v in texts.values())} text(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
