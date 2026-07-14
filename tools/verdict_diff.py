#!/usr/bin/env python3
"""verdict_diff — the per-round gating-vs-shadow verdict diff record (issue #166, slice E of
epic #161's evidence loop).

Every gating review round (tools/dev-runner.sh's review_stage()) has its full transcript preserved
in the round's review bundle (tools/review_bundle.py's `rounds` list — review.md itself is
overwritten in place each round, so the bundle is the only per-round store). WHERE a shadow round
(issue #165) landed for that SAME round index, this tool pairs the two, extracts both verdicts with
one shared exact-match grammar, and emits one `yr-verdict-diff/1` record: `{round, gating, shadow,
agree}`. WHEN a round has no shadow record, nothing is emitted for it — never a synthesized
disagreement (a round with no shadow is not evidence of anything).

Grammar (shared with tools/dev-runner.sh's `verdict_line()` / `shadow_verdict_token()`, issue #151):
line-anchored `VERDICT:` (no leading whitespace, case-sensitive) — a prose or quoted mention never
counts — the LAST such line wins, trailing whitespace stripped. Applied identically to the gating
transcript and the shadow transcript, so the two verdicts are extracted like-for-like.

Merge outcome is NOT written here — slice F backfills it at aggregation time; the evaluator and
every gate are untouched by this tool. Best-effort by design: a caller that cannot read the bundle
or a shadow file for one round simply gets no record for that round, never a crash that would touch
the (unrelated) gating build.

Stdlib-only JSON-CLI, mirroring tools/review_bundle.py / tools/registry.py's shape.
"""
import argparse
import json
import pathlib
import sys

SCHEMA = "yr-verdict-diff/1"


def extract_verdict(text):
    """The shared exact-match grammar: line-anchored `VERDICT:`, last line wins, trailing
    whitespace stripped, bare token returned (e.g. "APPROVE"), or None if no such line landed."""
    lines = [line.rstrip() for line in text.splitlines() if line.startswith("VERDICT:")]
    return lines[-1][len("VERDICT:"):].strip() if lines else None


def shadow_path_for_round(run_dir, round_index):
    """Mirrors tools/dev-runner.sh's shadow_review_round() suffix pattern: round 1 ->
    shadow-review.md, round N (N>=2) -> shadow-review-N.md."""
    name = "shadow-review.md" if round_index == 1 else f"shadow-review-{round_index}.md"
    return run_dir / name


def record_path(run_dir, round_index):
    name = "verdict-diff.json" if round_index == 1 else f"verdict-diff-{round_index}.json"
    return run_dir / name


def comment_path(run_dir, round_index):
    name = "verdict-diff-comment.md" if round_index == 1 else f"verdict-diff-{round_index}-comment.md"
    return run_dir / name


def build_records(run_dir, bundle):
    """One record per gating round that has its OWN shadow round present in run_dir — a round with
    no shadow file emits nothing (never a synthesized disagreement)."""
    records = []
    for round_entry in bundle.get("rounds") or []:
        index = round_entry["index"]
        shadow_file = shadow_path_for_round(run_dir, index)
        if not shadow_file.exists():
            continue
        gating_transcript = round_entry.get("transcript") or ""
        shadow_transcript = shadow_file.read_text()
        gating_verdict = extract_verdict(gating_transcript)
        shadow_verdict = extract_verdict(shadow_transcript)
        agree = gating_verdict is not None and gating_verdict == shadow_verdict
        record = {
            "schema": SCHEMA,
            "round": index,
            "gating": gating_verdict,
            "shadow": shadow_verdict,
            "agree": agree,
        }
        if not agree:
            record["gating_transcript"] = gating_transcript
            record["shadow_transcript"] = shadow_transcript
        records.append(record)
    return records


def render_comment(record):
    """Inert by construction: field lines, then (on disagreement) blockquoted transcript excerpts —
    no line of the comment can match the line-anchored gating token `^VERDICT:` (the blockquote `> `
    prefix breaks the anchor, same trick as the shadow-review comment)."""
    lines = [
        f"YR-VERDICT-DIFF: {'agree' if record['agree'] else 'disagree'}",
        "",
        f"round: {record['round']}",
        f"gating: {record['gating']}",
        f"shadow: {record['shadow']}",
        f"agree: {'true' if record['agree'] else 'false'}",
    ]
    if not record["agree"]:
        lines.append("")
        lines.append("gating transcript:")
        lines.extend(f"> {line}" for line in record["gating_transcript"].splitlines())
        lines.append("")
        lines.append("shadow transcript:")
        lines.extend(f"> {line}" for line in record["shadow_transcript"].splitlines())
    return "\n".join(lines) + "\n"


def _cli_run(args):
    run_dir = pathlib.Path(args.run_dir)
    bundle_path = pathlib.Path(args.bundle)
    if not bundle_path.exists():
        return 0   # no bundle -> no gating round history to pair against; silent, never a crash
    with open(bundle_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)
    for record in build_records(run_dir, bundle):
        record_path(run_dir, record["round"]).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        cpath = comment_path(run_dir, record["round"])
        cpath.write_text(render_comment(record))
        print(cpath)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pair each gating review round with its shadow round and emit yr-verdict-diff/1 records.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="emit one record + one inert PR-comment body per paired round")
    p_run.add_argument("--run-dir", required=True, help="the run dir holding review-bundle.json and shadow-review*.md")
    p_run.add_argument("--bundle", required=True, help="path to review-bundle.json (tools/review_bundle.py)")
    p_run.set_defaults(func=_cli_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
