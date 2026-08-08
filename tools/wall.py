#!/usr/bin/env python3
"""wall.py — the attended lane's wall engine (it-30 slice 5, epic #415).

The enforcement layer's deciding half: PreToolUse calls arrive as hook JSON on stdin, are classified
against the walled-act map (`skills/factory/references/attended-lane.md`; conditions per act, stance
fail-closed on every act in the map), and dispose as a permission decision whose reason NAMES THE
RULE — the talking wall is the teaching mechanism, never an inconvenience. The Stop half checks the
session's close: a session that executed a walled act or emitted a mandated record is refused a
silent close once, with each missing trace named; a second consecutive close with traces unchanged
proceeds loud and records the override.

Design rules carried from the epic:
  * walls check EXISTENCE AND GRAMMAR only — genuineness stays with independent review and the bench;
  * infrastructure failure ≠ condition failure: a wall that cannot evaluate a fail-closed act's
    condition REFUSES (naming what it could not read); the close check never hard-locks (the
    second-close override);
  * every event lands in the counts (refusals, records demanded, escalations) where the round record
    reads them — the state dir's JSONL, one object per event;
  * act classification is pure and offline; trail reads are bounded subprocess `gh` calls, stubbed
    in tests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402
import textutil  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

STATE_DIR = Path(os.environ.get("YR_WALL_STATE", Path.home() / ".cache" / "yr-attended"))
VAULT_ROOT = Path(os.environ.get("YR_VAULT_ROOT", "/srv/obsidian/vaults/obsidian"))
GH_TIMEOUT = int(os.environ.get("YR_WALL_GH_TIMEOUT", "20"))


# ── who this engine speaks to ────────────────────────────────────────────────────────────────────

def in_scope(cwd: Path | None = None) -> bool:
    """Does this session's working directory belong to the factory's world?

    Plugin hooks are USER-scoped: without this check the walls fire in every session in every
    directory — a personal repo's untrailered commit refused, a `git push origin main` anywhere
    refused. The lane's authority ends where factory work ends, so the engine speaks only inside a
    factory-governed tree: a repo carrying `.yr/factory.toml` (the manifest that makes a repo the
    factory's), the factory repo itself, or anything under `$YR_WORKSPACE` (the vault included —
    the write-path class is a factory rule about the design brain).

    Machinery is out of scope too: a cold pipeline stage inherits `YR_MACHINERY` from the runner,
    exactly as delivery already honours it (`hooks/deliver.sh`) — one declaration, both halves.
    """
    if os.environ.get("YR_MACHINERY"):
        return False
    here = (cwd or Path.cwd()).resolve()
    workspace = Path(os.environ.get("YR_WORKSPACE", REPO_ROOT.parent)).resolve()
    for d in (here, *here.parents):
        if (d / ".yr" / "factory.toml").is_file():
            return True
        if (d / ".claude-plugin" / "plugin.json").is_file() and (d / "tools" / "dev-runner.sh").is_file():
            return True  # the factory repo itself
        if d == workspace or d == VAULT_ROOT:
            return True
    return False


# ── counts: the round record's raw material ──────────────────────────────────────────────────────

def _emit_event(kind: str, session_id: str, act: str, detail: str) -> None:
    """Counting must never decide an act. An unwritable state dir used to raise out of `decide()`,
    the hook then exited non-zero with no decision — and a PreToolUse hook that errors lets the call
    THROUGH. So the wall failed OPEN on every act whenever its bookkeeping broke, the exact inverse
    of the canon's rule. Bookkeeping is now best-effort and silent; the refusal is what matters."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        row = {"ts": int(time.time()), "kind": kind, "session": session_id, "act": act, "detail": detail}
        with open(STATE_DIR / "counts.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def read_counts(session_id: str | None = None) -> list[dict]:
    """Tolerant by construction: one truncated line (a killed session) used to raise and disable the
    close check permanently, for every future session, silently."""
    p = STATE_DIR / "counts.jsonl"
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue  # a partial write from a killed session: skip the line, keep the ledger
    return [r for r in rows if session_id is None or r.get("session") == session_id]


# ── act classification (pure) ────────────────────────────────────────────────────────────────────

def classify(tool_name: str, tool_input: dict) -> tuple[str, dict] | None:
    """The walled act this tool call performs, or None. Returns (act, evidence)."""
    if tool_name == "Bash":
        cmd = tool_input.get("command") or ""
        try:
            toks = shlex.split(cmd)
        except ValueError:
            toks = cmd.split()
        joined = " ".join(toks)
        if re.search(r"\bgh\b.*\bpr\b.*\bmerge\b", joined):
            return "hand-merge", {"command": cmd}
        m = re.search(r"\bgit\b[^|;&]*\bpush\b([^|;&]*)", cmd)
        if m:
            rest = m.group(1)
            if re.search(r"(^|\s)(origin\s+)?(main|master)(\s|:|$)", rest) or ":main" in rest or ":master" in rest:
                return "push-main", {"command": cmd}
            br = re.search(r"task/(\d+)-[\w-]+", rest)
            if br or "-u origin task/" in cmd or re.search(r"\bgit push\b\s*$", cmd.strip()) \
               or re.search(r"\bpush\b\s*$", cmd.strip()):
                return None  # the session's own task branch (or bare push on it) is the lawful case
            return "push-shared", {"command": cmd}
        if "board_plumbing.py" in cmd and "set-field" in cmd:
            return "board-write", {"command": cmd}
        if re.search(r"\bgh\b.*\bissue\b.*\bcreate\b", joined):
            body = _issue_create_body(cmd)
            if body is None:
                return "crossing-file", {"unreadable": True, "command": cmd}
            if re.search(r"\*\*Source:\*\*.*(product-spec|feature-rfc)", body):
                return "crossing-file", {"body": body, "command": cmd}
            return None
        if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd):
            return _classify_commit(cmd)
        return None
    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path") or ""
        if path.startswith(str(VAULT_ROOT) + os.sep):
            return "vault-fs-write", {"path": path}
        if path.endswith(".yr/factory.toml") or "/.yr/factory.toml" in path:
            return "arming-edit", {"path": path}
        if path.endswith(".claude-plugin/plugin.json"):
            return "release-edit", {"path": path}
        return None
    if tool_name == "mcp__obsidian__vault_patch":
        if (tool_input.get("targetType") == "frontmatter"
                and tool_input.get("target") == "status"
                and str(tool_input.get("content") or "").strip('"') in ("active", "superseded")):
            return "lifecycle-stamp", {"path": tool_input.get("path"),
                                       "to": str(tool_input.get("content")).strip('"')}
        return None
    return None


