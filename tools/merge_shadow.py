#!/usr/bin/env python3
"""merge_shadow — the factory's terminal merge-condition evaluator, record, and shadow-completion
computer (issues #37 shadow, #38 autonomous merge).

After the PR opens, the runner's terminal responsibility is a DETERMINISTIC step (no new LLM stage):
evaluate the fail-closed merge conditions IN ORDER, IN CODE, with an indeterminate result treated as
FAILED. A repo is ARMED when its manifest sets `auto_merge = true` (read at DECISION time from the base
ref's current tip), the host sentinel is not thrown, and shadow is complete. An armed repo whose
conditions all pass is squash-merged BY THE FACTORY and recorded as a durable `YR-MERGE: MERGED`;
everything else stays in shadow (`YR-MERGE-SHADOW`) or armed-blocked (`YR-MERGE: BLOCKED`).

The four base conditions, in evaluation order (their ids are the WOULD-BLOCK / BLOCKED reason):
  ci_green           — every configured check on the PR head concluded successful (bounded wait for
                       in-flight runs upstream; a rollup still empty after a bounded registration
                       grace — see shadow_ci's own env pair — is a failure).
  freshness          — the reviewed base SHA equals main's tip at decision time.
  terminal_approval  — the final review round is a clean `VERDICT: APPROVE`.
  rank_gate          — the resolved pair satisfies strict review-rank > build-rank on one provider.
For an armed repo two more gate the merge: `sentinel` (the host kill switch is not thrown) and shadow
completion (below). A moved main (freshness fail) on an otherwise-armed pass is REMEDIATED by the runner
(rebase + re-green), not blocked.

Three stdlib-only subcommands (like tools/review_bundle.py / tools/registry.py):
  classify-checks  — reduce a PR statusCheckRollup to `<total> <in_flight> <failed>`, the fields the
                     runner's bounded CI-wait loop polls on.
  record           — emit the PR comment: line 1 the loud marker, then a fenced `yr-merge-record` JSON
                     block at schema yr-merge-record/1. `--mode shadow` derives WOULD-MERGE/WOULD-BLOCK
                     from the conditions; `--mode armed --decision MERGED|BLOCKED` posts the durable
                     merge/blocked record.
  shadow-complete  — compute shadow completion MECHANICALLY from the repo's prior PR merge records
                     (`--prs-file`, `gh pr list --json …comments`) and `main` history (`--main-log-file`,
                     for revert detection). One unified window over the last N merge records — shadow and
                     armed alike — ≥K landed unreverted successes and no reset. Prints `<true|false> <k> <n>`.

The record schema + marker grammar are a versioned contract — a later change bumps SCHEMA. New fields are
added additively so old records (and old parsers) stay valid.
"""
import argparse
import json
import pathlib
import re
import sys

MARKER_SHADOW = "YR-MERGE-SHADOW"
MARKER_ARMED = "YR-MERGE"
SCHEMA = "yr-merge-record/1"
# Order is the contract: the FIRST failed condition names the WOULD-BLOCK reason (shadow mode).
SHADOW_ORDER = ("ci_green", "freshness", "terminal_approval", "rank_gate")
CONDITION_ORDER = SHADOW_ORDER  # back-compat alias

# Shadow-completion window defaults (the epic's pinned N/K).
DEFAULT_WINDOW = 5
DEFAULT_NEED = 3

# A CheckRun `status` that is not COMPLETED means the run is still in flight (wait for it upstream).
IN_FLIGHT_STATUS = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED", "STALE"}
# A COMPLETED CheckRun `conclusion` (or a StatusContext `state`) counted as success.
SUCCESS_TERMS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# A StatusContext `state` that is still pending.
PENDING_STATE = {"PENDING", "EXPECTED"}


def _rollup_list(data):
    """The `statusCheckRollup` array from `gh pr view --json statusCheckRollup` (or a bare list)."""
    if isinstance(data, dict):
        data = data.get("statusCheckRollup")
    return data if isinstance(data, list) else []


