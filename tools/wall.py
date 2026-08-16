#!/usr/bin/env python3
"""wall.py — the attended lane's hook shim over the process model (it-30 slice 5, rebuilt).

The walls are a LOOP OVER COMPILED ROWS, never a pile of per-act regexes: `process.toml` declares
the machines, transitions, guards, stores and bindings; `tools/process.py` loads it, derives every
stance, and decides. This file is only the transport — hook JSON in, decision JSON out — plus the
journal append (after the decision, best-effort, structurally unable to influence it) and the Stop
close report.

Fail-open honesty (the verified harness contract): a PreToolUse hook that crashes lets the call
through INVISIBLY. So a model that does not load is answered with a LOUD, non-blocking
`additionalContext` note — the walls are off and every session is told so — while the gating tier
(the model-loads test inside check_cmd/CI, ruling 1) keeps that state from ever shipping.

CLI: pre-tool · close · promote-check (delegates to the engine's transition-check; promote.sh's
     seam, unchanged) · counts (the journal view the round record reads).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import process  # noqa: E402


def _load_model():
    try:
        return process.load(), None
    except Exception as e:  # noqa: BLE001 — records.RegistryError or process.ModelError alike
        return None, str(e)


def pre_tool(hook: dict, *, no_journal: bool = False) -> dict | None:
    model, err = _load_model()
    if model is None:
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (f"YR walls: THE MODEL DOES NOT LOAD — the walls are OFF for this "
                                  f"session ({err}). The load-time tier gates in check_cmd/CI; "
                                  f"repair process.toml before trusting any wall.")}}
    out, rows = process.decide(model, hook)
    if not no_journal:
        process.journal_append(model, rows, hook.get("session_id") or "")
    return out


def close(hook: dict, *, no_journal: bool = False) -> dict | None:
    model, err = _load_model()
    if model is None:
        return None  # the pre-tool half already tells the session, loudly, on every act
    session = hook.get("session_id") or ""
    text, should_block = process.close_report(model, session,
                                              journal_announcements=not no_journal)
    if not text:
        return None
    if should_block:
        if not no_journal:
            process.journal_append(model, [{"ts": int(time.time()), "transition_id": "close",
                                            "binding_id": None, "scope": {},
                                            "stance": "close-block",
                                            "caller": "attended-agent"}], session)
        return {"decision": "block",
                "reason": (text + "\n\nResolve the unresolved traces, or close again to proceed "
                                  "loud — the override is journaled and the close report carries it.")}
    if "OVERRIDE:" in text and not no_journal:
        # "OVERRIDE:" is the proceed-loud line's prefix; the standing "OVERRIDDEN:" line never
        # journals another override row — bookkeeping must not multiply (it-31 slice 1)
        process.journal_append(model, [{"ts": int(time.time()), "transition_id": "close",
                                        "binding_id": None, "scope": {}, "stance": "close-override",
                                        "caller": "attended-agent"}], session)
    return {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": text}}


def counts(session: str | None) -> int:
    model, err = _load_model()
    if model is None:
        print(f"wall: MODEL DOES NOT LOAD — {err}", file=sys.stderr)
        return 1
    rows = process.journal_rows(model, session)
    if rows is None:
        print("wall: journal unreadable — UNKNOWN, never ok", file=sys.stderr)
        return 1
    for r in rows:
        print(json.dumps(r))
    return 0


def promote_check(repo: str, issue: str) -> int:
    """The standalone promote wall — the engine's transition-check on the promote row. One grammar,
    one judge: the guards evaluate through the same registry-routed predicate every reader uses."""
    model, err = _load_model()
    if model is None:
        print(f"wall: REFUSED [promote] — the model does not load ({err}); a fail-closed wall that "
              f"cannot evaluate refuses", file=sys.stderr)
        return 1
    rc, failures = process.transition_check(model, "task.backlog->ready.standalone",
                                            {"repo": repo, "issue": issue})
    for f in failures:
        print(f"wall: REFUSED [promote] — {f}", file=sys.stderr)
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the attended lane's wall — hook shim over process.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_pre = sub.add_parser("pre-tool", help="PreToolUse: hook JSON on stdin -> decision JSON (or silence)")
    p_pre.add_argument("--dry-run", action="store_true",
                       help="test mode: decide without touching the journal")
    p_close = sub.add_parser("close",
                             help="Stop: hook JSON on stdin -> close report / block (or silence)")
    p_close.add_argument("--dry-run", action="store_true",
                         help="test mode: decide without touching the journal")
    p_prom = sub.add_parser("promote-check", help="the promote wall (called by promote.sh)")
    p_prom.add_argument("repo")
    p_prom.add_argument("issue")
    p_prom.add_argument("--gh", default=None,
                        help="the caller's gh binary; exported as GH_BIN for the source layer")
    p_counts = sub.add_parser("counts", help="print journal rows (round-record raw material)")
    p_counts.add_argument("--session", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "promote-check":
        if args.gh:
            os.environ["GH_BIN"] = args.gh
        return promote_check(args.repo, args.issue)
    if args.cmd == "counts":
        return counts(args.session)
    try:
        hook = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # unreadable hook input: stay silent — never brick the session on our own defect
    out = (pre_tool(hook, no_journal=args.dry_run) if args.cmd == "pre-tool"
           else close(hook, no_journal=args.dry_run))
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
