#!/usr/bin/env python3
"""kpi.py — the KPI report on demand (it-36 slice J, #475).

Regenerates a component's month-to-date KPI note from NATIVE surfaces alone — never the build
host's ledger (`tools/round_record.py`'s own rule, inherited): PR-usage comments (velocity, spend,
blocked/repair rates), issue timelines (cycle time), `git log` (revert rate), the board (backlog
age), the ideas folder's frontmatter (inflow/outflow, the product-versus-factory ratio), and the
`YR-DEPLOY` trail (#464, deploy lag) — each metric read against the strategy doc's own
`kpi_targets` (`tools/strategy.py`). Writes one note per month into the component's operations home
through the vault client and posts `YR-KPI`; when the strategy doc's own content hash has moved
since the last run, also posts `YR-STRATEGY` (records.toml — both rows minted ahead of this slice).

Two layers, like every other machinery tool in this tree (`tools/round_record.py`/
`tools/design_gate.py`'s own shape):
  * PURE metric functions below take ALREADY-FETCHED data (fixture-friendly: a list of merge
    timestamps, a list of PR-usage dicts, a list of board-item dicts, ...) and never do I/O —
    the whole point is that a test can hand them canned fixtures and check the arithmetic.
  * `main()`/`gather_report_inputs()` do the real reads (`gh`, `git`, the vault client) and are the
    only place a live surface is touched; every external is an injectable seam, no live network in
    a test.

Attended-invoked today, like `tools/changelog.py` (slice I, #474)'s own RULING: no cron/sweep wires
this automatically in this slice ("Runner-built: not gate-touching" — the acceptance criterion's own
words) — a human runs `kpi.py report ...` "on request" today, and the strategy-doc-hash check inside
THIS run is what decides whether `YR-STRATEGY` also posts. The design sweep's own automatic trigger
(run the report the moment the strategy doc's hash changes, never waiting on a human's "on request")
is deliberately not wired here — the sweep trigger is #520's, filed at this slice's #475 fold review
(cold review round 1) rather than folded into this build.

`--code-root` (B2, #475 fold review round 1) is a SEPARATE, optional local checkout from
`--component-root`: `component_root` is the vault-mirror path everywhere else in this tree
(`tools/design_gate.py`'s own `next_iteration_slug`/`resolve_activation_paths`, this file's own
`--help`) — reading `git log` there for revert detection would read the VAULT's own commit history,
never the product's. `code_root`, when given, is the local checkout of the component's OWN code repo;
absent, revert detection is fail-closed (`None`, never a silently-empty 0/0), and the note states the
surface was never declared rather than printing a number nobody read.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from statistics import mean

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drift             # noqa: E402 — the shared YR-DEPLOY well-formedness parser (I4, #475 fold review)
import rank             # noqa: E402
import records          # noqa: E402
import round_record     # noqa: E402 — NEEDS_INFO_PREFIX / BLOCKED_PREFIX, the runner's own bounce prose
import sources          # noqa: E402
import strategy         # noqa: E402
import textutil         # noqa: E402
import vault_api        # noqa: E402

GH_TIMEOUT = int(os.environ.get("YR_KPI_GH_TIMEOUT", "20"))
DEV_RUNNER_HOME = os.environ.get("DEV_RUNNER_HOME", str(pathlib.Path.home() / ".cache" / "dev-runner"))
DEPLOY_TRAIL_REPO = "yellow-robots/factory"
DEPLOY_TRAIL_ISSUE = "464"
FACTORY_REPO = "yellow-robots/factory"


# --- small shared helpers -------------------------------------------------------------------------

def _parse_iso(ts: str) -> datetime.datetime:
    """A GitHub ISO-8601 UTC timestamp -> an aware datetime. Never raises on a well-formed
    `...Z` string (the shape every `gh`/vault timestamp in this tree carries)."""
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _hours_between(a: str, b: str) -> float:
    return (_parse_iso(b) - _parse_iso(a)).total_seconds() / 3600.0


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def month_bounds(period: str) -> tuple[str, str]:
    """`"YYYY-MM"` -> `(start, end)` ISO-8601 UTC bounds, `end` exclusive (the first instant of the
    NEXT month) — the one month-window computation every metric below shares."""
    year, month = (int(x) for x in period.split("-"))
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=datetime.timezone.utc)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def current_period(now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m")


# --- velocity: merged PRs per week (sources.pr_usage over the repo's merged PRs) --------------------

def velocity_per_week(merge_dates: list[str], *, start: str, end: str) -> dict:
    """Merged-PR count over the window, normalized to a per-week rate."""
    weeks = max(_hours_between(start, end) / (24 * 7), 1e-9)
    merged = len(merge_dates)
    return {"merged": merged, "weeks": round(weeks, 2), "per_week": round(merged / weeks, 2)}


# --- cycle time: the issue timeline (created -> Ready -> merged) ------------------------------------

def cycle_time_hours(events: list[dict]) -> dict:
    """`events`: `{"created": iso, "ready_at": iso|None, "merged": iso, "link_status": ...}` per
    delivered issue. `mean_total_hours` is created->merged (the lead time every event with both
    bounds contributes); `mean_queue_hours` is created->Ready, reported only from events that
    actually carry a `ready_at` (GitHub's REST/GraphQL surfaces expose no per-field ProjectV2
    status-change history without the audit-log API — an event missing it degrades this ONE figure,
    never the whole metric, and is never guessed at).

    `gap_reason` (B1, #475 fold review round 2): `None` once at least one event resolved a
    `created` — otherwise names WHY none did, distinguishing "no merged PR named a linked issue"
    from "a linked issue's own read failed" (`link_status`, `gather_report_inputs`'s own field) —
    never one blanket claim that could misstate which actually happened this window."""
    total = [_hours_between(e["created"], e["merged"]) for e in events if e.get("created") and e.get("merged")]
    queue = [_hours_between(e["created"], e["ready_at"]) for e in events if e.get("created") and e.get("ready_at")]
    gap_reason = None
    if not total:
        if not events:
            gap_reason = "no PR merged this window"
        else:
            no_link = sum(1 for e in events if e.get("link_status") == "no_linked_issue")
            failed = sum(1 for e in events if e.get("link_status") == "read_failed")
            if no_link and failed:
                gap_reason = (f"{no_link} merged PR(s) named no linked issue, "
                              f"{failed} linked-issue read(s) failed")
            elif failed:
                gap_reason = "the linked issue's own read failed for every merged PR this window"
            elif no_link:
                gap_reason = "no merged PR named a linked issue this window"
            else:
                gap_reason = "no merged PR resolved a linked issue's own createdAt this window"
    return {"mean_total_hours": _mean(total), "mean_queue_hours": _mean(queue), "count": len(total),
           "gap_reason": gap_reason}


# --- blocked / repair rates: the runner's own bounce/block prose + a repair stage in the PR's usage --

def blocked_rate(pr_trails: list[list[str]]) -> dict:
    """`pr_trails`: one comment-body list per merged PR (`sources.pr_trail_texts_from_json`'s own
    shape). A PR counts as blocked once, however many bounce/Blocked comments it carries — the
    runner's own prose (`tools/round_record.py`'s `NEEDS_INFO_PREFIX`/`BLOCKED_PREFIX`), never a
    second, re-implemented prefix pair."""
    total = len(pr_trails)
    blocked = sum(
        1 for texts in pr_trails
        if any(t.startswith(round_record.NEEDS_INFO_PREFIX) or t.startswith(round_record.BLOCKED_PREFIX)
              for t in texts)
    )
    return {"blocked": blocked, "total": total, "rate": round(blocked / total, 3) if total else None}


def repair_rate(pr_usages: list[dict]) -> dict:
    """`pr_usages`: one `sources.pr_usage_from_texts`-shaped dict per merged PR — a PR counts as
    repaired once any of its usage summary's own stage names ends `_repair` (`check_repair` /
    `review_repair` / `lint_repair`, `tools/dev-runner.sh`'s own stage names)."""
    total = len(pr_usages)
    repaired = sum(
        1 for u in pr_usages
        if any((s.get("stage") or "").endswith("_repair") for s in (u.get("stages") or []))
    )
    return {"repaired": repaired, "total": total, "rate": round(repaired / total, 3) if total else None}


# --- revert rate: git log --------------------------------------------------------------------------

REVERT_PREFIX = "Revert "


def revert_rate(commit_subjects: list[str] | None) -> dict:
    """`commit_subjects`: one commit subject line per commit in the window (`git log --format=%s`,
    read from `--code-root`, NEVER the vault-mirror `component_root` — B2, #475 fold review round 1).
    GitHub's own revert-commit convention (`Revert "<original subject>"`) is the one grammar read —
    never a heuristic over diff content.

    `None` (not `[]`) means the surface was never declared at all — `--code-root` absent this run —
    and stays a THREE-None triple, distinct from a declared-but-empty window (`[]`, a real read that
    just found zero commits): conflating the two would let a note print "0/0" and read as a fact
    about the code when nobody ever looked."""
    if commit_subjects is None:
        return {"reverts": None, "total": None, "rate": None}
    total = len(commit_subjects)
    reverts = sum(1 for s in commit_subjects if s.startswith(REVERT_PREFIX))
    return {"reverts": reverts, "total": total, "rate": round(reverts / total, 3) if total else None}


# --- spend: sources.pr_usage's own cost_usd, summed --------------------------------------------------

def total_spend_usd(pr_usages: list[dict]) -> float:
    return round(sum(u.get("cost_usd") or 0.0 for u in pr_usages), 2)


# --- backlog age: the board, with createdAt (tools/board.sh's own query gained the field) -----------

def backlog_age_days(board_rows: list[dict], *, now: str) -> dict:
    """`board_rows`: open board items (`{"createdAt": iso, ...}`, board.sh's own paged query shape) —
    mean age, in days, of everything currently sitting on the board."""
    ages = [_hours_between(r["createdAt"], now) / 24 for r in board_rows if r.get("createdAt")]
    return {"mean_days": _mean(ages), "count": len(ages)}


# --- inflow / outflow / the product-versus-factory ratio: the ideas folder's own frontmatter --------

def load_ideas_frontmatter(component_root) -> list[dict]:
    """Every ideas-folder seed under `component_root` (`rank.find_seeds`'s own walk — the one
    directory-discovery rule, never re-implemented), read for the fields `rank.load_seed` does not
    expose: `created`/`updated` (the vault's own stamping-plugin fields, preserved verbatim by
    `textutil.split_frontmatter`) and `crossed_to` (the task-delivered arm's own back-pointer,
    documentation-model.md's *The ideas-backlog*)."""
    out = []
    for path in rank.find_seeds(component_root):
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, _ = textutil.split_frontmatter(text)
        out.append({
            "path": str(path.relative_to(component_root)),
            "status": meta.get("status", ""),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
            "crossed_to": meta.get("crossed_to", ""),
        })
    return out


def inflow_outflow(seeds: list[dict], *, start: str, end: str) -> dict:
    """Inflow: seeds captured in the window (`created` falls in `[start, end)`). Outflow: seeds that
    LEFT `open` custody in the window (`status != "open"` and `updated` falls in `[start, end)`) —
    the documentation model's own "custody, not progress" rule: a status other than `open` is
    exactly what the backlog's own model calls departure, whatever it flipped to."""
    inflow = sum(1 for s in seeds if s.get("created") and start <= s["created"] < end)
    outflow = sum(1 for s in seeds
                  if s.get("status") and s["status"] != "open" and s.get("updated")
                  and start <= s["updated"] < end)
    return {"inflow": inflow, "outflow": outflow}


def product_factory_ratio(seeds: list[dict], *, parsed_strategy: dict | None = None,
                          factory_repo: str = FACTORY_REPO) -> dict:
    """Of every seed that has SHIPPED through the task-delivered arm (a non-empty `crossed_to:
    owner/repo#N`), how many delivered against this component's own product surface versus against
    the factory — cumulative to date (a delivered-seed sample is typically too thin to scope to one
    month alone). A seed with no `crossed_to` (still open, or superseded/rejected some other way)
    carries no delivery repo and is excluded.

    Classification (I5, #475 fold review round 1 — "theme from the strategy doc", the issue's own
    Context line): when `parsed_strategy` is given (this run's own read of the strategy doc),
    `strategy.matching_theme` — the declared public seam a theme's own `repos` line already states
    in-direction through — is the ONLY classifier: a repo some theme names is product, a repo NO
    theme names is factory, whatever it is called — no repo is exempted merely by not being spelled
    `factory_repo`. The literal `factory_repo` string comparison is the fallback ONLY when no parsed
    strategy is available at all (the doc unreadable or malformed this run) — the pre-#475-fold-
    review rule, kept for that one degraded case, never the primary rule."""
    product = 0
    factory = 0
    for s in seeds:
        crossed_to = (s.get("crossed_to") or "").strip()
        if not crossed_to:
            continue
        repo = crossed_to.split("#", 1)[0]
        if parsed_strategy is not None:
            if strategy.matching_theme(parsed_strategy, repo):
                product += 1
            else:
                factory += 1
        elif repo == factory_repo:
            factory += 1
        else:
            product += 1
    ratio = None
    if factory:
        ratio = round(product / factory, 2)
    elif product:
        ratio = float("inf")
    return {"product": product, "factory": factory, "ratio": ratio}


# --- deploy lag: the YR-DEPLOY trail (#464) ----------------------------------------------------------

def deploy_lag_hours(merge_dates: list[str], deploy_dates: list[str]) -> dict:
    """For each merge, the time until the next deploy timestamp at or after it (the first `YR-DEPLOY`
    record whose comment landed on/after the merge) — a merge with no later deploy yet is `pending`,
    never guessed at or dropped from the count."""
    sorted_deploys = sorted(deploy_dates)
    lags = []
    pending = 0
    for m in merge_dates:
        nxt = next((d for d in sorted_deploys if d >= m), None)
        if nxt is None:
            pending += 1
            continue
        lags.append(_hours_between(m, nxt))
    return {"mean_hours": _mean(lags), "count": len(lags), "pending": pending}


def deploy_records_timed(rows: list[tuple[str, str]]) -> list[str]:
    """`rows`: `(iso-timestamp, text)` pairs (`sources.issue_trail_timed`'s own shape, read over the
    deploy trail issue) -> the timestamp of every WELL-FORMED `YR-DEPLOY` record among them, in trail
    order. Well-formedness is judged through `tools/drift.py`'s own `parse_deploy_records` (I4, #475
    fold review round 1 — the shared authority `tools/round_record.py` also reads `YR-DEPLOY`
    through), one text at a time so each qualifying text keeps its own timestamp — never a second,
    looser marker-only match that would count a comment merely MENTIONING the marker without the
    complete surface/commit fields a real record carries."""
    out = []
    for ts, text in rows:
        if drift.parse_deploy_records([text]):
            out.append(ts)
    return out


# --- the combined report ----------------------------------------------------------------------------

def compute_report(inputs: dict, *, period: str, parsed_strategy: dict | None = None) -> dict:
    """`inputs`: every already-fetched surface this report reads (see `gather_report_inputs`'s own
    keys) -> the full metric report, one key per acceptance-criterion metric. `parsed_strategy`
    (I5, #475 fold review round 1) is this run's own read of the strategy doc, threaded through to
    `product_factory_ratio`'s own theme-membership classifier — `None` (the default) falls back to
    that function's own literal `factory_repo` comparison, unchanged from before this round."""
    start, end = month_bounds(period)
    return {
        "period": period,
        "velocity": velocity_per_week(inputs["merge_dates"], start=start, end=end),
        "cycle_time": cycle_time_hours(inputs["cycle_events"]),
        "blocked": blocked_rate(inputs["pr_trails"]),
        "repair": repair_rate(inputs["pr_usages"]),
        "revert": revert_rate(inputs["commit_subjects"]),
        "spend_usd": total_spend_usd(inputs["pr_usages"]),
        "backlog_age": backlog_age_days(inputs["board_rows"], now=inputs.get("now") or end),
        "inflow_outflow": inflow_outflow(inputs["ideas_seeds"], start=start, end=end),
        "product_factory_ratio": product_factory_ratio(inputs["ideas_seeds"], parsed_strategy=parsed_strategy),
        "deploy_lag": deploy_lag_hours(inputs["merge_dates"], inputs["deploy_dates"]),
    }


# The flat metric-name -> report-value lookup `kpi_targets` (a free-form dict, tools/strategy.py's own
# schema) is compared against, by matching key name alone — a target key with no like-named figure
# below is simply never shown a comparison, never an error (the doc's own vocabulary is free-form).
_TARGET_VIEW = {
    "velocity_per_week": lambda r: r["velocity"]["per_week"],
    "cycle_time_hours": lambda r: r["cycle_time"]["mean_total_hours"],
    "blocked_rate": lambda r: r["blocked"]["rate"],
    "repair_rate": lambda r: r["repair"]["rate"],
    "revert_rate": lambda r: r["revert"]["rate"],
    "spend_usd": lambda r: r["spend_usd"],
    "backlog_age_days": lambda r: r["backlog_age"]["mean_days"],
    "inflow": lambda r: r["inflow_outflow"]["inflow"],
    "outflow": lambda r: r["inflow_outflow"]["outflow"],
    "product_factory_ratio": lambda r: r["product_factory_ratio"]["ratio"],
    "deploy_lag_hours": lambda r: r["deploy_lag"]["mean_hours"],
}


def against_targets(report: dict, kpi_targets: dict) -> dict:
    """`{metric_name: {"actual": ..., "target": ...}}` for every metric this report computes that the
    strategy doc's own `kpi_targets` also names — never a judgment on "good"/"bad" (a target's own
    direction — higher-is-better or the reverse — is not stated anywhere in the schema, so this
    reports the pair, honestly, and leaves the reading to whoever reads the note)."""
    out = {}
    for name, getter in _TARGET_VIEW.items():
        if name in kpi_targets:
            out[name] = {"actual": getter(report), "target": kpi_targets[name]}
    return out


# --- rendering the note ------------------------------------------------------------------------------

def render_kpi_note(report: dict, *, targets: dict) -> str:
    """The note's own frontmatter (N3, #475 fold review round 1; corrected NEW-2, round 2):
    `type: note` + `status: active` ONLY — documentation-model.md:219's stamping rule: "Never
    hand-stamp `created`/`updated` — the vault's update-time plugin stamps both ... supply `created`
    only to backdate". Hand-stamping both on every regeneration would reset `created` every run
    (never backdating), use an ISO-Z format that is not the plugin's own, and race the plugin's own
    re-stamp (it fires within seconds of any parseable write) against `vault_api.write`'s read-back.
    `type`/`status` alone still give the plugin something well-formed to modify on the note's first
    write (AGENTS.md: it "writes nothing at all when the frontmatter cannot be parsed") — the plugin
    owns `created`/`updated` from there on, exactly as every other doc in this tree already gets
    them."""

    def line(label, actual, unit="", *, reason=None):
        t = targets.get(label)
        shown_unit = unit if actual is not None else ""
        target_str = f" (target: {t['target']}{unit})" if t else ""
        reason_str = f" — {reason}" if actual is None and reason else ""
        return f"- **{label}**: {actual}{shown_unit}{target_str}{reason_str}"

    v, c, b, rp, rv, ba, io, pf, dl = (
        report["velocity"], report["cycle_time"], report["blocked"], report["repair"],
        report["revert"], report["backlog_age"], report["inflow_outflow"],
        report["product_factory_ratio"], report["deploy_lag"],
    )
    frontmatter = "---\ntype: note\nstatus: active\n---\n"
    lines = [f"# KPI — {report['period']}", ""]
    # N1 (#475 fold review round 1): velocity narrows to runner-authored PRs (`--search "Produced by
    # dev-runner in:body"`, merged_runner_prs's own filter) — say so, never let a bare "merged" count
    # read as every merge this window.
    lines.append(line("velocity_per_week", v["per_week"], "/week") +
                f" ({v['merged']} runner PRs merged; attended PRs excluded)")
    lines.append(line("cycle_time_hours", c["mean_total_hours"], "h", reason=c.get("gap_reason")) +
                (f" (queue: {c['mean_queue_hours']}h)" if c["mean_queue_hours"] is not None else ""))
    lines.append(line("blocked_rate", b["rate"]) + f" ({b['blocked']}/{b['total']})")
    lines.append(line("repair_rate", rp["rate"]) + f" ({rp['repaired']}/{rp['total']})")
    revert_reason = "--code-root not declared this run — revert detection skipped (never a vault-mirror read)" \
        if rv["total"] is None else None
    lines.append(line("revert_rate", rv["rate"], reason=revert_reason) +
                (f" ({rv['reverts']}/{rv['total']})" if rv["total"] is not None else ""))
    lines.append(line("spend_usd", report["spend_usd"], " USD"))
    lines.append(line("backlog_age_days", ba["mean_days"], "d") + f" ({ba['count']} items)")
    lines.append(line("inflow", io["inflow"]))
    lines.append(line("outflow", io["outflow"]))
    lines.append(line("product_factory_ratio", pf["ratio"]) + f" (product={pf['product']} factory={pf['factory']})")
    lines.append(line("deploy_lag_hours", dl["mean_hours"], "h") + f" ({dl['pending']} pending)")
    lines.append("")
    return frontmatter + "\n".join(lines) + "\n"


def note_path(operations_home: str, period: str) -> str:
    return f"{operations_home.rstrip('/')}/kpi-{period}.md"


# --- records: YR-KPI (vault-doc + issue-trail), YR-STRATEGY (issue-trail, on the doc's own change) ---

def render_yr_kpi_line(*, who: str, period: str) -> str:
    return f"YR-KPI: who={who} period={period}\n"


def render_yr_strategy_line(*, who: str, doc: str) -> str:
    return f"YR-STRATEGY: who={who} doc={doc}\n"


def render_yr_strategy_comment(*, who: str, doc: str, doc_text: str) -> str:
    """The `YR-STRATEGY:` line plus a snapshot of the doc's own fenced ```yr-strategy block
    (`yr-strategy/1`, records.toml) — re-emitted VERBATIM from the doc's own fence, never a second,
    independent parse of it: a reader on the issue trail sees exactly what changed without opening
    the vault. Falls back to the line alone when the doc carries no well-formed block (a malformed
    doc still gets its change announced; `strategy.parse_strategy` is the loud detector for that,
    elsewhere)."""
    line = render_yr_strategy_line(who=who, doc=doc)
    try:
        _, body = textutil.split_frontmatter(doc_text)
        block = strategy.extract_block(body)
    except strategy.StrategyError:
        return line
    return f"{line}\n```yr-strategy{block}```\n"


def _field(line: str, key: str) -> str:
    m = re.search(rf"(?:^|\s){re.escape(key)}=(\S+)", line)
    return m.group(1) if m else ""


def kpi_already_posted(comment_bodies: list[str], period: str, reg=None) -> bool:
    """True iff some comment already carries a `YR-KPI` record naming THIS period — idempotence
    per month, the same "posted once" discipline every machinery record in this tree keeps
    (`YR-TRIAGE-PACK`/`YR-ESCALATION`/`YR-CLOSE-HOLD`'s own precedent); a re-run mid-month still
    regenerates the vault note (the report is meant to be current), it just does not re-comment."""
    reg = reg or records.load()
    marker = records.get(reg, "YR-KPI")["marker"]
    for body in comment_bodies:
        for l in body.splitlines():
            if textutil.marker_line_matches(l, marker, mode=textutil.MARKER_PREFIX) and _field(l, "period") == period:
                return True
    return False


def strategy_doc_changed(doc_text: str, state_path: pathlib.Path) -> tuple[bool, str]:
    """`(changed, digest)` — `changed` iff `doc_text`'s own sha256 differs from the last-observed
    digest stored at `state_path` (a local, per-repo state file under `DEV_RUNNER_HOME` —
    `tools/design_gate.py`'s own pidfile precedent, applied to a content digest instead of a PID).

    READ-ONLY (I6, #475 fold review round 1): never writes `state_path` itself — the old shape
    persisted the new digest as a side effect of this SAME call that decided `YR-STRATEGY` should
    post, so a transient `gh` failure on the comment that followed still left the digest updated,
    and the doc's own change was lost forever (the next run would see "unchanged", never re-try).
    The caller persists `digest` via `_persist_strategy_hash` ONLY once the comment has actually
    landed."""
    digest = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()
    prior = state_path.read_text().strip() if state_path.exists() else None
    return digest != prior, digest


def _persist_strategy_hash(state_path: pathlib.Path, digest: str) -> None:
    """The write half of `strategy_doc_changed` (I6) — called only after the `YR-STRATEGY` comment
    this digest justified has actually posted."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(digest)


_SLUG_RE = re.compile(r"[^a-z0-9-]")


def strategy_hash_path(repo: str) -> pathlib.Path:
    slug = _SLUG_RE.sub("-", (repo or "").lower())
    return pathlib.Path(DEV_RUNNER_HOME) / "pm" / f"strategy-hash-{slug}.txt"


# --- real I/O: gathering inputs (the only place a live surface is touched) ---------------------------

def _gh(argv, timeout=GH_TIMEOUT):
    proc = subprocess.run([os.environ.get("GH_BIN", "gh"), *argv], capture_output=True, text=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _as_json(out):
    return out if isinstance(out, (dict, list)) else json.loads(out or "null")


def merged_runner_prs(gh, repo, start, end, limit=200):
    """Merged runner PRs (`Produced by dev-runner in:body`, `tools/design_gate.py`'s own search
    convention) whose `mergedAt` falls in `[start, end)`."""
    out = _as_json(gh(["pr", "list", "--repo", repo, "--state", "merged",
                       "--search", "Produced by dev-runner in:body",
                       "--json", "number,mergedAt", "--limit", str(limit)]))
    return [p for p in (out or []) if isinstance(p, dict) and p.get("mergedAt")
           and start <= p["mergedAt"] < end]


def board_items(gh, org, project, repo, page_cap=100):
    """Every open board item belonging to `repo`, paged beyond `first: 100` — the same query shape
    `tools/board.sh`'s own `BOARD_QUERY` carries (createdAt included), read here directly rather
    than shelling out to the TSV script (whose printed columns do not carry createdAt at all). The
    repo filter matches the FULL `owner/name` (`tools/compile_slice.py`'s own board-filter
    precedent: a short-name compare matched nothing, ever)."""
    query = (
        "query($org: String!, $project: Int!, $cursor: String) {"
        "organization(login: $org) { projectV2(number: $project) {"
        "items(first: 100, after: $cursor) { nodes {"
        "content { ... on Issue { number title state createdAt "
        "issueType { name } repository { nameWithOwner } } }"
        'status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }'
        "} pageInfo { hasNextPage endCursor } } } } }"
    )
    nodes = []
    cursor = None
    for _ in range(page_cap):
        argv = ["api", "graphql", "-f", f"query={query}", "-F", f"org={org}", "-F", f"project={project}"]
        if cursor:
            argv += ["-F", f"cursor={cursor}"]
        data = _as_json(gh(argv))
        if "data" in data:
            data = data["data"]
        items = (((data.get("organization") or {}).get("projectV2") or {}).get("items")) or {}
        nodes += items.get("nodes") or []
        page = items.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    rows = []
    for it in nodes:
        c = it.get("content") or {}
        if not c or (c.get("state") or "").upper() != "OPEN":
            continue
        if ((c.get("repository") or {}).get("nameWithOwner") or "") != repo:
            continue
        rows.append({"number": c.get("number"), "repo": repo,
                    "createdAt": c.get("createdAt") or "", "status": ((it.get("status") or {}).get("name")) or ""})
    return rows


def gather_report_inputs(*, gh, repo, org, project, component_root, code_root=None, period=None, now=None):
    """The real reads assembled into `compute_report`'s own `inputs` shape (`gh`, `git`, and a local
    read of the vault-mirror checkout's own ideas folder — `tools/design_resolver.py`'s own
    precedent: a READ crosses the local mirror directly, never the REST client; only a WRITE does).
    Every failed read degrades to an empty list for that surface (a report with a hole in one
    metric, never a crash that loses every other metric) — the caller (`main`) is responsible for
    saying so.

    `component_root` is the vault-mirror checkout (`ideas/`) — never a source of `git log`. `code_root`
    (B2, #475 fold review round 1) is the SEPARATE, optional local checkout of the component's OWN
    code repo that revert detection actually reads; absent, `commit_subjects` is `None` (not `[]`) —
    the surface was never declared, fail-closed, never a silently-empty read someone could mistake
    for "zero reverts this month"."""
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    period = period or current_period()
    start, end = month_bounds(period)

    merge_dates, pr_trails, pr_usages, cycle_events = [], [], [], []
    try:
        prs = merged_runner_prs(gh, repo, start, end)
    except Exception:
        prs = []
    for pr in prs:
        merge_dates.append(pr["mergedAt"])
        try:
            # B1 (#475 fold review round 2): `closingIssuesReferences` rides the SAME call as
            # `body,comments` — but it is a NARROW projection (verified live against a real PR,
            # yellow-robots/factory#431: id/number/repository/url ONLY, no createdAt anywhere on
            # it). The issue NUMBER comes from here; `ready_at` stays None, documented at
            # `cycle_time_hours` itself (no per-field ProjectV2 status-change history without the
            # audit-log API).
            data = _as_json(gh(["pr", "view", str(pr["number"]), "--repo", repo,
                               "--json", "body,comments,closingIssuesReferences"]))
        except Exception:
            data = {}
        texts = sources.pr_trail_texts_from_json(data) if data else []
        pr_trails.append(texts)
        ok, usage = sources.pr_usage_from_texts(texts) if texts else (False, "")
        pr_usages.append(usage if ok else {"stages": [], "cost_usd": 0.0})

        # The linked issue's own `createdAt` is a SEPARATE read the pr-view projection can never
        # answer — the REST issue resource (`gh api repos/<owner>/<repo>/issues/<n>`, the mandate's
        # own `gh api` wording; REST's own snake_case `created_at`, never GraphQL's `createdAt`).
        # `link_status` distinguishes "this PR named no linked issue at all" from "it named one but
        # that read failed" — two different facts the note must never blur into one bare `None`.
        refs = (data or {}).get("closingIssuesReferences") or []
        created = None
        link_status = "no_linked_issue"
        if refs and isinstance(refs[0], dict) and refs[0].get("number"):
            link_status = "read_failed"
            try:
                issue_data = _as_json(gh(["api", f"repos/{repo}/issues/{refs[0]['number']}"]))
                created = (issue_data or {}).get("created_at")
                if created:
                    link_status = "linked"
            except Exception:
                pass
        cycle_events.append({"created": created, "ready_at": None, "merged": pr["mergedAt"],
                             "link_status": link_status})

    if code_root:
        try:
            log = subprocess.run(["git", "-C", code_root, "log", f"--since={start}", f"--until={end}",
                                 "--format=%s"], capture_output=True, text=True, timeout=GH_TIMEOUT)
            commit_subjects = log.stdout.splitlines() if log.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired):
            commit_subjects = []
    else:
        commit_subjects = None

    try:
        board_rows = board_items(gh, org, project, repo)
    except Exception:
        board_rows = []

    try:
        ideas_seeds = load_ideas_frontmatter(pathlib.Path(component_root))
    except OSError:
        ideas_seeds = []

    try:
        ok, rows = sources.issue_trail_timed(DEPLOY_TRAIL_REPO, DEPLOY_TRAIL_ISSUE)
        deploy_dates = deploy_records_timed(rows) if ok else []
    except Exception:
        deploy_dates = []

    return {
        "now": now, "merge_dates": merge_dates, "pr_trails": pr_trails, "pr_usages": pr_usages,
        "cycle_events": cycle_events, "commit_subjects": commit_subjects, "board_rows": board_rows,
        "ideas_seeds": ideas_seeds, "deploy_dates": deploy_dates,
    }


def _comment(gh, repo, issue, body):
    gh(["issue", "comment", str(issue), "--repo", repo, "--body", body])


def run_report(*, gh, vault, repo, issue, org, project, component_root, code_root=None, strategy_doc,
               operations_home, who, period=None):
    """The whole act: gather, compute, write the note, post `YR-KPI` (idempotent per period, fail-
    CLOSED when the idempotence check itself can't be verified — N5 below), and — when the strategy
    doc's own hash moved since the last run — post `YR-STRATEGY` too. Returns a small report of what
    happened; never raises past `VaultUnreachable` from the note write itself (I6, #475 fold review
    round 1 — a `gh` `RuntimeError` from either comment post is caught here and turned into a stated
    `*_post_failed` result field, never an uncaught crash past this function)."""
    period = period or current_period()
    inputs = gather_report_inputs(gh=gh, repo=repo, org=org, project=project,
                                  component_root=component_root, code_root=code_root, period=period)

    # I5 (#475 fold review round 1): the strategy doc is read and parsed BEFORE compute_report, so
    # product_factory_ratio can classify by theme membership rather than the bare factory_repo
    # literal.
    ok, doc_text = sources.vault_doc(pathlib.Path(strategy_doc))
    parsed_strategy = None
    kpi_targets = {}
    strategy_changed = False
    strategy_digest = None
    if ok:
        try:
            parsed_strategy = strategy.parse_strategy(doc_text)
            kpi_targets = parsed_strategy.get("kpi_targets") or {}
        except strategy.StrategyError:
            parsed_strategy = None
            kpi_targets = {}
        strategy_changed, strategy_digest = strategy_doc_changed(doc_text, strategy_hash_path(repo))

    report = compute_report(inputs, period=period, parsed_strategy=parsed_strategy)
    targets = against_targets(report, kpi_targets)
    note = render_kpi_note(report, targets=targets)
    kpi_line = render_yr_kpi_line(who=who, period=period)
    vault.write(note_path(operations_home, period), note + "\n" + kpi_line)

    result = {"period": period, "wrote_note": True, "posted_kpi": False, "posted_strategy": False,
             "kpi_post_failed": False, "strategy_post_failed": False}

    # N5 (#475 fold review round 1): an unreadable trail used to fail OPEN (`already = False`),
    # risking a DUPLICATE YR-KPI post whenever the trail happened to already carry one — fail
    # CLOSED instead: refuse to post at all when idempotence can't be verified, naming why.
    ok_trail, texts = sources.issue_trail(repo, str(issue))
    if not ok_trail:
        result["kpi_post_failed"] = True
        print(f"kpi.py: {repo}#{issue}'s own trail is unreadable ({texts}) — refusing to post "
              "YR-KPI (cannot verify idempotence this run)", file=sys.stderr)
    else:
        already = kpi_already_posted(texts, period)
        if not already:
            try:
                _comment(gh, repo, issue, kpi_line)
                result["posted_kpi"] = True
            except RuntimeError as e:
                result["kpi_post_failed"] = True
                print(f"kpi.py: failed to post YR-KPI for {period}: {e}", file=sys.stderr)

    if strategy_changed:
        try:
            _comment(gh, repo, issue,
                    render_yr_strategy_comment(who=who, doc=strategy_doc, doc_text=doc_text))
            result["posted_strategy"] = True
            # I6: the digest persists ONLY once the comment it justifies has actually landed — a
            # failed post below leaves the prior digest in place, so the NEXT run still sees "changed".
            _persist_strategy_hash(strategy_hash_path(repo), strategy_digest)
        except RuntimeError as e:
            result["strategy_post_failed"] = True
            print(f"kpi.py: failed to post YR-STRATEGY for {strategy_doc}: {e}", file=sys.stderr)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="the KPI report on demand (it-36 slice J, #475)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_r = sub.add_parser("report", help="compute this month's KPI note, write it, post the records")
    p_r.add_argument("--repo", required=True, help="owner/name — the component's own repo")
    p_r.add_argument("--issue", required=True, help="the issue whose trail carries YR-KPI/YR-STRATEGY")
    p_r.add_argument("--org", default=os.environ.get("YR_ORG", "yellow-robots"))
    p_r.add_argument("--project", required=True, help="the board's project number")
    p_r.add_argument("--component-root", required=True, help="the vault-mirror component root (ideas/)")
    p_r.add_argument("--code-root", default=None,
                     help="local checkout of the component's OWN code repo (git log revert "
                          "detection) — SEPARATE from --component-root, the vault mirror; absent, "
                          "revert detection is skipped, fail-closed, never derived from the manifest "
                          "or $YR_WORKSPACE (B2, #475 fold review round 1)")
    p_r.add_argument("--strategy-doc", required=True, help="local path to the strategy note")
    p_r.add_argument("--operations-home", required=True, help="vault-relative operations home path")
    p_r.add_argument("--who", default=os.environ.get("YR_GH_APP_SLUG", "machinery"))
    p_r.add_argument("--period", default=None, help='"YYYY-MM", default: the current month')
    p_r.add_argument("--test-mode", action="store_true", help="print the note; write and post nothing")
    args = ap.parse_args(argv)

    if args.cmd != "report":
        ap.print_usage(sys.stderr)
        return 2

    if args.test_mode:
        period = args.period or current_period()
        inputs = gather_report_inputs(gh=_gh, repo=args.repo, org=args.org,
                                      project=args.project, component_root=args.component_root,
                                      code_root=args.code_root, period=period)
        ok, doc_text = sources.vault_doc(pathlib.Path(args.strategy_doc))
        parsed_strategy = None
        kpi_targets = {}
        if ok:
            try:
                parsed_strategy = strategy.parse_strategy(doc_text)
                kpi_targets = parsed_strategy.get("kpi_targets") or {}
            except strategy.StrategyError:
                parsed_strategy = None
                kpi_targets = {}
        report = compute_report(inputs, period=period, parsed_strategy=parsed_strategy)
        note = render_kpi_note(report, targets=against_targets(report, kpi_targets))
        print("TEST-MODE: no vault write, no comment posted — the plan only")
        print(note)
        return 0

    vault = vault_api.VaultClient()
    result = run_report(gh=_gh, vault=vault, repo=args.repo, issue=args.issue, org=args.org,
                        project=args.project, component_root=args.component_root,
                        code_root=args.code_root, strategy_doc=args.strategy_doc,
                        operations_home=args.operations_home, who=args.who, period=args.period)
    print(json.dumps(result))
    # NEW-6 (#475 fold review round 2): a stated failure exits as one — `run_report` already turns
    # a failed comment post into `kpi_post_failed`/`strategy_post_failed` rather than raising, but a
    # bare `return 0` here would still tell the caller (a shell, a cron wrapper) that the run
    # succeeded.
    return 1 if (result.get("kpi_post_failed") or result.get("strategy_post_failed")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
