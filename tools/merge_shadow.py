#!/usr/bin/env python3
"""merge_shadow — the factory's terminal (shadow) merge-condition evaluator + record (issue #37).

After the PR opens, the runner's first post-PR responsibility is a DETERMINISTIC step (no new LLM
stage): evaluate the fail-closed merge conditions IN ORDER, IN CODE, with an indeterminate result
treated as FAILED. Because arming is a later task, EVERY repo is treated as shadow — so the outcome is
posted as one loud, machine-readable record on the PR and the run stops for the human exactly as today
(a shadow WOULD-BLOCK is a NORMAL negative outcome, never Reason=Blocked).

The four conditions, in evaluation order (their ids are the WOULD-BLOCK reason):
  ci_green           — every configured check on the PR head concluded successful (bounded wait for
                       in-flight runs upstream; zero configured checks is a failure).
  freshness          — the reviewed base SHA equals main's tip at decision time.
  terminal_approval  — the final review round is a clean `VERDICT: APPROVE`.
  rank_gate          — the resolved pair satisfies strict review-rank > build-rank on one provider,
                       both ranked.

Two stdlib-only subcommands (like tools/review_bundle.py / tools/registry.py):
  classify-checks  — reduce a PR statusCheckRollup to `<total> <in_flight> <failed>`, the fields the
                     runner's bounded CI-wait loop polls on.
  record           — given each condition's pass/fail result (evaluated upstream, in order), the SHAs,
                     the rollup, and the review bundle, emit the PR comment: line 1 the loud marker
                     (`YR-MERGE-SHADOW: WOULD-MERGE` or `... WOULD-BLOCK — <first failed condition>`),
                     then a fenced `yr-merge-record` JSON block at schema yr-merge-record/1.

The record schema + marker grammar are a versioned contract — a later change bumps SCHEMA.
"""
import argparse
import json
import pathlib
import sys

MARKER = "YR-MERGE-SHADOW"
SCHEMA = "yr-merge-record/1"
# Order is the contract: the FIRST failed condition names the WOULD-BLOCK reason.
CONDITION_ORDER = ("ci_green", "freshness", "terminal_approval", "rank_gate")

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
    (indeterminate = failed): the loud shadow record must never over-report green."""
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


def first_failed(results):
    """The first condition (in CONDITION_ORDER) whose result is not exactly 'pass'. None => all pass."""
    for cid in CONDITION_ORDER:
        if results.get(cid) != "pass":
            return cid
    return None


def build_record(*, results, bundle, base_sha, head_sha, main_tip_sha, checks, check_rollup,
                 run_id, timestamp):
    """The yr-merge-record/1 object — the exact fields fixed by the epic (shadow-completion, a later
    task, computes over it, so it is machine-parseable, not prose)."""
    failed = first_failed(results)
    rounds = bundle.get("rounds") or []
    review_verdict = rounds[-1].get("verdict") if rounds else None
    return {
        "schema": SCHEMA,
        "decision": "WOULD-MERGE" if failed is None else "WOULD-BLOCK",
        "mode": "shadow",
        "machinery_ok": True,
        "failed_condition": failed,
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


def render_comment(record):
    """Line 1 the loud marker; then the fenced `yr-merge-record` JSON block. Loud by design: the marker
    is line 1 and, on a block, names its reason there."""
    if record["decision"] == "WOULD-MERGE":
        marker = f"{MARKER}: WOULD-MERGE"
    else:
        marker = f"{MARKER}: WOULD-BLOCK — {record['failed_condition']}"
    block = json.dumps(record, indent=2, sort_keys=True)
    return f"{marker}\n\n```yr-merge-record\n{block}\n```\n"


def _read_json(path):
    return json.loads(pathlib.Path(path).read_text()) if path else {}


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
    record = build_record(
        results=results, bundle=bundle,
        base_sha=args.base_sha, head_sha=args.head_sha, main_tip_sha=args.main_tip_sha,
        checks=checks, check_rollup=args.ci_state,
        run_id=args.run_id, timestamp=args.timestamp,
    )
    comment = render_comment(record)
    if args.out:
        pathlib.Path(args.out).write_text(comment)
    else:
        sys.stdout.write(comment)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Terminal (shadow) merge-condition evaluator + record.")
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
    p_r.add_argument("--ci-state", default="", help="overall CI rollup state (success/failure/empty/timed_out)")
    p_r.add_argument("--run-id", required=True)
    p_r.add_argument("--timestamp", required=True)
    p_r.add_argument("--out", default="", help="write the comment here (default: stdout)")
    p_r.set_defaults(func=_cli_record)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