def bucket_of(check):
    """Reduce one rollup entry to 'pass' | 'pending' | 'fail'. Anything unrecognized -> 'fail'
    (indeterminate = failed): the loud record must never over-report green."""
    tn = check.get("__typename")
    # StatusContext (legacy commit statuses): carries `state`, no `status`.
    if tn == "StatusContext" or ("state" in check and "status" not in check):
        state = str(check.get("state") or "").upper()
        if state in SUCCESS_TERMS:
            return "pass"
        if state in PENDING_STATE:
            return "pending"
        return "fail"
    # CheckRun (GitHub Actions & apps): `status` + `conclusion`.
    status = str(check.get("status") or "").upper()
    if status and status != "COMPLETED":
        return "pending" if status in IN_FLIGHT_STATUS else "fail"
    conclusion = str(check.get("conclusion") or "").upper()
    if not status and not conclusion:
        return "fail"
    return "pass" if conclusion in SUCCESS_TERMS else "fail"


def _check_name(check):
    return check.get("name") or check.get("context") or ""


def _check_state(check):
    return (check.get("conclusion") or check.get("status") or check.get("state") or "") or None


def normalize_checks(checks):
    return [{"name": _check_name(c), "state": _check_state(c), "bucket": bucket_of(c)} for c in checks]


def count_checks(checks):
    buckets = [bucket_of(c) for c in checks]
    return {
        "total": len(buckets),
        "in_flight": buckets.count("pending"),
        "failed": buckets.count("fail"),
        "successful": buckets.count("pass"),
    }


def first_failed(results, order=SHADOW_ORDER):
    """The first condition (in order) whose result is not exactly 'pass'. None => all pass."""
    for cid in order:
        if results.get(cid) != "pass":
            return cid
    return None


_UNSET = object()


def build_record(*, results, bundle, base_sha, head_sha, main_tip_sha, checks, check_rollup,
                 run_id, timestamp, mode="shadow", decision=None, failed_condition=_UNSET,
                 merge_commit=None, auto_merge=None, shadow_complete=None, shadow_progress=None,
                 sentinel=None):
    """The yr-merge-record/1 object — the exact fields fixed by the epic (shadow-completion computes over
    it, so it is machine-parseable, not prose). `decision`/`failed_condition` are DERIVED from the
    conditions when not supplied (shadow: WOULD-MERGE/WOULD-BLOCK); a caller with an out-of-band reason
    (an armed BLOCKED on `sentinel`, or a MERGED) passes them explicitly. `merge_commit`/`auto_merge`/
    `shadow_*`/`sentinel` are the additive arming fields; old shadow records simply omit them."""
    if failed_condition is _UNSET:
        failed_condition = first_failed(results)
    if decision is None:
        if mode == "armed":
            decision = "MERGED" if failed_condition is None else "BLOCKED"
        else:
            decision = "WOULD-MERGE" if failed_condition is None else "WOULD-BLOCK"
    rounds = bundle.get("rounds") or []
    review_verdict = rounds[-1].get("verdict") if rounds else None
    return {
        "schema": SCHEMA,
        "decision": decision,
        "mode": mode,
        "machinery_ok": True,
        "failed_condition": failed_condition,
        "conditions": results,
        "sentinel": sentinel,
        "auto_merge": auto_merge,
        "shadow_complete": shadow_complete,
        "shadow_progress": shadow_progress,
        "merge_commit": merge_commit or None,
        "bundle_sha256": bundle.get("sha256"),
        "base_sha": base_sha,
        "head_sha": head_sha,
        "main_tip_sha": main_tip_sha or None,
        "check_rollup": check_rollup,
        "checks": checks,
        "review_verdict": review_verdict,
        "rounds": len(rounds),
        "build": bundle.get("build"),
        "review": bundle.get("review"),
        "run_id": run_id,
        "timestamp": timestamp,
    }


