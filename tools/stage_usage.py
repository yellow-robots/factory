#!/usr/bin/env python3
"""stage_usage — extract a `claude --output-format json` result envelope from a stage log, rewrite
the log to the plain reply text, and file the token/cache usage as a per-stage artifact (issue #48).
Stdlib only, like tools/review_bundle.py / tools/merge_shadow.py / tools/registry.py.

`claude -p ... --output-format json` prints exactly one JSON object as a single line of stdout
(`{"type":"result",...,"result":"<the reply text>","usage":{...},"duration_ms":...}`). Pairing
`--output-format json` with `--verbose` turns that into a JSON ARRAY of stream events instead (verified
against the live CLI) — so tools/dev-runner.sh's new default omits `--verbose`, keeping it only for the
old, explicit `CLAUDE_OUTPUT_FORMAT` override (byte-identical prior behavior, extraction never attempted
there). `run_stage` merges stderr into the same log file, and pre-isolation hook/MCP warnings land there
too, so extraction tolerates surrounding non-JSON noise: it scans the log LINE BY LINE (the CLI's own
envelope is always exactly one line) for the LAST line that parses as JSON with `"type": "result"`,
ignoring every other line rather than requiring a byte-clean envelope.

Every existing consumer of a stage log (the fail-closed verdict gate, review_bundle.py, the repair
prompts, the PR-attached review) must keep seeing plain text with byte-identical semantics — so a
successful extraction REWRITES the log to just `.result`, filing the counts/model/duration alongside as
a separate `usage-<stage>.json`, never inline. A log that never held a result envelope (plain text, e.g.
the stubbed test suite's `claude`, or an explicit non-json CLAUDE_OUTPUT_FORMAT) is left completely
untouched and no usage file is written — degrade, never mask the stage's own success or failure.
"""
import argparse
import json
import pathlib
import sys

# The CLI's own `usage` object keys -> this artifact's keys (fresh input / output / cache write / cache
# read, per the acceptance criteria's wording).
USAGE_FIELDS = (
    ("input_tokens", "input_tokens"),
    ("output_tokens", "output_tokens"),
    ("cache_creation_input_tokens", "cache_write_tokens"),
    ("cache_read_input_tokens", "cache_read_tokens"),
)

# The it-8 census cost measure (benchmark protocol on yellow-robots/factory#47): fresh input, output,
# cache-write, cache-read weights for the census-weighted token total.
WEIGHTED_TOTAL_WEIGHTS = {
    "input_tokens": 1,
    "output_tokens": 5,
    "cache_write_tokens": 1.25,
    "cache_read_tokens": 0.1,
}


def find_result_envelope(text):
    """The LAST line in `text` that parses as JSON with `"type": "result"`, or None. Line-based (not a
    full-text brace scan) because the CLI's envelope is always exactly one physical line — so any
    unmatched quote/brace in a surrounding hook/MCP warning line can never desync the parse of a
    different line."""
    best = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            best = obj
    return best


def usage_record(envelope, *, stage, model):
    """The per-stage usage artifact. Missing fields (a field the CLI omitted) are simply left out —
    additive, forward-compatible — rather than defaulted to zero."""
    usage = envelope.get("usage") or {}
    record = {"stage": stage, "model": model or None}
    duration = envelope.get("duration_ms")
    if duration is not None:
        record["duration_ms"] = duration
    session_id = envelope.get("session_id")
    if session_id is not None:
        record["session_id"] = session_id
    for cli_key, out_key in USAGE_FIELDS:
        if cli_key in usage:
            record[out_key] = usage[cli_key]
    return record


def process_stage_log(log_path, *, stage, model):
    """Best-effort: if `log_path` holds a result envelope, rewrite it to the plain reply text and
    return the usage record. Otherwise leave the file untouched and return None."""
    path = pathlib.Path(log_path)
    text = path.read_text(errors="replace")
    envelope = find_result_envelope(text)
    if envelope is None:
        return None
    path.write_text(envelope.get("result") or "")
    return usage_record(envelope, stage=stage, model=model)


