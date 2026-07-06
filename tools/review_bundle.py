#!/usr/bin/env python3
"""review_bundle — the factory's canonical, incrementally-built, hashed review bundle.

One artifact per run, assembled in two steps and written to the run dir (stdlib only, like
tools/textutil.py / tools/registry.py):

  init            — before the review stage: the staged diff (base/head SHAs), the
                    acceptance-criteria block, the check gate's command/exit/output tail, and the
                    resolved build/review entries (with ranks). This is what the reviewer reads.
  record-verdict  — after each review round lands: append its verdict/transcript and refresh the
                    decision-time sha256 over the completed bundle so far.

Serialization is canonical (sorted keys, compact separators) so the hash is reproducible for
identical inputs — it names exactly the decision's inputs, not incidental formatting.
"""
import argparse
import hashlib
import json
import pathlib
import sys

CHECK_TAIL_LINES = 40


def _read_text(path):
    return pathlib.Path(path).read_text() if path else ""


def _tail(text, n=CHECK_TAIL_LINES):
    return "\n".join(text.splitlines()[-n:])


def canonical_dumps(data):
    """Stable key order + compact separators, so identical bundle contents hash identically."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_bundle(*, base_sha, head_sha, diff, acceptance_criteria, check_cmd, check_exit,
                  checks_log, build_entry, review_entry):
    """Assemble the pre-review subset (RFC: census seed 6)."""
    return {
        "diff": {"base_sha": base_sha, "head_sha": head_sha, "patch": diff},
        "acceptance_criteria": acceptance_criteria,
        "check": {"command": check_cmd, "exit_code": int(check_exit), "output_tail": _tail(checks_log)},
        "build": build_entry,
        "review": review_entry,
        "rounds": [],
    }


def append_round(bundle, verdict_text):
    """Append one review round's verdict (its last `VERDICT:` line) plus the full transcript."""
    verdict_lines = [line.strip() for line in verdict_text.splitlines() if line.strip().upper().startswith("VERDICT:")]
    rounds = bundle.setdefault("rounds", [])
    rounds.append({
        "index": len(rounds) + 1,
        "verdict": verdict_lines[-1] if verdict_lines else None,
        "transcript": verdict_text,
    })
    return bundle


def finalize(bundle):
    """Return bundle with 'sha256' set to the digest of its own canonical serialization (self-excluded,
    so the hash names the decision's inputs — not itself)."""
    without_hash = {k: v for k, v in bundle.items() if k != "sha256"}
    digest = hashlib.sha256(canonical_dumps(without_hash).encode("utf-8")).hexdigest()
    result = dict(without_hash)
    result["sha256"] = digest
    return result


def read_bundle(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_bundle(path, bundle):
    pathlib.Path(path).write_text(canonical_dumps(bundle))


def _cli_init(args):
    build_entry = json.loads(args.build_json) if args.build_json else {}
    review_entry = json.loads(args.review_json) if args.review_json else {}
    bundle = build_bundle(
        base_sha=args.base_sha, head_sha=args.head_sha,
        diff=_read_text(args.diff_file),
        acceptance_criteria=_read_text(args.criteria_file),
        check_cmd=args.check_cmd, check_exit=args.check_exit,
        checks_log=_read_text(args.checks_log),
        build_entry=build_entry, review_entry=review_entry,
    )
    write_bundle(args.bundle, bundle)
    return 0


def _cli_record_verdict(args):
    bundle = read_bundle(args.bundle)
    append_round(bundle, _read_text(args.file))
    write_bundle(args.bundle, finalize(bundle))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Assemble the factory's canonical, hashed review bundle.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="assemble the pre-review bundle subset")
    p_init.add_argument("--bundle", required=True, help="path to write the bundle JSON to")
    p_init.add_argument("--base-sha", required=True)
    p_init.add_argument("--head-sha", required=True)
    p_init.add_argument("--diff-file", required=True, help="file containing the staged diff")
    p_init.add_argument("--criteria-file", required=True, help="file containing the acceptance-criteria block")
    p_init.add_argument("--checks-log", required=True, help="the check gate's captured output")
    p_init.add_argument("--check-cmd", required=True)
    p_init.add_argument("--check-exit", required=True, type=int)
    p_init.add_argument("--build-json", default="", help="resolved build role entry (JSON)")
    p_init.add_argument("--review-json", default="", help="resolved review role entry (JSON)")
    p_init.set_defaults(func=_cli_init)

    p_rv = sub.add_parser("record-verdict",
                           help="append a review round's verdict and refresh the decision-time hash")
    p_rv.add_argument("--bundle", required=True)
    p_rv.add_argument("--file", required=True, help="path to the reviewer's transcript (e.g. review.md)")
    p_rv.set_defaults(func=_cli_record_verdict)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