def render_comment(record, armed_note=None):
    """Line 1 the loud marker; then the fenced `yr-merge-record` JSON block. The marker prefix is
    `YR-MERGE` for an armed record (MERGED/BLOCKED) and `YR-MERGE-SHADOW` for a shadow record
    (WOULD-MERGE/WOULD-BLOCK). A block/blocked record names its reason on line 1; an armed-but-shadow-
    incomplete WOULD-MERGE carries the `armed, shadow-incomplete n/N` progress note there."""
    prefix = MARKER_ARMED if record.get("mode") == "armed" else MARKER_SHADOW
    decision = record["decision"]
    if decision in ("WOULD-MERGE", "MERGED"):
        marker = f"{prefix}: {decision}"
        if armed_note and decision == "WOULD-MERGE":
            marker += f" — {armed_note}"
    else:  # WOULD-BLOCK / BLOCKED
        marker = f"{prefix}: {decision} — {record['failed_condition']}"
    block = json.dumps(record, indent=2, sort_keys=True)
    return f"{marker}\n\n```yr-merge-record\n{block}\n```\n"


# ---------------------------------------------------------------------------
# Shadow completion — computed mechanically from prior PR merge records + main history.
# ---------------------------------------------------------------------------

def _parse_record_block(body):
    """Parse the fenced ```yr-merge-record JSON block from a comment body. dict, or None if
    absent/unparseable."""
    marker = "```yr-merge-record"
    i = body.find(marker)
    if i < 0:
        return None
    rest = body[i + len(marker):]
    j = rest.find("```")
    if j < 0:
        return None
    try:
        return json.loads(rest[:j])
    except Exception:
        return None


def _last_merge_record(comments):
    """(record_dict | None, malformed_bool, seen_bool) for the LAST comment carrying a YR-MERGE marker.
    `seen` is False when the PR has no merge record at all (so it is not part of the window)."""
    rec, malformed, seen = None, False, False
    for c in comments or []:
        body = c.get("body") or ""
        # A merge-record comment is identified by its loud marker OR its fenced block (real records
        # carry both; either alone still marks the comment as a record for the window).
        if "YR-MERGE" not in body and "yr-merge-record" not in body:
            continue
        seen = True
        parsed = _parse_record_block(body)
        if parsed is None:
            rec, malformed = None, True
        else:
            rec, malformed = parsed, False
    return rec, malformed, seen


def _reverted_sets(main_log, repo):
    """From `main`'s history, the set of reverted commit SHAs and reverted PR numbers. Recognizes
    `This reverts commit <sha>` and `Reverts <owner>/<repo>#<n>` / `Reverts #<n>` (the epic's pinned
    grammar). `main_log` is `<hash>\\x1e<full message>` per commit, commits NUL-separated."""
    shas, prs = set(), set()
    repo_pat = re.escape(repo) if repo else None
    for chunk in (main_log or "").split("\x00"):
        if not chunk.strip():
            continue
        parts = chunk.split("\x1e", 1)
        msg = parts[1] if len(parts) > 1 else parts[0]
        for m in re.finditer(r"[Tt]his reverts commit ([0-9a-fA-F]{7,40})", msg):
            shas.add(m.group(1).lower())
        # "Reverts owner/repo#N" or a bare "Reverts #N".
        for m in re.finditer(r"[Rr]everts\s+(?:%s)?#(\d+)" % (repo_pat or ""), msg):
            prs.add(int(m.group(1)))
    return shas, prs


def _is_reverted(merge_sha, pr_number, rev_shas, rev_prs):
    """Was this landing reverted? A PR-number or a commit-SHA revert marker matches. Ambiguity (a
    partial SHA either way) counts as reverted (fail-closed, per the epic)."""
    if pr_number is not None and pr_number in rev_prs:
        return True
    if merge_sha:
        s0 = merge_sha.lower()
        for s in rev_shas:
            if s0.startswith(s) or s.startswith(s0):
                return True
    return False


