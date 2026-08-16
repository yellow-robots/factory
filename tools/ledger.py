#!/usr/bin/env python3
"""ledger — stage transcript archiving, the runner-owned transcript retention cap (issue #205, slice 1),
and the per-invocation ledger row (issue #206, slice 2) of epic yellow-robots/factory#204. Stdlib only,
like tools/stage_usage.py / tools/registry.py.

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

`append` (issue #206) writes ONE `yr-ledger-row/1` JSONL object to `rows.jsonl` in the ledger dir, at
whichever terminal branch a runner invocation reaches — census-weighted usage per stage, outcome,
repairs, wall-clock, identity. Usage comes from two sources: every `usage-*.json` artifact already in the
run dir (`tools/stage_usage.py`'s own loader — dedup-suffixed rounds included, `usage-summary.json`
excluded), plus, for a stage whose log still holds an UNEXTRACTED result envelope (an rc != 0 stage never
reaches `capture_stage_usage`), a read-only `find_result_envelope` pass over that log — never a rewrite.
Weights are `stage_usage.WEIGHTED_TOTAL_WEIGHTS`/`build_summary`, unchanged. A shadow-review-seat stage
is recorded in the per-stage array but excluded from the run's weighted total. The append itself holds a
BLOCKING flock on the ledger file (a row can exceed PIPE_BUF, so the OS's own small-write atomicity isn't
enough) so concurrent builds each land exactly one, uninterleaved row. Fail-soft throughout: every
function here degrades to an empty/best-effort result rather than raising on a missing run dir or log —
`tools/dev-runner.sh`'s own call site wraps this CLI so a failure warns and never blocks, fails, or gates
the run.

`per-model` / `report` (issue #207, epic #204 slice 3) are read-only aggregations over `rows.jsonl` —
never a write path, never a gate. Each stage's `price` is `tools/registry.py`'s `price_for_id()` snapshot
of that stage's `model` at append time (null when the id is unregistered or carries no price), stored
beside the raw counts so a row re-weights as a read (re-run `per-model`/`report`) rather than a re-run of
the build. `totals.shadow_cost_usd` sums `weighted_total × price` over the row's non-shadow, priced
stages only, divided by 1_000_000 (the AGENTS.md rule verbatim: the census weights are exactly the Claude
API price ratios, and price is $/Mtok — so the raw product is µ$, true dollars need the /1e6) — an
unpriced or shadow-review-seat stage contributes nothing to the sum but never causes the row itself, or
any other stage in it, to be skipped.

True units, self-describing eras (issue #313): a row built by this module carries `totals.cost_unit:
"usd"` — `shadow_cost_usd` is already true dollars. Disposition is READ-TIME, never a host rewrite of
`rows.jsonl` (pure JSONL, no header, `append_row` below / `read_rows`'s non-JSON skip): every reader
(`_row_shadow_cost` below, so transitively `per_model_view`/`close_time_cost`/`crossover_cost_axis`)
treats an ABSENT `cost_unit` as the pre-fix µ$ era and re-derives the true dollar figure from that row's
own `stages` (`weighted_total` × `price`, same non-shadow/priced filter, /1e6) rather than trusting the
stored (wrong-unit) `shadow_cost_usd` — so a mixed-era `rows.jsonl` aggregates correctly forever, no
migration, no file rewrite anywhere.

Gate durations (issue #313): `tools/dev-runner.sh` writes a run-dir artifact `gate-durations.json` — one
entry per `run_checks`/`run_lint`/`run_lens` invocation (`site`, `elapsed_seconds`, `disposition`).
`build_ledger_row` folds it into the row as a top-level `gates` list, fail-soft (a missing or unparseable
artifact yields an empty list, never raises) — informs window calibration only, never gates.

`per_model_view()`/`close_time_cost()`/`crossover_cost_axis()`/`daily_weighted_tokens()` are the four
standing reads (informing capacity/model decisions only — nothing here gates a build), windowed on
`ts_end` (a row's close time) via lexical ISO-8601 comparison.
"""
import argparse
import fcntl
import json
import os
import pathlib
import shutil
import sys
import time