def _issue_create_body(cmd: str) -> str | None:
    m = re.search(r"--body-file\s+(\S+)", cmd)
    if m:
        try:
            return Path(m.group(1)).read_text(encoding="utf-8")
        except OSError:
            return None
    m = re.search(r"--body\s+(\"(?:[^\"\\]|\\.)*\"|'[^']*'|\S+)", cmd)
    if m:
        return m.group(1).strip("\"'")
    return ""


def _classify_commit(cmd: str) -> tuple[str, dict] | None:
    if "Co-Authored-By:" in cmd:
        return None
    m = re.search(r"(?:-F|--file)\s+(\S+)", cmd)
    if m:
        try:
            if "Co-Authored-By:" in Path(m.group(1)).read_text(encoding="utf-8"):
                return None
            return "commit-untrailed", {"command": cmd}
        except OSError:
            return "commit-untrailed", {"unreadable": True, "command": cmd}
    if re.search(r"\s-m\b|\s--message\b", cmd):
        return "commit-untrailed", {"command": cmd}
    return None  # editor-driven commit: the body is not visible pre-execution; the trailer rides it


# ── condition checks (trail reads: bounded gh; vault reads: filesystem) ──────────────────────────

def _gh_lines(args: list[str]) -> list[str] | None:
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.splitlines()


def _trail_has(repo: str, issue: str, marker: str, mode: str) -> bool | None:
    lines = _gh_lines(["issue", "view", issue, "--repo", repo,
                       "--json", "body,comments",
                       "--jq", ".body, (.comments[].body)"])
    if lines is None:
        return None
    return any(textutil.marker_line_matches(l, marker, mode=mode) for l in lines)


def _design_status_from_body(body: str) -> str | None:
    m = re.search(r"\[\[([^\]]+/iterations/[^\]|]+)\]\]", body)
    if not m:
        return None
    rel = m.group(1)
    p = VAULT_ROOT / (rel if rel.endswith(".md") else rel + ".md")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return None
    s = re.search(r"^status:\s*(\S+)", txt, flags=re.M)
    return s.group(1) if s else None