def classify_event(pr, rev_shas, rev_prs):
    """Classify one PR's merge record into 'success' | 'reset' | 'neutral', or None when the PR carries
    no merge record (so it is not part of the window). A landed unreverted WOULD-MERGE (human-merged) or
    factory MERGED is a success; an overridden WOULD-BLOCK/BLOCKED, a reverted MERGED, a malformed or
    machinery-error record, or a contradiction is a reset; everything else is neutral."""
    rec, malformed, seen = _last_merge_record(pr.get("comments"))
    if not seen:
        return None
    number = pr.get("number")
    merged = str(pr.get("state") or "").upper() == "MERGED"
    merge_oid = ((pr.get("mergeCommit") or {}) or {}).get("oid") or ""
    if malformed or rec is None:
        return "reset"
    if rec.get("machinery_ok") is False:
        return "reset"
    decision = rec.get("decision")
    if decision == "MERGED":
        mc = rec.get("merge_commit") or merge_oid
        if not merged:
            return "reset"  # claims a factory merge but the PR is not merged -> contradiction
        return "reset" if _is_reverted(mc, number, rev_shas, rev_prs) else "success"
    if decision == "WOULD-MERGE":
        if merged:
            return "reset" if _is_reverted(merge_oid, number, rev_shas, rev_prs) else "success"
        return "neutral"  # would-merge the human has not (yet) merged: no landed success, no reset
    if decision in ("WOULD-BLOCK", "BLOCKED"):
        return "reset" if merged else "neutral"  # merged over a block -> overridden -> reset
    return "reset"  # unknown/contradictory decision


def shadow_completion(prs, main_log, *, repo="", exclude_pr=None, window=DEFAULT_WINDOW, need=DEFAULT_NEED):
    """(complete_bool, successes, window_size). One unified window over the last `window` merge records
    (newest first), excluding the current PR: complete iff no reset in the window AND >= `need`
    landed unreverted successes."""
    rev_shas, rev_prs = _reverted_sets(main_log, repo)
    ordered = sorted(prs, key=lambda p: (p.get("number") or 0), reverse=True)
    events = []
    for pr in ordered:
        if exclude_pr is not None and str(pr.get("number")) == str(exclude_pr):
            continue
        ev = classify_event(pr, rev_shas, rev_prs)
        if ev is not None:
            events.append(ev)
        if len(events) >= window:
            break
    win = events[:window]
    successes = sum(1 for e in win if e == "success")
    has_reset = any(e == "reset" for e in win)
    complete = (not has_reset) and (successes >= need)
    return complete, successes, len(win)


def _tribool(v):
    if v == "true":
        return True
    if v == "false":
        return False
    return None


def _read_json(path):
    return json.loads(pathlib.Path(path).read_text()) if path else {}


def _read_text(path):
    return pathlib.Path(path).read_text() if path else ""


def _cli_classify_checks(args):
    checks = _rollup_list(_read_json(args.rollup_file))
    c = count_checks(checks)
    print(f"{c['total']} {c['in_flight']} {c['failed']}")
    return 0


def _cli_record(args):
    bundle = _read_json(args.bundle)
    checks = normalize_checks(_rollup_list(_read_json(args.rollup_file))) if args.rollup_file else []
    results = {
        "ci_green": args.ci_green,
        "freshness": args.freshness,
        "terminal_approval": args.terminal_approval,
        "rank_gate": args.rank_gate,
    }
    decision, failed = None, _UNSET   # shadow: let build_record derive from the conditions
    if args.mode == "armed":
        if args.decision not in ("MERGED", "BLOCKED"):
            sys.stderr.write("record: --mode armed requires --decision MERGED|BLOCKED\n")
            return 2
        decision = args.decision
        if decision == "BLOCKED":
            if not args.block_reason:
                sys.stderr.write("record: --decision BLOCKED requires --block-reason\n")
                return 2
            failed = args.block_reason
        else:
            failed = None
    record = build_record(
        mode=args.mode, decision=decision, failed_condition=failed, results=results,
        bundle=bundle, base_sha=args.base_sha, head_sha=args.head_sha, main_tip_sha=args.main_tip_sha,
        merge_commit=args.merge_commit, auto_merge=_tribool(args.auto_merge),
        shadow_complete=_tribool(args.shadow_complete), shadow_progress=(args.shadow_progress or None),
        sentinel=(args.sentinel or None), checks=checks, check_rollup=args.ci_state,
        run_id=args.run_id, timestamp=args.timestamp,
    )
    comment = render_comment(record, armed_note=(args.armed_note or None))
    if args.out:
        pathlib.Path(args.out).write_text(comment)
    else:
        sys.stdout.write(comment)
    return 0