def load_usage_records(run_dir):
    """Every `usage-*.json` artifact in `run_dir` (never the aggregate `usage-summary.json` itself),
    sorted by filename for a stable per-stage order. A record file that fails to parse is skipped
    (degrade, never crash the summary over one bad artifact)."""
    records = []
    for p in sorted(pathlib.Path(run_dir).glob("usage-*.json")):
        if p.name == "usage-summary.json":
            continue
        try:
            records.append(json.loads(p.read_text()))
        except Exception:
            continue
    return records


def build_summary(records):
    totals = {out_key: 0 for _, out_key in USAGE_FIELDS}
    for r in records:
        for out_key in totals:
            totals[out_key] += int(r.get(out_key) or 0)
    weighted_total = round(sum(totals[k] * w for k, w in WEIGHTED_TOTAL_WEIGHTS.items()))
    return {"stages": records, "totals": totals, "weighted_total": weighted_total}


def render_summary_comment(summary):
    """`### dev-runner usage` + a per-stage table + totals + the fenced raw JSON. Deliberately carries
    no `YR-`-prefixed marker line anywhere (that grammar belongs to tools/merge_shadow.py alone) so the
    shadow-completion parser never mistakes this for a merge record."""
    lines = ["### dev-runner usage", ""]
    stages = summary.get("stages") or []
    if not stages:
        lines.append("_no per-stage usage artifacts were recorded for this run._")
    else:
        lines.append("| stage | model | fresh input | output | cache write | cache read | duration (ms) |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in stages:
            lines.append("| {stage} | {model} | {input_tokens} | {output_tokens} | {cache_write_tokens} | {cache_read_tokens} | {duration_ms} |".format(
                stage=r.get("stage", ""), model=r.get("model") or "",
                input_tokens=r.get("input_tokens", ""), output_tokens=r.get("output_tokens", ""),
                cache_write_tokens=r.get("cache_write_tokens", ""), cache_read_tokens=r.get("cache_read_tokens", ""),
                duration_ms=r.get("duration_ms", ""),
            ))
        t = summary["totals"]
        lines.append("| **total** |  | **{input_tokens}** | **{output_tokens}** | **{cache_write_tokens}** | **{cache_read_tokens}** |  |".format(**t))
        lines.append("**weighted total: {}** (fresh input ×1 · output ×5 · cache-write ×1.25 · cache-read ×0.1)".format(summary["weighted_total"]))
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary, indent=2, sort_keys=True))
    lines.append("```")
    return "\n".join(lines) + "\n"


def _cli_extract(args):
    record = process_stage_log(args.log, stage=args.stage, model=args.model)
    if record is None:
        return 1
    pathlib.Path(args.out).write_text(json.dumps(record, indent=2, sort_keys=True))
    return 0


def _cli_summarize(args):
    summary = build_summary(load_usage_records(args.run_dir))
    pathlib.Path(args.out_json).write_text(json.dumps(summary, indent=2, sort_keys=True))
    pathlib.Path(args.out_comment).write_text(render_summary_comment(summary))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Per-stage usage capture + PR usage summary (issue #48).")
    sub = ap.add_subparsers(dest="command", required=True)

    p_ex = sub.add_parser("extract", help="extract a result envelope from a stage log, rewrite it to plain text")
    p_ex.add_argument("--log", required=True, help="the stage log file (rewritten in place on success)")
    p_ex.add_argument("--stage", required=True, help="stage name, for the usage artifact + summary table")
    p_ex.add_argument("--model", default="", help="the model id this stage ran with")
    p_ex.add_argument("--out", required=True, help="path to write the usage-<stage>.json artifact")
    p_ex.set_defaults(func=_cli_extract)

    p_sum = sub.add_parser("summarize", help="aggregate usage-*.json artifacts into the PR usage summary")
    p_sum.add_argument("--run-dir", required=True)
    p_sum.add_argument("--out-json", required=True, help="path to write the aggregate usage-summary.json")
    p_sum.add_argument("--out-comment", required=True, help="path to write the PR comment body")
    p_sum.set_defaults(func=_cli_summarize)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