# ── the decision ─────────────────────────────────────────────────────────────────────────────────

RULES = {
    "hand-merge": "categorical: an attended hand-merge is refused outright — merges execute through the evaluator (attended-lane.md, the walled-act map; spec ruling (i))",
    "push-main": "categorical: pushing main is refused — the branch protection's client-side voice (attended-lane.md)",
    "push-shared": "a shared branch that is not this task's own requires the record of the human's explicit instruction (attended-lane.md)",
    "board-write": "a board Status/Reason write requires the YR-BOARD-FLIP record on the trail first — record-before-flip, typed (attended-lane.md)",
    "lifecycle-stamp": "a vault lifecycle stamp is the accept act's — it requires the accepting doc's review, fit, and accept records (attended-lane.md)",
    "arming-edit": "arming is decided exclusively by the human — the edit requires the record attributing her explicit instruction (attended-lane.md; onboarding.md)",
    "crossing-file": "filing a crossing requires the governing design to be active (attended-lane.md; the epic-gate's own wall)",
    "release-edit": "a skill release requires the freeze checks' records (attended-lane.md; closing.md's release block)",
    "vault-fs-write": "categorical: a filesystem vault write is off-table — the Editing-safely decision table names the sanctioned rows (documentation-model.md)",
    "commit-untrailed": "an attended commit carries the Co-Authored-By trailer naming the authoring model — a commit minted on the human's identity without it is walled (attended-lane.md; AGENTS conventions)",
}


def decide(hook: dict) -> dict | None:
    """The PreToolUse decision, or None to stay silent (unwalled call)."""
    session = hook.get("session_id") or "unknown"
    got = classify(hook.get("tool_name") or "", hook.get("tool_input") or {})
    if got is None:
        return None
    act, ev = got
    reason = RULES[act]
    # Acts whose condition can be satisfied in-flight:
    if act == "crossing-file" and not ev.get("unreadable"):
        status = _design_status_from_body(ev.get("body") or "")
        if status == "active":
            _emit_event("pass", session, act, "design active")
            return None
        reason += f" — resolved status: {status or 'unresolvable'}"
    if act == "crossing-file" and ev.get("unreadable"):
        reason += " — the body could not be read; a fail-closed wall that cannot evaluate refuses, naming what it could not read"
    _emit_event("refusal", session, act, reason[:200])
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"YR-WALL [{act}] — {reason}",
        }
    }


# ── the close check ──────────────────────────────────────────────────────────────────────────────

def close_check(hook: dict) -> dict | None:
    """Stop: refuse a silent close once when this session's walled activity has missing traces;
    second consecutive unchanged close proceeds loud and records the override. V1 traces: a session
    that suffered refusals should have resolved them (no unresolved refusal in its tail) — presence
    of activity with no later 'pass'/'resolved' marks the trace missing."""
    session = hook.get("session_id") or "unknown"
    events = read_counts(session)
    if not events:
        return None
    refusals = [e for e in events if e["kind"] == "refusal"]
    blocks = [e for e in events if e["kind"] == "close-block"]
    unresolved = [e for e in refusals if not any(
        p["kind"] == "pass" and p["act"] == e["act"] and p["ts"] >= e["ts"] for p in events)]
    if not unresolved:
        return None
    if blocks and blocks[-1]["ts"] >= max(e["ts"] for e in unresolved):
        _emit_event("close-override", session, "close",
                    f"proceeding loud with {len(unresolved)} unresolved refusal(s)")
        return None  # second consecutive close, traces unchanged: proceed loud, recorded
    _emit_event("close-block", session, "close", f"{len(unresolved)} unresolved refusal(s)")
    acts = ", ".join(sorted({e['act'] for e in unresolved}))
    return {
        "decision": "block",
        "reason": (f"YR-WALL [close] — this session was refused on: {acts}, and the traces are "
                   f"unresolved. Resolve them (or close again to proceed loud — the override is "
                   f"recorded in the round's counts)."),
    }


# ── the promote wall (the in-funnel half promote.sh calls) ───────────────────────────────────────