# sibling-module import (never `tools.`-prefixed): run as a bare script (`tools/ledger.py ...`),
# sys.path[0] is already `tools/` — the same discipline tools/bench_replay.py documents for
# `import stage_usage` / `import registry`.
import registry
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


# ---------------------------------------------------------------------------
# append — one yr-ledger-row/1 JSONL row per runner invocation (issue #206).
# ---------------------------------------------------------------------------

ROW_SCHEMA = "yr-ledger-row/1"
REFUSAL_SCHEMA = "yr-ledger-refusal/1"


def build_refusal_row(*, repo, issue, site, reason, ts):
    """One fail-soft row per DoR refusal (it-31 slice 9): a refused invocation is work the factory
    performed, so the crossover's cost evidence counts it — while the cost aggregates themselves
    skip these rows (no stages, no tokens, no outcome)."""
    return {"schema": REFUSAL_SCHEMA, "repo": repo, "task": f"{repo}#{issue}",
            "site": site, "reason": reason, "ts_end": ts}


def _build_rows(rows):
    """The build-row population every COST aggregate reads: refusal rows (and any future foreign
    schema) are excluded here, in one place, so mixed rows.jsonl stays correct forever."""
    return [r for r in rows if r.get("schema") != REFUSAL_SCHEMA]

# Fixed per-run log artifacts that can still hold an UNEXTRACTED result envelope on an rc != 0 stage (the
# CLI never reached a clean exit, so tools/dev-runner.sh's capture_stage_usage was never called and the
# log was never rewritten): (log filename, the stage name it would use, the model-key naming which model
# resolves it). `review.md` is shared by both review rounds (the file is overwritten, not suffixed) —
# the same dedup-on-write convention as capture_stage_usage assigns it "review" or "review-2" here too.
_FIXED_LOG_STAGES = (
    ("implement.log", "implement", "build_model"),
    ("test.log", "test", "build_model"),
    ("repair.log", "repair", "check_repair_model"),
    ("review.md", "review", "review_model"),
    ("review-repair.log", "review-repair", "review_repair_model"),
)


def _stage_weighted_total(record):
    """The census-weighted total for ONE stage record — stage_usage.WEIGHTED_TOTAL_WEIGHTS (the same
    weights build_summary uses for the run-wide total), applied to a single record."""
    return round(sum(int(record.get(key) or 0) * w
                     for key, w in stage_usage.WEIGHTED_TOTAL_WEIGHTS.items()))


def _envelope_fallback_records(run_dir, models, taken_stage_names):
    """Additional per-stage usage records for logs whose stage never got a usage-<stage>.json (an rc != 0
    stage — capture_stage_usage only runs on a clean exit) but whose log STILL holds an unextracted
    result envelope. Read-only — never rewrites the log — resolved via stage_usage.find_result_envelope,
    the same parser tools/stage_usage.py itself uses, never a clone. `taken_stage_names` is the set of
    stage names already covered by a real usage-*.json file; a fresh record is assigned the next free
    dedup suffix (-2, -3, ...) the same way capture_stage_usage dedups its OWN output filename, so e.g. a
    second review round that failed after the first round already succeeded still lands as its own row,
    never overwriting or double-counting the first. The shadow review seat's own logs (`shadow-review*.md`,
    present only when the seat's env keys are set) are included the same way, tagged with the shadow
    model — never omitted, and never allowed to skip the whole row even when that model carries no
    registry entry (this function never consults the registry at all)."""
    run_dir = pathlib.Path(run_dir)
    candidates = list(_FIXED_LOG_STAGES)
    if models.get("shadow_model"):
        for p in sorted(run_dir.glob("shadow-review*.md")):
            candidates.append((p.name, p.stem, "shadow_model"))

    taken = set(taken_stage_names)
    records = []
    for log_name, base_stage, model_key in candidates:
        log_path = run_dir / log_name
        if not log_path.is_file():
            continue
        try:
            text = log_path.read_text(errors="replace")
        except Exception:
            continue
        envelope = stage_usage.find_result_envelope(text)
        if envelope is None:
            continue
        stage = base_stage
        n = 2
        while stage in taken:
            stage = f"{base_stage}-{n}"
            n += 1
        taken.add(stage)
        rec = stage_usage.usage_record(envelope, stage=stage, model=models.get(model_key) or None)
        rec["source"] = "envelope"
        records.append(rec)
    return records


