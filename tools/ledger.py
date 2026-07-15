#!/usr/bin/env python3
"""ledger — stage transcript archiving + the runner-owned transcript retention cap (issue #205, slice 1
of epic yellow-robots/factory#204). Stdlib only, like tools/stage_usage.py / tools/registry.py.

Every completed stage's full CLI session transcript (`~/.claude/projects/<slug>/<session_id>.jsonl`) is
copied into the run dir as `transcript-<stage>.jsonl` — a run artifact independent of the CLI's own
retention, for forensic recovery of a stage's full session (e.g. a signal-killed stage; the gilda#9
motivating case). `tools/dev-runner.sh`'s `archive_stage_transcript` shells out to this module's
`archive` subcommand at every stage's end, BEFORE `capture_stage_usage` rewrites the stage log (on a
clean exit) — so the log is always read intact here, never after its own rewrite.

Resolution imports `tools/stage_usage.py`'s `find_result_envelope` (never a cloned parser) to pull
`session_id` off the log's result envelope. No envelope, no `session_id`, or the named transcript file
missing (e.g. a signal-killed stage never got to write one) -> the newest `.jsonl` in the CLI project
slug dir, since stages serialize per worktree (the newest file at stage end IS this stage's own
transcript) — a heuristic, always so-labeled. An empty or absent slug dir is the only true skip.

No redaction (ruled 2026-07-15): the archive copies byte-faithful. Archiving is fail-soft throughout —
a failure is reported, never raised; it never blocks or fails the stage/run.

`prune` deletes `transcript-*.jsonl` under a runs/ dir past a runner-owned retention cap (age, then
size) — never any other run-dir artifact, never a dispatch log — also fail-soft. Tunables
LEDGER_TRANSCRIPT_MAX_AGE_DAYS / LEDGER_TRANSCRIPT_MAX_GB (env > default) are read as argparse defaults,
so an explicit CLI flag (tests) still wins over both.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys
import time

# sibling-module import (never `tools.`-prefixed): run as a bare script (`tools/ledger.py ...`),
# sys.path[0] is already `tools/` — the same discipline tools/bench_replay.py documents for
# `import stage_usage` / `import registry`.
import stage_usage

DEFAULT_MAX_AGE_DAYS = 90
DEFAULT_MAX_GB = 10


def _newest_jsonl(slug_dir):
    """The most-recently-modified `.jsonl` file directly under `slug_dir`, or None if the directory is
    absent or holds none."""
    d = pathlib.Path(slug_dir)
    if not d.is_dir():
        return None
    candidates = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def resolve_transcript(log_path, slug_dir):
    """Resolve the just-finished stage's CLI session transcript. Reads `log_path` READ-ONLY (never
    rewrites it) — safe to call before `stage_usage.process_stage_log`'s in-place rewrite.

    Returns `(path, "session_id")` when the envelope's session_id names an existing transcript file,
    `(path, "heuristic-newest")` on the newest-.jsonl-in-slug-dir fallback, or `(None, reason)` when
    nothing is resolvable (`reason` names why — never raises)."""
    text = pathlib.Path(log_path).read_text(errors="replace")
    envelope = stage_usage.find_result_envelope(text)
    session_id = envelope.get("session_id") if envelope else None
    if session_id:
        candidate = pathlib.Path(slug_dir) / f"{session_id}.jsonl"
        if candidate.is_file():
            return candidate, "session_id"
    newest = _newest_jsonl(slug_dir)
    if newest is not None:
        return newest, "heuristic-newest"
    reason = "slug dir absent" if not pathlib.Path(slug_dir).is_dir() else "slug dir empty"
    return None, reason


def archive_transcript(log_path, slug_dir, dest_path):
    """Best-effort: resolve + byte-faithful copy the stage's session transcript to `dest_path`. Returns
    a status dict; never raises (fail-soft — archiving must never block or fail the run)."""
    try:
        source, method = resolve_transcript(log_path, slug_dir)
    except Exception as e:
        return {"status": "error", "reason": str(e)}
    if source is None:
        return {"status": "skipped", "reason": method}
    try:
        shutil.copy2(source, dest_path)
    except Exception as e:
        return {"status": "error", "reason": str(e)}
    return {"status": "archived", "method": method, "source": str(source), "dest": str(dest_path)}


def _transcript_files(runs_dir):
    return list(pathlib.Path(runs_dir).rglob("transcript-*.jsonl"))


def prune_transcripts(runs_dir, *, max_age_days, max_gb):
    """Delete `transcript-*.jsonl` files under `runs_dir`: first any older than `max_age_days`, then
    (oldest mtime first) whatever's left above `max_gb` total. Touches ONLY transcript-*.jsonl files —
    never another run-dir artifact, never a dispatch log. Fail-soft per file: a delete failure is
    recorded and skipped, never raised. Returns a summary dict."""
    deleted, errors = [], []
    max_age_seconds = max_age_days * 86400
    now = time.time()

    kept = []
    for p in _transcript_files(runs_dir):
        try:
            st = p.stat()
        except OSError as e:
            errors.append({"path": str(p), "reason": str(e)})
            continue
        if now - st.st_mtime > max_age_seconds:
            try:
                p.unlink()
                deleted.append(str(p))
            except OSError as e:
                errors.append({"path": str(p), "reason": str(e)})
        else:
            kept.append((p, st))

    max_bytes = max_gb * (1024 ** 3)
    kept.sort(key=lambda t: t[1].st_mtime)  # oldest first
    total = sum(st.st_size for _, st in kept)
    i = 0
    while total > max_bytes and i < len(kept):
        p, st = kept[i]
        i += 1
        try:
            p.unlink()
            deleted.append(str(p))
            total -= st.st_size
        except OSError as e:
            errors.append({"path": str(p), "reason": str(e)})

    return {"deleted": deleted, "deleted_count": len(deleted), "errors": errors}


def _cli_archive(args):
    result = archive_transcript(args.log, args.slug_dir, args.out)
    print(json.dumps(result))
    return 0 if result["status"] == "archived" else 1


def _cli_prune(args):
    result = prune_transcripts(args.runs_dir, max_age_days=args.max_age_days, max_gb=args.max_gb)
    print(json.dumps(result))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage transcript archiving + retention cap (issue #205).")
    sub = ap.add_subparsers(dest="command", required=True)

    p_arc = sub.add_parser("archive", help="archive a just-finished stage's CLI session transcript into the run dir")
    p_arc.add_argument("--log", required=True, help="the stage log file (read-only; never rewritten)")
    p_arc.add_argument("--slug-dir", required=True, help="the CLI project slug dir to resolve/fall back into")
    p_arc.add_argument("--out", required=True, help="destination path for the archived transcript-<stage>.jsonl")
    p_arc.set_defaults(func=_cli_archive)

    p_prune = sub.add_parser("prune", help="delete transcript-*.jsonl under --runs-dir past the age/size retention cap")
    p_prune.add_argument("--runs-dir", required=True, help="the runs/ dir to prune (e.g. $DEV_RUNNER_HOME/runs)")
    p_prune.add_argument("--max-age-days", type=int,
                          default=int(os.environ.get("LEDGER_TRANSCRIPT_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS)),
                          help="delete transcripts older than this many days (env: LEDGER_TRANSCRIPT_MAX_AGE_DAYS)")
    p_prune.add_argument("--max-gb", type=float,
                          default=float(os.environ.get("LEDGER_TRANSCRIPT_MAX_GB", DEFAULT_MAX_GB)),
                          help="above this total size (GB), delete oldest-first (env: LEDGER_TRANSCRIPT_MAX_GB)")
    p_prune.set_defaults(func=_cli_prune)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