def _comment_bodies(gh_bin: str, repo: str, issue: str) -> list[str] | None:
    """Comment bodies via `--json comments`, parsed here rather than through `--jq`: the shape is
    stable across the real gh (objects with `body`) and the test harness's fake (plain strings), and
    parsing in one place keeps the wall evaluable under both."""
    try:
        out = subprocess.run([gh_bin, "issue", "view", issue, "--repo", repo, "--json", "comments"],
                             capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return None
    bodies = []
    for c in (data.get("comments") or []):
        bodies.append(c.get("body") or "" if isinstance(c, dict) else str(c))
    return bodies


def board_check(item_id: str, gh_bin: str = "gh") -> int:
    """The board-write condition, evaluated HERE rather than in `board_plumbing` — the home imports
    stdlib only, and a hand-rolled marker matcher outside `textutil` is refused tree-wide (the it-28
    anti-recurrence guard). One implementation, two callers: the funnel shells out to this, and the
    hook's raw-evasion classification resolves the same item.

    Condition: the issue this board item fronts carries the typed `YR-BOARD-FLIP` record — record
    before flip. Fail-closed: a condition that cannot be evaluated refuses, naming what it could not
    read."""
    reg = records.load()
    row = records.get(reg, "YR-BOARD-FLIP")
    query = ("query($id:ID!){node(id:$id){... on ProjectV2Item{content{... on Issue{"
             "body comments(last:100){nodes{body}}}}}}}")
    try:
        out = subprocess.run(
            [gh_bin, "api", "graphql", "-f", f"query={query}", "-F", f"id={item_id}",
             "--jq", '[.data.node.content.body, (.data.node.content.comments.nodes[].body)] | join("\\u0000")'],
            capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"wall: REFUSED [board-write] — the item's trail could not be read ({e}); a fail-closed "
              f"wall that cannot evaluate refuses (attended-lane.md)", file=sys.stderr)
        return 1
    if out.returncode != 0:
        print(f"wall: REFUSED [board-write] — the item's trail could not be read "
              f"({out.stderr.strip()[:160]}); a fail-closed wall that cannot evaluate refuses", file=sys.stderr)
        return 1
    lines = [l for t in out.stdout.split("\0") for l in t.splitlines()]
    if any(textutil.marker_line_matches(l, row["marker"], mode=textutil.MARKER_PREFIX) for l in lines):
        return 0
    print(f"wall: REFUSED [board-write] — an attended board write requires the {row['marker']} record "
          f"on the issue's trail first (record-before-flip, typed; attended-lane.md). Post it, then "
          f"write.", file=sys.stderr)
    return 1


def promote_check(repo: str, issue: str, gh_bin: str = "gh") -> int:
    reg = records.load()
    row = records.get(reg, "YR-TASK-GATES")
    bodies = _comment_bodies(gh_bin, repo, issue)
    lines = None if bodies is None else [l for b in bodies for l in b.splitlines()]
    if lines is None:
        print(f"wall: REFUSED [promote] — the trail could not be read; a fail-closed wall that "
              f"cannot evaluate refuses (repo {repo} issue {issue})", file=sys.stderr)
        return 1
    ok = any(l.rstrip() == row["marker"] for l in lines)
    fields_ok = all(any(l.lstrip().startswith(f"{f}:") for l in lines) for f in row["fields"])
    if ok and fields_ok:
        return 0
    print(f"wall: REFUSED [promote] — a standalone promote requires the {row['marker']} record "
          f"(fields {', '.join(row['fields'])}) on the trail first; YR-PROMOTED / YR-AUTO-PROMOTED "
          f"never satisfy it (attended-lane.md; closing.md)", file=sys.stderr)
    return 1


# ── entry ────────────────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the attended lane's wall engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pre-tool", help="PreToolUse: hook JSON on stdin -> decision JSON (or silence)")
    sub.add_parser("close", help="Stop: hook JSON on stdin -> block JSON (or silence)")
    p_prom = sub.add_parser("promote-check", help="the promote wall (called by promote.sh)")
    p_prom.add_argument("repo")
    p_prom.add_argument("issue")
    p_prom.add_argument("--gh", default=os.environ.get("GH_BIN", "gh"),
                        help="the gh binary the caller uses (promote.sh passes its own $GH_BIN)")
    p_counts = sub.add_parser("counts", help="print counts (round-record raw material)")
    p_counts.add_argument("--session", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "promote-check":
        return promote_check(args.repo, args.issue, args.gh)
    if args.cmd == "counts":
        for r in read_counts(args.session):
            print(json.dumps(r))
        return 0
    try:
        hook = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # unreadable hook input: stay silent — never brick the session on our own defect
    out = decide(hook) if args.cmd == "pre-tool" else close_check(hook)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