def _cli_shadow_complete(args):
    prs = _read_json(args.prs_file)
    if not isinstance(prs, list):
        prs = prs.get("prs", []) if isinstance(prs, dict) else []
    main_log = _read_text(args.main_log_file) if args.main_log_file else ""
    complete, successes, size = shadow_completion(
        prs, main_log, repo=args.repo, exclude_pr=(args.exclude_pr or None),
        window=args.window, need=args.need,
    )
    print(f"{'true' if complete else 'false'} {successes} {size}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Terminal merge-condition evaluator, record, and completion.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_cc = sub.add_parser("classify-checks", help="reduce a PR statusCheckRollup to total/in_flight/failed")
    p_cc.add_argument("--rollup-file", required=True, help="JSON from `gh pr view --json statusCheckRollup`")
    p_cc.set_defaults(func=_cli_classify_checks)

    p_r = sub.add_parser("record", help="emit the PR comment (marker line + yr-merge-record block)")
    for cond in ("ci-green", "freshness", "terminal-approval", "rank-gate"):
        p_r.add_argument(f"--{cond}", required=True, choices=("pass", "fail"),
                         dest=cond.replace("-", "_"))
    p_r.add_argument("--bundle", required=True, help="the review bundle (for sha256/rounds/build/review)")
    p_r.add_argument("--base-sha", required=True)
    p_r.add_argument("--head-sha", required=True)
    p_r.add_argument("--main-tip-sha", default="")
    p_r.add_argument("--rollup-file", default="", help="JSON check rollup (for the normalized checks list)")
    p_r.add_argument("--ci-state", default="",
                      help="overall CI rollup state (success/failure/timed_out/empty_after_grace)")
    p_r.add_argument("--run-id", required=True)
    p_r.add_argument("--timestamp", required=True)
    p_r.add_argument("--out", default="", help="write the comment here (default: stdout)")
    # arming (issue #38): mode + the durable merge/blocked decision and its fields.
    p_r.add_argument("--mode", choices=("shadow", "armed"), default="shadow")
    p_r.add_argument("--decision", choices=("MERGED", "BLOCKED"), default="")
    p_r.add_argument("--block-reason", default="", help="the failed condition for an armed BLOCKED record")
    p_r.add_argument("--merge-commit", default="", help="the squash merge commit sha for a MERGED record")
    p_r.add_argument("--auto-merge", default="", choices=("", "true", "false"))
    p_r.add_argument("--shadow-complete", default="", choices=("", "true", "false"))
    p_r.add_argument("--shadow-progress", default="", help="e.g. '2/5'")
    p_r.add_argument("--sentinel", default="", help="'ok' | 'thrown'")
    p_r.add_argument("--armed-note", default="", help="marker note for an armed-but-shadow-incomplete WOULD-MERGE")
    p_r.set_defaults(func=_cli_record)

    p_sc = sub.add_parser("shadow-complete",
                          help="compute shadow completion from prior PR merge records + main history")
    p_sc.add_argument("--prs-file", required=True, help="`gh pr list --json number,state,mergeCommit,comments`")
    p_sc.add_argument("--main-log-file", default="", help="main history dump for revert detection")
    p_sc.add_argument("--repo", default="", help="owner/name (for 'Reverts owner/repo#N' matching)")
    p_sc.add_argument("--exclude-pr", default="", help="the current PR number (excluded from the window)")
    p_sc.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    p_sc.add_argument("--need", type=int, default=DEFAULT_NEED)
    p_sc.set_defaults(func=_cli_shadow_complete)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