def load_gate_durations(run_dir):
    """Fail-soft load of the run dir's `gate-durations.json` (issue #313) — `tools/dev-runner.sh` writes
    one entry per `run_checks`/`run_lint`/`run_lens` invocation (`site`, `elapsed_seconds`,
    `disposition`). A missing file, unparseable JSON, or a top-level shape that isn't a list all yield an
    empty list — never raises; the ledger informs, never gates, and a durations artifact is optional."""
    path = pathlib.Path(run_dir) / "gate-durations.json"
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


def build_ledger_row(*, run_id, task, repo, branch, base_sha, run_dir,
                      build_model, review_model, check_repair_model, review_repair_model, shadow_model,
                      outcome_type, outcome_decision, ts_start, ts_end, wall_seconds):
    """The `yr-ledger-row/1` object for ONE runner invocation. Never raises on a missing/empty run_dir (a
    Needs-info bounce runs before the run dir is created; a hard-killed run may never have written a
    single usage artifact) — an absent artifact just means an empty stage array, not an error."""
    run_dir_path = pathlib.Path(run_dir)

    usage_records = stage_usage.load_usage_records(run_dir)
    for r in usage_records:
        r["source"] = "usage-file"
    taken = {r.get("stage") for r in usage_records}

    models = {"build_model": build_model, "review_model": review_model,
              "check_repair_model": check_repair_model, "review_repair_model": review_repair_model,
              "shadow_model": shadow_model}
    stage_records = usage_records + _envelope_fallback_records(run_dir, models, taken)
    for r in stage_records:
        r["weighted_total"] = _stage_weighted_total(r)

    # The price snapshot (issue #207): each stage's registry input_price_per_mtok at append time, taken
    # by the stage's own model id — never by role — so a stage that ran under an override still prices
    # correctly. null (unregistered id, or a registered id with no price) never skips the stage or the row.
    registry_data = registry.load()
    for r in stage_records:
        r["price"] = registry.price_for_id(registry_data, r.get("model"))

    # Shadow-review-seat stages are recorded above but excluded from the run's weighted total (issue #206
    # acceptance criteria) — stage_usage.build_summary's own census weights, unchanged, over the rest.
    non_shadow = [r for r in stage_records if not str(r.get("stage") or "").startswith("shadow-review")]
    summary = stage_usage.build_summary(non_shadow)

    # Shadow cost (issue #207; true dollars per issue #313): weighted-total × the model's registry input
    # price, summed over the non-shadow stages that carry a price, divided by 1_000_000 — price is
    # $/Mtok (the AGENTS.md rule verbatim), so the raw product is µ$ and this is the /1e6 to true dollars.
    # A stage with price: null (no registry match) simply contributes nothing to the sum, never excludes
    # the row.
    shadow_cost_usd = sum(r["weighted_total"] * r["price"] for r in non_shadow
                           if r.get("price") is not None) / 1_000_000

    repairs = {
        "check": 1 if (run_dir_path / "repair.log").is_file() else 0,
        "review": 1 if (run_dir_path / "review-repair.log").is_file() else 0,
    }

    return {
        "schema": ROW_SCHEMA,
        "run_id": run_id,
        "task": task,
        "repo": repo,
        "branch": branch or None,
        "base_sha": base_sha or None,
        "models": {"build": build_model or None, "review": review_model or None},
        "stages": stage_records,
        "totals": {**summary["totals"], "weighted_total": summary["weighted_total"],
                   "shadow_cost_usd": shadow_cost_usd, "cost_unit": "usd"},
        "outcome": {"type": outcome_type, "decision": outcome_decision or None},
        "repairs": repairs,
        "gates": load_gate_durations(run_dir),
        "wall_seconds": wall_seconds,
        "ts_start": ts_start,
        "ts_end": ts_end,
    }


def append_row(ledger_dir, row):
    """Append ONE JSONL line to `<ledger_dir>/rows.jsonl` under a BLOCKING flock (a row can exceed
    PIPE_BUF, so the OS's own small-write atomicity guarantee isn't enough on its own) — concurrent
    builds each land exactly one, uninterleaved row. Creates the ledger dir/file on first use."""
    path = pathlib.Path(ledger_dir) / "rows.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True) + "\n"
    with open(path, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return path


# ---------------------------------------------------------------------------
# per-model / report — read-only aggregations over rows.jsonl (issue #207). Never a write path, never
# a gate: these inform (model choice, capacity headroom, cross-repo/before-after comparison) only.
# ---------------------------------------------------------------------------

def load_rows(ledger_dir):
    """Every row in `<ledger_dir>/rows.jsonl`, file order (oldest-appended first). A line that fails to
    parse is skipped (degrade, never crash a read over one bad row); a missing ledger dir/file yields an
    empty list — these are read-only reports, so there is nothing here to create."""
    path = pathlib.Path(ledger_dir) / "rows.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def filter_rows(rows, *, repo=None, since=None, until=None):
    """Rows matching `repo` (exact match, when given) and windowed on `ts_end` (a row's close time) via
    lexical ISO-8601 comparison (inclusive both ends) — the timestamps `tools/dev-runner.sh` stamps are
    always `%Y-%m-%dT%H:%M:%SZ`, so string order IS chronological order. `since`/`until` of None leave
    that side of the window open."""
    out = []
    for r in rows:
        if repo is not None and r.get("repo") != repo:
            continue
        ts_end = r.get("ts_end") or ""
        if since is not None and ts_end < since:
            continue
        if until is not None and ts_end > until:
            continue
        out.append(r)
    return out


def _stages_shadow_cost_usd(stages):
    """True-dollar shadow cost over a `stages` list — weighted_total × price, non-shadow-review-seat and
    priced stages only, /1_000_000 (price is $/Mtok). The same formula `build_ledger_row` uses to fill
    `totals.shadow_cost_usd` on a new row — used here to RE-DERIVE it, read-time, for a µ$-era row (issue
    #313) that carries no `cost_unit` and whose own stored `shadow_cost_usd` predates the /1e6 fix."""
    return sum((s.get("weighted_total") or 0) * s["price"] for s in stages
               if s.get("price") is not None
               and not str(s.get("stage") or "").startswith("shadow-review")) / 1_000_000


def _row_shadow_cost(row):
    """A row's true-dollar shadow cost — self-describing across eras (issue #313). `cost_unit == "usd"`
    means `totals.shadow_cost_usd` is already true dollars, trusted as stored; an ABSENT `cost_unit`
    marks the pre-fix µ$ era, whose stored figure is the wrong unit — re-derived instead from the row's
    own `stages` (never rewriting the row/file itself), so a mixed-era rows.jsonl aggregates correctly."""
    totals = row.get("totals") or {}
    if totals.get("cost_unit") == "usd":
        return totals.get("shadow_cost_usd") or 0
    return _stages_shadow_cost_usd(row.get("stages") or [])


def _row_repairs_count(row):
    repairs = row.get("repairs") or {}
    return int(repairs.get("check") or 0) + int(repairs.get("review") or 0)


def per_model_view(rows):
    """The per-model aggregate view (issue #207) — keyed by each row's BUILD model id (the axis a
    build-model trial varies; the id that actually executed the task). Per model: `runs` (row count);
    `merged` (outcome.type == 'merged' — armed merges ONLY, never conflated with 'shadow-would-merge',
    which lands as its own bucket in `verdict_outcomes` instead); `weighted_cost_per_merged_task` (that
    model's total shadow_cost_usd across ALL its rows, divided by its merged count — None when merged is
    0, a per-task figure being undefined with no completed task to divide by); `repair_rate` (total
    repairs.check + repairs.review across its rows, divided by runs); `verdict_outcomes` (a count per
    distinct outcome.type, straight from each row's own `outcome` field)."""
    by_model = {}
    for r in _build_rows(rows):
        model = (r.get("models") or {}).get("build")
        bucket = by_model.setdefault(model, {"runs": 0, "merged": 0, "cost": 0.0, "repairs": 0,
                                              "verdict_outcomes": {}})
        bucket["runs"] += 1
        bucket["cost"] += _row_shadow_cost(r)
        bucket["repairs"] += _row_repairs_count(r)
        outcome_type = (r.get("outcome") or {}).get("type")
        bucket["verdict_outcomes"][outcome_type] = bucket["verdict_outcomes"].get(outcome_type, 0) + 1
        if outcome_type == "merged":
            bucket["merged"] += 1

    view = {}
    for model, b in by_model.items():
        view[model] = {
            "runs": b["runs"],
            "merged": b["merged"],
            "weighted_cost_per_merged_task": (b["cost"] / b["merged"]) if b["merged"] else None,
            "repair_rate": (b["repairs"] / b["runs"]) if b["runs"] else 0,
            "verdict_outcomes": b["verdict_outcomes"],
        }
    return view


def close_time_cost(rows):
    """Standing read (1) — the close-time cost line: total `shadow_cost_usd` and the per-merged-task
    figure, over whatever rows the caller already narrowed to a repo/window (`filter_rows()`).
    Cost is a BUILD-row figure: refusal rows are excluded here (it-31 slice 9)."""
    rows = _build_rows(rows)
    total = sum(_row_shadow_cost(r) for r in rows)
    merged = sum(1 for r in rows if (r.get("outcome") or {}).get("type") == "merged")
    return {"total_shadow_cost_usd": total, "merged_count": merged,
            "cost_per_merged_task": (total / merged) if merged else None}


def crossover_cost_axis(rows, *, factory_repo="yellow-robots/factory"):
    """Standing read (2) — the crossover cost axis: the same close-time-cost figure, split into the
    factory's own repo vs every other (product) repo over the same window, plus the REFUSED
    invocation count per split (it-31 slice 9: the cost evidence stops under-counting refused
    work). `rows` should be window-filtered only (via `filter_rows()`, repo=None) — this function
    does the repo split itself, comparing two repo populations at once rather than being
    pre-narrowed to one."""
    factory_rows = [r for r in rows if r.get("repo") == factory_repo]
    product_rows = [r for r in rows if r.get("repo") != factory_repo]
    out = {"factory": close_time_cost(factory_rows), "product": close_time_cost(product_rows)}
    for key, pop in (("factory", factory_rows), ("product", product_rows)):
        out[key]["refused_invocations"] = sum(
            1 for r in pop if r.get("schema") == REFUSAL_SCHEMA)
    return out


def crossover_comment_body(ledger_dir, *, verdict, who, since="", until=""):
    """The YR-CROSSOVER record's body (it-31 slice 9): the cost field carries the crossover-cost
    axis actually read — both splits, refused invocations counted — so the verdict's evidence is in
    the record itself; the pricing judgment stays the human's."""
    rows = filter_rows(load_rows(ledger_dir), since=since or None, until=until or None)
    axis = crossover_cost_axis(rows)
    f, p = axis["factory"], axis["product"]
    window = f"; window {since or 'start'}..{until or 'now'}" if (since or until) else ""
    cost = (f"factory ${f['total_shadow_cost_usd']:.2f} over {f['merged_count']} merged builds "
            f"(+{f['refused_invocations']} refused) vs product ${p['total_shadow_cost_usd']:.2f} "
            f"over {p['merged_count']} merged builds (+{p['refused_invocations']} refused)"
            f"{window}")
    return (f"YR-CROSSOVER\n"
            f"cost: {cost}\n"
            f"verdict: {verdict}\n"
            f"who: {who}\n\n"
            "The crossover test's typed verdict (it-31 slice 9): the cost evidence above is the "
            "ledger's crossover-cost axis, read at close — the pricing judgment stays the human's.")


def daily_weighted_tokens(rows):
    """Standing read (4) — the concurrency headroom: weighted tokens per day, summed ACROSS every repo
    in `rows` (window-filtered only via `filter_rows()`, repo=None — headroom is a host-wide figure, not
    a per-repo one). Bucketed by the date portion (first 10 chars) of each row's `ts_end`; a row with no
    `ts_end` contributes to no bucket."""
    by_day = {}
    for r in _build_rows(rows):
        day = (r.get("ts_end") or "")[:10]
        if not day:
            continue
        weighted_total = (r.get("totals") or {}).get("weighted_total") or 0
        by_day[day] = by_day.get(day, 0) + weighted_total
    return dict(sorted(by_day.items()))


def _cli_archive(args):
    result = archive_transcript(args.log, args.slug_dir, args.out)
    print(json.dumps(result))
    return 0 if result["status"] == "archived" else 1


def _cli_prune(args):
    result = prune_transcripts(args.runs_dir, max_age_days=args.max_age_days, max_gb=args.max_gb)
    print(json.dumps(result))
    return 0


def _cli_append(args):
    row = build_ledger_row(
        run_id=args.run_id, task=args.task, repo=args.repo, branch=args.branch, base_sha=args.base_sha,
        run_dir=args.run_dir, build_model=args.build_model, review_model=args.review_model,
        check_repair_model=args.check_repair_model, review_repair_model=args.review_repair_model,
        shadow_model=args.shadow_model, outcome_type=args.outcome_type,
        outcome_decision=args.outcome_decision, ts_start=args.ts_start, ts_end=args.ts_end,
        wall_seconds=args.wall_seconds,
    )
    append_row(args.ledger_dir, row)
    return 0


def _cli_per_model(args):
    rows = filter_rows(load_rows(args.ledger_dir), repo=args.repo or None,
                        since=args.since or None, until=args.until or None)
    print(json.dumps(per_model_view(rows), sort_keys=True))
    return 0


def _cli_refusal(args):
    """Fail-soft by contract: the refusing caller (dev-runner's gate(), exit 3) must never be
    blocked, failed, or altered by its own observability — any error is a stderr note, exit 0."""
    try:
        row = build_refusal_row(repo=args.repo, issue=args.issue, site=args.site,
                                reason=args.reason,
                                ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        append_row(args.ledger_dir, row)
    except Exception as e:  # noqa: BLE001 — informs, never gates
        print(f"ledger: refusal row not appended ({e}) — fail-soft, the refusal stands",
              file=sys.stderr)
    return 0


def _cli_crossover(args):
    import subprocess
    body = crossover_comment_body(args.ledger_dir, verdict=args.verdict, who=args.who,
                                  since=args.since, until=args.until)
    if args.test_mode:
        print("TEST-MODE: no trail write — the record only")
        print(body)
        return 0
    gh = os.environ.get("GH_BIN", "gh")
    out = subprocess.run([gh, "issue", "comment", str(args.issue), "--repo", args.repo,
                          "--body", body], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        print(f"ledger: crossover comment failed: {(out.stderr or out.stdout or '').strip()[:300]}",
              file=sys.stderr)
        return 1
    print(f"crossover: YR-CROSSOVER posted on {args.repo}#{args.issue} (verdict={args.verdict})")
    return 0


def _cli_report(args):
    windowed = filter_rows(load_rows(args.ledger_dir), since=args.since or None, until=args.until or None)
    if args.kind == "close-time-cost":
        result = close_time_cost(filter_rows(windowed, repo=args.repo or None))
    elif args.kind == "crossover-cost":
        result = crossover_cost_axis(windowed, factory_repo=args.factory_repo)
    elif args.kind == "concurrency-headroom":
        result = daily_weighted_tokens(windowed)
    else:
        print(json.dumps({"error": f"unknown report kind '{args.kind}'"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Stage transcript archiving + retention cap (#205); the ledger row (#206); "
                     "the per-model view + the four standing reads (#207).")
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

    p_app = sub.add_parser("append", help="append one yr-ledger-row/1 JSONL row for this runner invocation (issue #206)")
    p_app.add_argument("--ledger-dir", required=True, help="the ledger dir (e.g. $DEV_RUNNER_HOME/ledger); rows.jsonl lives here")
    p_app.add_argument("--run-id", required=True, help="basename of the run dir, e.g. '<issue>-<pid>'")
    p_app.add_argument("--task", required=True, help="owner/repo#issue — passed explicitly, never derived from the run dir")
    p_app.add_argument("--repo", required=True)
    p_app.add_argument("--branch", default="")
    p_app.add_argument("--base-sha", default="")
    p_app.add_argument("--run-dir", required=True, help="the run dir to scan for usage-*.json / stage logs (need not exist yet)")
    p_app.add_argument("--build-model", default="")
    p_app.add_argument("--review-model", default="")
    p_app.add_argument("--check-repair-model", default="")
    p_app.add_argument("--review-repair-model", default="")
    p_app.add_argument("--shadow-model", default="", help="the shadow-review-seat model id, or empty when the seat is dark")
    p_app.add_argument("--outcome-type", required=True,
                        help="needs-info | blocked | env-hold | merged | shadow-would-merge | shadow-would-block | in-review")
    p_app.add_argument("--outcome-decision", default="")
    p_app.add_argument("--ts-start", required=True)
    p_app.add_argument("--ts-end", required=True)
    p_app.add_argument("--wall-seconds", type=int, required=True)
    p_app.set_defaults(func=_cli_append)

    p_ref = sub.add_parser("refusal", help="append one fail-soft yr-ledger-refusal/1 row (it-31 slice 9: gate() refusals reach the ledger; never blocks, never changes the caller's exit)")
    p_ref.add_argument("--ledger-dir", required=True)
    p_ref.add_argument("--repo", required=True)
    p_ref.add_argument("--issue", required=True)
    p_ref.add_argument("--site", required=True, help="the refusing site, e.g. 'gate'")
    p_ref.add_argument("--reason", required=True)
    p_ref.set_defaults(func=_cli_refusal)

    p_xo = sub.add_parser("crossover", help="post the YR-CROSSOVER record on an epic's trail (it-31 slice 9: the cost evidence is this ledger's crossover-cost axis)")
    p_xo.add_argument("--ledger-dir", required=True)
    p_xo.add_argument("--repo", required=True)
    p_xo.add_argument("--issue", required=True, help="the closing epic's issue number")
    p_xo.add_argument("--verdict", required=True)
    p_xo.add_argument("--who", required=True)
    p_xo.add_argument("--since", default="")
    p_xo.add_argument("--until", default="")
    p_xo.add_argument("--test-mode", action="store_true",
                      help="print the record; write nothing to any trail")
    p_xo.set_defaults(func=_cli_crossover)

    p_pm = sub.add_parser("per-model", help="the per-model aggregate view over rows.jsonl (issue #207)")
    p_pm.add_argument("--ledger-dir", required=True, help="the ledger dir (e.g. $DEV_RUNNER_HOME/ledger); rows.jsonl lives here")
    p_pm.add_argument("--repo", default="", help="restrict to one repo (owner/name); default: every repo")
    p_pm.add_argument("--since", default="", help="ISO-8601 lower bound on a row's ts_end, inclusive")
    p_pm.add_argument("--until", default="", help="ISO-8601 upper bound on a row's ts_end, inclusive")
    p_pm.set_defaults(func=_cli_per_model)

    p_rep = sub.add_parser("report", help="the other three standing reads over rows.jsonl (issue #207)")
    p_rep.add_argument("--kind", required=True,
                        choices=["close-time-cost", "crossover-cost", "concurrency-headroom"],
                        help="close-time-cost (repo/window); crossover-cost (factory vs product "
                             "repo, window); concurrency-headroom (weighted tokens/day, window)")
    p_rep.add_argument("--ledger-dir", required=True, help="the ledger dir (e.g. $DEV_RUNNER_HOME/ledger); rows.jsonl lives here")
    p_rep.add_argument("--repo", default="", help="close-time-cost only: restrict to one repo; ignored by the other kinds")
    p_rep.add_argument("--factory-repo", default="yellow-robots/factory", help="crossover-cost only: the repo counted as 'factory'; every other repo is 'product'")
    p_rep.add_argument("--since", default="", help="ISO-8601 lower bound on a row's ts_end, inclusive")
    p_rep.add_argument("--until", default="", help="ISO-8601 upper bound on a row's ts_end, inclusive")
    p_rep.set_defaults(func=_cli_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
