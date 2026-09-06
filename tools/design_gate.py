#!/usr/bin/env python3
"""design_gate.py — the design sweep (it-36 slice E, #470).

`sweep_designs(*, gh=None, repos, ...)` is the reusable, pure core — `epic_gate.sweep_epics`'s own
shape: the one external, the `gh` CLI, is injected as a callable `gh(argv) -> stdout` (parsed JSON *or*
text; tolerant either way, like `epic_gate._query`). The default runs `$GH_BIN` (falling back to `gh`);
tests pass a `FakeGh` that serves canned issue/PR JSON and records writes — no live network, no live
vault. `repos` is explicit input (never filesystem/vault-discovered inside the pure core, the same
discipline `sweep_epics(repos=...)` uses): each entry names a repository's triage issue and carries its
ALREADY-READ seeds (`tools/rank.py`) and strategy (`tools/strategy.py`) — `main()` does those real
vault reads; a test supplies canned ones directly, so "the vault interface does not answer" is just
another `ok=False` entry, no filesystem needed to exercise it.

Per repository, one pass:
  1. seeds/strategy unreadable -> idle, loudly, on the triage issue ("vault interface down").
  2. no strategy theme targets this repo -> idle ("no theme" — nothing can ever be in-direction).
  3. the strategy's `loop_budget_usd_per_week` is exhausted (this repo's `kind=design` ledger spend
     over the trailing week) -> a `YR-ESCALATION` record, then idle (posted once, never repeated).
  4. read the triage trail (`tools/sources.py:triage_surface`'s own shape): a `YR-TRIAGE` record from
     anyone but `YR_OWNER_LOGIN` is ignored outright; the LAST record per seed (trail order) wins.
  5. every UNDECIDED ranked seed (no record yet) gets one `YR-TRIAGE-PACK` comment, posted once, never
     re-posted — scope/value/cost/theme plus a paste-ready `YR-TRIAGE:` sample line, INDENTED so it can
     never satisfy the sweep's own column-0 reader on a later pass (the self-triggering-record lesson,
     `epic_gate.py`'s own).
  6. a `park`/`reject` disposition on a seed that has an in-flight design stops it: the sweep kills the
     stage group, notes it on the triage issue, and the seed leaves the queue — no resume without a
     fresh `go`. The same license withdrawal fires when a named governing epic is un-Readied or closed.
  7. the top-ranked licensed (`go`, in-direction) seed with no design already in flight for this repo
     gets the runner's `product` stage spawned (`tools/design-runner.sh`) — one design in flight per
     repository, this round's own rule (distinct from the epic gate's one-slice-per-epic).
  8. no licensed candidate at all -> idle, loudly, naming that too.

`main()` supplies the real repo list from an operator-maintained config (item P's own human
provisioning: which repos, which triage issue, which vault paths) and the real vault reads.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time

# sibling-module imports (never `tools.`-prefixed): this runs as a bare script, `tools/` at
# sys.path[0] — the same discipline `tools/epic_gate.py` / `tools/design_resolver.py` document.
import board_plumbing
import check_trail
import ledger
import rank
import records
import sources
import strategy
import textutil
import vault_api

# --- record grammar (records.toml, it-36 slice D, #469 — minted there; read here) ----------------------
TRIAGE_MARKER = "YR-TRIAGE:"
PACK_MARKER = "YR-TRIAGE-PACK"
ESCALATION_MARKER = "YR-ESCALATION:"

# S/M/L effort factor (the Base's own vocabulary, tools/rank.py); an unrecognized effort falls to the
# L factor — the same discount rank.py's own `compute_rank` gives an unrecognized effort.
EFFORT_FACTOR = {"S": 1, "M": 3, "L": 6}

DEV_RUNNER_HOME = os.environ.get("DEV_RUNNER_HOME", str(pathlib.Path.home() / ".cache" / "dev-runner"))
DESIGN_RUNNER = os.environ.get("DESIGN_RUNNER", str(pathlib.Path(__file__).resolve().parent / "design-runner.sh"))
# the local vault-mirror root design_resolver.py already reads through (its own YR_VAULT_ROOT
# default) — every machinery READ crosses it directly; every WRITE crosses through vault_api.py's
# REST client instead, addressed relative to this same root (Editing safely: never a filesystem
# mutation).
VAULT_ROOT = os.environ.get("YR_VAULT_ROOT", "/srv/obsidian/vaults/obsidian")


# --- default `gh` runner (the only real external; injected/overridden in tests) -----------------------
def _gh(argv):
    """Run `$GH_BIN <argv...>` (default `gh`) — the acceptance criterion's own routing: every `gh` call
    in the runner, the gate, the sources and the PM goes through `GH_BIN`, so pointing it at the App
    token wrapper (`tools/gh-app`) is the whole switch. Raises on a non-zero exit."""
    proc = subprocess.run([os.environ.get("GH_BIN", "gh"), *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _as_json(out):
    """Tolerate a callable that returns either parsed JSON or a JSON string — `epic_gate._query`'s own
    tolerance, so a FakeGh can serve canned dicts/lists directly."""
    return out if isinstance(out, (dict, list)) else json.loads(out or "null")


def _comment(gh, repo, issue, body):
    gh(["issue", "comment", str(issue), "--repo", repo, "--body", body])


# --- the triage trail: last-record-per-seed, owner-only ------------------------------------------------
def _extract_kv(line, key):
    """One `key=value` token off a space-separated record line (the `YR-TRIAGE`/`YR-ESCALATION` one-
    line grammar) — the value runs to the next whitespace. `""` when the key is absent."""
    m = re.search(rf"(?:^|\s){re.escape(key)}=(\S+)", line)
    return m.group(1) if m else ""


def latest_triage_dispositions(trail, owner_login):
    """`trail`: `(author_login, body)` pairs in chronological order (`sources.triage_surface`'s own
    shape). A record from anyone but `owner_login` is ignored outright (the human-only grammar,
    records.toml) — the last `YR-TRIAGE:` record PER SEED, scanning forward, wins."""
    dispositions = {}
    for author, body in trail:
        if author != owner_login:
            continue
        for line in body.splitlines():
            if not textutil.marker_line_matches(line, TRIAGE_MARKER, mode="prefix"):
                continue
            seed = _extract_kv(line, "seed")
            disposition = _extract_kv(line, "disposition")
            if seed and disposition:
                dispositions[seed] = disposition
    return dispositions


def _pack_already_posted(comment_bodies, seed_stem):
    """True iff some comment already carries the `YR-TRIAGE-PACK` sentinel AND names this seed (its
    `seed:` field, indented right under the marker — the `commit:`-under-marker convention
    `epic_gate.py`'s own provenance rows use) — the pack's own idempotence key: posted once, per seed,
    never re-posted."""
    for body in comment_bodies:
        lines = body.splitlines()
        if not any(textutil.marker_line_matches(ln, PACK_MARKER, mode="sentinel") for ln in lines):
            continue
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("seed:") and stripped[len("seed:"):].strip() == seed_stem:
                return True
    return False


def _has_escalation_posted(comment_bodies, repo):
    """True iff a loop-budget `YR-ESCALATION` was already raised for this repo — posted once, never
    repeated (a human clearing the hold and re-triaging is out of this sweep's scope)."""
    return any(
        any(textutil.marker_line_matches(ln, ESCALATION_MARKER, mode="prefix")
            and "why=loop-budget-exhausted" in ln for ln in body.splitlines())
        for body in comment_bodies
    )


# --- theme matching (tools/strategy.py) -----------------------------------------------------------------
def _matching_theme(parsed_strategy, repo):
    """The first theme (declared order) whose `repos` names this repository, or None — "in-direction"
    for this slice's purposes is exactly "some theme targets this repo at all"."""
    for theme in parsed_strategy.get("themes") or []:
        if repo in (theme.get("repos") or []):
            return theme
    return None


# --- cost estimate: the mean of the repo's recent runner-PR usage, x the seed's own effort factor -------
def _repo_recent_runner_prs(gh, repo, limit):
    try:
        out = gh(["pr", "list", "--repo", repo, "--state", "merged",
                  "--search", "Produced by dev-runner in:body", "--json", "number",
                  "--limit", str(limit)])
        data = _as_json(out)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [p["number"] for p in data if isinstance(p, dict) and p.get("number")]


def seed_cost_usd(gh, repo, effort, limit=5):
    """Mean `cost_usd` (`sources.pr_usage`'s own figure) over the repo's last `limit` merged runner
    PRs, times the seed's own S/M/L effort factor. None when no priced PR is found — the pack still
    posts, naming the cost as unknown rather than refusing to post."""
    costs = []
    for number in _repo_recent_runner_prs(gh, repo, limit):
        try:
            data = _as_json(gh(["pr", "view", str(number), "--repo", repo, "--json", "body,comments"]))
        except Exception:
            continue
        texts = sources.pr_trail_texts_from_json(data)
        ok, usage = sources.pr_usage_from_texts(texts)
        if ok:
            costs.append(usage["cost_usd"])
    if not costs:
        return None
    mean = sum(costs) / len(costs)
    factor = EFFORT_FACTOR.get(effort, EFFORT_FACTOR["L"])
    return round(mean * factor, 2)


# --- rendering the pack comment -------------------------------------------------------------------------
def _render_pack_body(seed, stem, cost_usd, theme_id, owner_login):
    cost_str = f"${cost_usd:.2f}" if cost_usd is not None else "unknown (no priced merged PR yet)"
    sample = f"YR-TRIAGE: seed={stem} disposition=go who=@{owner_login}"
    return (
        f"{PACK_MARKER}\n"
        f"  seed: {stem}\n\n"
        f"**scope:** {seed.get('summary') or '(no summary)'}\n"
        f"**value:** {seed.get('value') or ''}  **effort:** {seed.get('effort') or ''}  "
        f"**rank:** {seed.get('rank')}\n"
        f"**cost estimate:** {cost_str} (mean of this repo's last merged runner PRs' usage, x the "
        "seed's own effort factor: S=1, M=3, L=6)\n"
        f"**theme:** {theme_id}\n\n"
        "To triage, reply on this issue with (paste exactly, editing the disposition to `go`, `park`, "
        "or `reject`):\n\n"
        f"    {sample}\n"
    )


# --- the governing-epic license (optional per repo entry): un-Readied or closed withdraws it ------------
_EPIC_STATUS_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){"
    "issue(number:$number){state projectItems(first:20){nodes{project{number} "
    'status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}'
    "}}}}}"
)


def _epic_license_active(gh, repo, epic_issue):
    """True iff the named governing epic is OPEN with board Status exactly `Ready` — the design's own
    license. Any read failure degrades to False: an unreadable epic can never keep a design licensed."""
    owner, _, name = repo.partition("/")
    try:
        obj = _as_json(gh(["api", "graphql", "-f", "query=" + _EPIC_STATUS_QUERY,
                          "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={epic_issue}"]))
        if isinstance(obj, dict) and "data" in obj:
            obj = obj["data"]
        node = ((obj.get("repository") or {}).get("issue")) or {}
    except Exception:
        return False
    if (node.get("state") or "").upper() != "OPEN":
        return False
    items = ((node.get("projectItems") or {}).get("nodes")) or []
    wanted = board_plumbing.project_number()
    matched = next((i for i in items if ((i.get("project") or {}).get("number")) == wanted), None)
    return (((matched or {}).get("status") or {}).get("name") or "") == "Ready"


# --- design-in-flight tracking + the spawn/kill seams (all injectable; the real ones are pidfile-based,
#     one design per repository — this sweep's own rule) ------------------------------------------------
_SLUG_RE = re.compile(r"[^a-z0-9-]")


def _slug(repo):
    return _SLUG_RE.sub("-", (repo or "").lower())


def _pidfile(repo):
    d = pathlib.Path(DEV_RUNNER_HOME) / "pm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"design-{_slug(repo)}.pid"


def _default_design_active(repo, seed):
    path = _pidfile(repo)
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        return False
    return True


def _default_spawn_stage(repo, seed):
    """Detached spawn of `tools/design-runner.sh <repo> <seed>` — its pid (the whole tree's own pgid;
    `start_new_session=True` is the Python-side `setsid`) is cached in the per-repo pidfile so a later
    sweep tick can tell a design is in flight, and so a reversal's kill has something to signal."""
    log_dir = pathlib.Path(DEV_RUNNER_HOME) / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"design-{_slug(repo)}-{int(time.time() * 1000)}.log"
    with open(log_path, "ab") as log_f:
        proc = subprocess.Popen([DESIGN_RUNNER, repo, seed], stdin=subprocess.DEVNULL,
                                stdout=log_f, stderr=subprocess.STDOUT, start_new_session=True)
    _pidfile(repo).write_text(str(proc.pid))


def _default_kill_stage_group(repo):
    """Best-effort: SIGTERM the pidfile's process GROUP, then drop the pidfile so the repo reads as
    free again. A `claude -p` stage that has already `setsid`'d into its OWN group (`stage_lib.sh`'s own
    per-stage isolation, issue #121) can outlive this — a known, documented residual: nothing downstream
    ever consumes that stage's output once the pidfile is gone, so an orphaned stage costs at most one
    wasted run, never a vault write or a PR."""
    path = _pidfile(repo)
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        path.unlink()
    except OSError:
        pass


_ONE_WEEK = datetime.timedelta(days=7)


def _default_ledger_spent_usd(repo, now_dt):
    """This repo's trailing-week `kind=design` ledger spend — the strategy doc's own
    `loop_budget_usd_per_week` measured against `tools/ledger.py`'s own cost read (never a second cost
    formula)."""
    rows = ledger.load_rows(str(pathlib.Path(DEV_RUNNER_HOME) / "ledger"))
    since = (now_dt - _ONE_WEEK).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [r for r in ledger.filter_rows(rows, repo=repo, since=since) if r.get("kind") == "design"]
    return ledger.close_time_cost(rows)["total_shadow_cost_usd"]


def _utcnow():
    return datetime.datetime.utcnow()


# --- the pure core ---------------------------------------------------------------------------------------
def _idle(gh, repo, issue, why):
    _comment(gh, repo, issue, f"YR-PM: idling on **{repo}** — {why}. No factory work is substituted.")


def _post_escalation(gh, repo, issue, spent, budget):
    body = (
        f"{ESCALATION_MARKER} act=idle why=loop-budget-exhausted\n"
        f"  spent: ${spent:.2f}\n"
        f"  budget: ${budget:.2f}/week\n\n"
        f"The design sweep's weekly loop budget (the strategy doc's `loop_budget_usd_per_week`) is "
        f"exhausted for **{repo}** — idling until the window resets. No factory work is substituted."
    )
    _comment(gh, repo, issue, body)


def _process_repo(gh, entry, now, owner_login, ledger_spent_usd, pr_scan_limit,
                   design_active, spawn_stage, kill_stage_group):
    repo = entry["repo"]
    triage_issue = entry["triage_issue"]
    epic_issue = entry.get("epic_issue")
    actions = []

    seeds_res = entry.get("seeds") or {}
    strategy_res = entry.get("strategy") or {}
    if not seeds_res.get("ok") or not strategy_res.get("ok"):
        reason = seeds_res.get("error") or strategy_res.get("error") or "unreachable"
        _idle(gh, repo, triage_issue, f"the vault interface did not answer ({reason})")
        actions.append({"repo": repo, "action": "idle", "reason": "vault-down"})
        return actions
    parsed_strategy = strategy_res["value"]
    seeds = seeds_res["value"]

    theme = _matching_theme(parsed_strategy, repo)
    if theme is None:
        _idle(gh, repo, triage_issue, "no strategy theme targets this repository")
        actions.append({"repo": repo, "action": "idle", "reason": "no-theme"})
        return actions

    try:
        ok_trail, trail_or_err = _fetch_triage_trail(gh, repo, triage_issue)
    except Exception as e:
        ok_trail, trail_or_err = False, str(e)
    if not ok_trail:
        _idle(gh, repo, triage_issue, f"the triage trail did not answer ({trail_or_err})")
        actions.append({"repo": repo, "action": "idle", "reason": "trail-unreadable"})
        return actions
    trail = trail_or_err
    comment_bodies = [body for _, body in trail]

    budget = parsed_strategy.get("loop_budget_usd_per_week")
    spent = ledger_spent_usd(repo, now())
    if isinstance(budget, (int, float)) and spent >= budget:
        if not _has_escalation_posted(comment_bodies, repo):
            _post_escalation(gh, repo, triage_issue, spent, budget)
        actions.append({"repo": repo, "action": "idle", "reason": "loop-budget"})
        return actions

    dispositions = latest_triage_dispositions(trail, owner_login)
    epic_ok = _epic_license_active(gh, repo, epic_issue) if epic_issue else True

    go_candidate = None
    for seed in seeds:
        stem = pathlib.Path(seed["path"]).stem
        disposition = dispositions.get(stem)
        if disposition is None:
            if not _pack_already_posted(comment_bodies, stem):
                cost = seed_cost_usd(gh, repo, seed.get("effort"), pr_scan_limit)
                body = _render_pack_body(seed, stem, cost, theme.get("id"), owner_login)
                _comment(gh, repo, triage_issue, body)
                actions.append({"repo": repo, "action": "pack-posted", "seed": stem})
            continue
        if disposition == "go":
            if go_candidate is None and epic_ok:
                go_candidate = stem
        elif disposition in ("park", "reject"):
            if design_active(repo, stem):
                kill_stage_group(repo)
                _comment(gh, repo, triage_issue,
                         f"YR-PM: design for seed `{stem}` stopped — disposition reversed to "
                         f"`{disposition}`. A new `go` record is required to resume.")
                actions.append({"repo": repo, "action": "reversed", "seed": stem})

    if epic_issue and not epic_ok and design_active(repo, None):
        kill_stage_group(repo)
        _comment(gh, repo, triage_issue,
                 f"YR-PM: design for **{repo}** stopped — the governing epic #{epic_issue} was "
                 "un-Readied or closed. A new `go` record is required to resume.")
        actions.append({"repo": repo, "action": "withdrawn"})
        return actions

    if go_candidate is None:
        _idle(gh, repo, triage_issue, "the ranked backlog holds no in-direction, licensed `go` candidate")
        actions.append({"repo": repo, "action": "idle", "reason": "no-candidate"})
        return actions

    if design_active(repo, go_candidate):
        actions.append({"repo": repo, "action": "in-flight", "seed": go_candidate})
        return actions

    spawn_stage(repo, go_candidate)
    actions.append({"repo": repo, "action": "spawned", "seed": go_candidate})
    return actions


def _fetch_triage_trail(gh, repo, issue):
    data = _as_json(gh(["issue", "view", str(issue), "--repo", repo, "--json", "body,comments"]))
    return True, sources.triage_rows_from_json(data)


def sweep_designs(*, gh=None, repos, now=None, owner_login=None, ledger_spent_usd=None,
                   pr_scan_limit=5, design_active=None, spawn_stage=None, kill_stage_group=None):
    """One sweep pass over `repos` (see the module docstring for the per-repository algorithm). Every
    external is injectable so this is unit-testable with a `FakeGh` and no live vault/ledger/process
    control."""
    gh = gh or _gh
    now = now or _utcnow
    owner_login = owner_login if owner_login is not None else os.environ.get("YR_OWNER_LOGIN", "")
    ledger_spent_usd = ledger_spent_usd or _default_ledger_spent_usd
    design_active = design_active or _default_design_active
    spawn_stage = spawn_stage or _default_spawn_stage
    kill_stage_group = kill_stage_group or _default_kill_stage_group

    actions = []
    for entry in repos:
        actions.extend(_process_repo(gh, entry, now, owner_login, ledger_spent_usd, pr_scan_limit,
                                     design_active, spawn_stage, kill_stage_group))
    return actions


# --- the close sweep: spawns tools/close-runner.sh when an epic carries YR-CLOSE-HOLD (it-36 slice
#     H, #473) — a SEPARATE concern from the triage/design sweep above (epics, not repo+seed pairs;
#     sharing only the pidfile-tracked spawn SHAPE, `_default_spawn_stage`'s own precedent). The
#     close arm itself (`tools/epic_gate.py` `:972-1004`) is UNCHANGED: this sweep only makes what
#     it demands appear, on the epic's own trail, before the next epic-gate tick looks again — it
#     never comments, never touches Status/Reason, never closes anything itself. ---------------------
CLOSE_HOLD_MARKER = "YR-CLOSE-HOLD"
CLOSE_RUNNER = os.environ.get("CLOSE_RUNNER", str(pathlib.Path(__file__).resolve().parent / "close-runner.sh"))


def _close_pidfile(repo, epic_number):
    d = pathlib.Path(DEV_RUNNER_HOME) / "pm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"close-{_slug(repo)}-{epic_number}.pid"


def _default_close_active(repo, epic_number):
    path = _close_pidfile(repo, epic_number)
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        return False
    return True


def _default_spawn_close(repo, epic_number, component_root="", strategy_doc=""):
    """Detached spawn of `tools/close-runner.sh <repo> <epic_number> [<component_root>
    [<strategy_doc>]]` — mirrors `_default_spawn_stage`'s own pidfile-tracked,
    `start_new_session=True` shape, keyed by `(repo, epic_number)` rather than `(repo, seed)`: more
    than one epic in the SAME repo can finish and hold in the same window, each earning its own
    close stage, independent of any design draft in flight for that repo. `component_root`/
    `strategy_doc` ride on ARGV (B3's own fix, #472 fold review): the pm-repos.json config entry
    already declares both per repo (`_resolve_entry` reads them, the SAME fields `rank.ranked_seeds`/
    `strategy.parse_strategy` already consume) — an env-var seam would be (a) one value shared
    across every swept repo when each entry declares its own, and (b) stripped by dispatch's own
    spawn-env allowlist under the PM instance, silently starving every close stage of both paths
    forever. Positional and OPTIONAL (an absent component_root/strategy_doc still spawns — the
    runner itself decides what it can and cannot do without them, loudly)."""
    log_dir = pathlib.Path(DEV_RUNNER_HOME) / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"close-{_slug(repo)}-{epic_number}-{int(time.time() * 1000)}.log"
    argv = [CLOSE_RUNNER, repo, str(epic_number), component_root or "", strategy_doc or ""]
    with open(log_path, "ab") as log_f:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                stdout=log_f, stderr=subprocess.STDOUT, start_new_session=True)
    _close_pidfile(repo, epic_number).write_text(str(proc.pid))


def _carries_close_hold(texts):
    return any(
        any(textutil.marker_line_matches(l, CLOSE_HOLD_MARKER, mode=textutil.MARKER_SENTINEL)
            for l in text.splitlines())
        for text in texts
    )


def _already_shipped(reg, texts):
    """True once the close lane's own mandates (`YR-ROUND-RECORD`, `YR-SHIP-WALK`) already sit on
    the epic's trail — the SAME detector the close arm itself runs
    (`tools/check_trail.py check_texts`), so this sweep never re-spawns a close stage for an epic
    whose records already landed and is simply waiting for the next epic-gate tick to self-close
    it."""
    return not check_trail.check_texts(reg, "close", {"issue-trail": texts})


def sweep_close(*, gh=None, epics, close_active=None, spawn_close=None):
    """One pass over `epics` (`[{"repo": .., "number": .., "component_root": .., "strategy_doc": ..},
    ...]` — explicit input, never board-discovered inside this pure core, mirroring
    `sweep_designs(repos=...)`'s own rule; `main()` supplies the real, discovered list, threading
    each repo's OWN `component_root`/`strategy_doc` from the SAME pm-repos.json config entry
    `_resolve_entry` already reads — B3's own fix, #472 fold review). For each: fetch its trail
    (issue body + comments — the SAME `body,comments` shape `sources.pr_trail_texts_from_json`
    already parses, issue and PR alike); if it carries `YR-CLOSE-HOLD` and its own mandated close
    records are not already on the trail, spawn the close stage (with that repo's own
    `component_root`/`strategy_doc` on argv) UNLESS one is already in flight for this exact epic.
    Every external is injectable so this is unit-testable with a `FakeGh` and no live network, no
    live pidfiles, no real subprocess spawn."""
    gh = gh or _gh
    close_active = close_active or _default_close_active
    spawn_close = spawn_close or _default_spawn_close
    reg = records.load()
    actions = []
    for entry in epics:
        repo, number = entry["repo"], entry["number"]
        data = _as_json(gh(["issue", "view", str(number), "--repo", repo, "--json", "body,comments"]))
        texts = sources.pr_trail_texts_from_json(data)
        if not _carries_close_hold(texts):
            actions.append({"repo": repo, "number": number, "action": "no-hold"})
            continue
        if _already_shipped(reg, texts):
            actions.append({"repo": repo, "number": number, "action": "already-shipped"})
            continue
        if close_active(repo, number):
            actions.append({"repo": repo, "number": number, "action": "in-flight"})
            continue
        spawn_close(repo, number, entry.get("component_root", ""), entry.get("strategy_doc", ""))
        actions.append({"repo": repo, "number": number, "action": "spawned"})
    return actions


def _default_discover_close_hold(gh, repo):
    """`main()`'s own real discovery (never the tested core above): a full-text search over `repo`'s
    OPEN issues carrying the `YR-CLOSE-HOLD` sentinel anywhere on their trail — the SAME set
    `tools/epic_gate.py`'s own sweep already comments on (a held epic stays `Status=Ready`,
    `Reason=Needs-info`; searching by content means this module never has to duplicate the board's
    own field-reading plumbing to find it). Returns bare `{"repo", "number"}` dicts — `main()` is the
    one that attaches `component_root`/`strategy_doc` from the config entry, since a search result
    carries no config of its own."""
    out = gh(["search", "issues", "--repo", repo, "YR-CLOSE-HOLD", "--state", "open", "--json", "number"])
    data = _as_json(out)
    return [{"repo": repo, "number": item["number"]} for item in (data or []) if isinstance(item, dict)]


# --- the triage-license evaluator (it-36 slice D declared the guard; the tool owns the trail-walk
#     that decides it) --------------------------------------------------------------------------------
def _load_pm_config(config_path):
    """The raw repo-config entries (`repo`/`triage_issue`/`epic_issue`), tolerant of a missing or
    unreadable file — an evaluator that cannot read its own config fails closed (a fail token), never
    with a traceback."""
    try:
        return json.loads(pathlib.Path(config_path).read_text()).get("repos") or []
    except (OSError, ValueError):
        return []


def update_pm_config_entry(config_path, *, repo, epic_issue=None, seed=None):
    """The crossing's own write-back (it-36 slice G, #472): `tools/cross.py` calls this right after
    filing an epic so the epic-triage-license evaluator's `--issue` scope can find it — the epic does
    not exist until the crossing files it, so no operator can pre-populate `epic_issue` at
    provisioning time. Merges `epic_issue`/`seed` onto `repo`'s own entry (creating the config file or
    the entry when absent — item P's provisioning may not have run yet in a test/dev config), leaving
    every other field (`triage_issue`, any other repo's entry) untouched. Atomic write (`.tmp` +
    `rename`), `tools/gh-app`'s own credential-cache discipline — never observed half-written."""
    path = pathlib.Path(config_path)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    repos = data.setdefault("repos", [])
    entry = next((e for e in repos if e.get("repo") == repo), None)
    if entry is None:
        entry = {"repo": repo}
        repos.append(entry)
    if epic_issue is not None:
        entry["epic_issue"] = epic_issue
    if seed is not None:
        entry["seed"] = seed
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def _task_sidecar(path):
    """The drafting task (`owner/repo#seed`) a local run-dir file belongs to, read from the sidecar
    the runner writes once at drafting time (`<run-dir>/task.txt`) — the runner already knows its own
    repo/seed; an evaluator invoked later with only `--path` never re-guesses it from the filesystem."""
    try:
        return (pathlib.Path(path).resolve().parent / "task.txt").read_text().strip()
    except OSError:
        return ""


def triage_license(task, *, dispositions):
    """True (pass) / False (fail) / None (UNKNOWN — no record at all yet) for whether `task`'s own
    seed (the part of `owner/repo#seed` after the `#`) carries a `go` disposition — the SAME
    last-record-per-seed rule `latest_triage_dispositions` already applies to the sweep, held here
    over exactly one seed instead of the whole backlog."""
    _repo, _, seed = task.partition("#")
    disposition = dispositions.get(seed)
    if disposition is None:
        return None
    return disposition == "go"


def evaluate(*, path=None, issue=None, gh=None, config_path=None, owner_login=None):
    """The pure(ish) core of `design_gate.py evaluate` (the `design-triage-license` /
    `epic-triage-license` evaluators, process.toml): resolves which repo/seed a `--path` or `--issue`
    scope names (the PM's own config, `YR_PM_CONFIG`), reads that repo's triage trail, and judges the
    SAME `go`-disposition rule the sweep itself obeys. Returns `(rc, token)` — the merge-evaluator
    contract every evaluator seam in this codebase shares (`tools/design_resolver.py`'s own shape):
    `rc=0` pass, `rc=1` with `token` naming the failed condition, never a third state from here."""
    gh = gh or _gh
    owner_login = owner_login if owner_login is not None else os.environ.get("YR_OWNER_LOGIN", "")
    config_path = config_path or os.environ.get(
        "YR_PM_CONFIG", str(pathlib.Path(DEV_RUNNER_HOME) / "pm-repos.json"))
    entries = _load_pm_config(config_path)

    if path:
        task = _task_sidecar(path)
        if not task:
            return 1, "task_unreadable"
        repo, _, _seed = task.partition("#")
    elif issue:
        # the epic-triage-license scope (the crossing's own machinery flip, it-36 slice G, #472):
        # the epic issue NUMBER is never the seed — `YR-TRIAGE: seed=<ideas file stem>` is written
        # by the owner before any epic exists at all. The config entry's own `seed` field (written
        # by `tools/cross.py` at filing time, alongside `epic_issue`, via `update_pm_config_entry`)
        # is what names the real seed this epic crossed from; an entry with no `epic_issue` match
        # (the epic hasn't been recorded yet) or no `seed` at all fails closed, never guesses.
        entry = next((e for e in entries if str(e.get("epic_issue")) == str(issue)), None)
        if entry is None:
            return 1, "repo_unconfigured"
        repo = entry["repo"]
        task = f"{repo}#{entry.get('seed') or ''}"
    else:
        return 1, "no_scope"

    entry = next((e for e in entries if e.get("repo") == repo), None)
    if entry is None:
        return 1, "repo_unconfigured"
    try:
        ok, trail = _fetch_triage_trail(gh, repo, entry["triage_issue"])
    except Exception:
        ok, trail = False, []
    if not ok:
        return 1, "triage_unreadable"

    dispositions = latest_triage_dispositions(trail, owner_login)
    result = triage_license(task, dispositions=dispositions)
    if result is None or result is False:
        return 1, "triage_licensed"
    return 0, ""


# --- the independence evaluator (it-36 slice D declared the guard; the tool owns the identity
#     comparison, held over the PM's own ledger — never the doc's authorship lines) --------------------
def independence(review_run_id, *, ledger_rows):
    """True (pass) / False (fail) / None (UNKNOWN) for author != verifier: `review_run_id`'s own
    ledger row names its drafting task; that task's `product`-stage row names the drafting run.
    Independence holds when the two run ids differ — collides only when the reviewing run reused
    the very run id that drafted the doc, the pathological case the guard exists to catch."""
    mine = next((r for r in ledger_rows if r.get("run_id") == review_run_id), None)
    if mine is None:
        return None
    task = mine.get("task")
    draft_rows = [r for r in ledger_rows if r.get("task") == task and r.get("stage") == "product"]
    if not draft_rows:
        return None
    return review_run_id != draft_rows[0].get("run_id")


def _review_run_id_sidecar(path):
    try:
        return (pathlib.Path(path).resolve().parent / "review-run-id.txt").read_text().strip()
    except OSError:
        return ""


def cli_independence(path, *, ledger_dir=None):
    ledger_dir = ledger_dir or str(pathlib.Path(DEV_RUNNER_HOME) / "ledger")
    review_run_id = _review_run_id_sidecar(path)
    if not review_run_id:
        return 1, "independent"
    result = independence(review_run_id, ledger_rows=ledger.load_rows(ledger_dir))
    if result is None or result is False:
        return 1, "independent"
    return 0, ""


# --- the architect's arch review: verdict grammar + the ADR (it-36 slice F) ----------------------------
ARCH_VALID_VERDICTS = ("fit", "refit", "block")
ADR_UPDATE_TRIGGER = "Write at ship"   # the maintenance-contract row this ADR names on admission
                                       # (documentation-model.md's own admission test)


def parse_verdict(text, *, valid=ARCH_VALID_VERDICTS):
    """The last line-anchored `VERDICT:` line — `tools/review_bundle.py`'s own grammar (case-
    sensitive, no leading whitespace, last line wins). Raises ValueError naming what is wrong: a
    malformed stage output is a loud stop here, never a guess at what the model meant."""
    lines = [ln[len("VERDICT:"):].strip() for ln in text.splitlines() if ln.startswith("VERDICT:")]
    if not lines:
        raise ValueError("no line-anchored VERDICT: line found")
    verdict = lines[-1].lower()
    if verdict not in valid:
        raise ValueError(f"VERDICT {verdict!r} is not one of {valid!r}")
    return verdict


def parse_alternatives(text):
    """Every line-anchored `ALTERNATIVE:` line, in order — the architect's own mandate names at
    least one argued alternative for the abstraction/pattern/libraries/language/boundary choice."""
    return [ln[len("ALTERNATIVE:"):].strip() for ln in text.splitlines() if ln.startswith("ALTERNATIVE:")]


def parse_arch_output(text):
    """The arch stage's own grammar: `VERDICT: fit|refit|block` plus >=1 `ALTERNATIVE:` line.
    Returns `{"verdict", "alternatives", "findings_text"}`; raises ValueError on either being
    absent/malformed — never a partial, silently-accepted result."""
    verdict = parse_verdict(text)
    alternatives = parse_alternatives(text)
    if not alternatives:
        raise ValueError("no ALTERNATIVE: line found — the architect names at least one argued "
                         "alternative")
    return {"verdict": verdict, "alternatives": alternatives, "findings_text": text.strip()}


def render_adr(*, title, verdict, alternatives, findings_text, today=None):
    """An ADR's full markdown (frontmatter + body): `type: research`, admitted to the architecture
    home under the *Write at ship* maintenance-contract trigger — documentation-model.md's own
    admission test (a new cross-cutting doc must name its update trigger to be created at all)."""
    date = today or _utcnow().strftime("%Y-%m-%d")
    alt_md = "\n".join(f"- {a}" for a in alternatives)
    return (
        "---\n"
        "type: research\n"
        "status: active\n"
        f"created: {date}\n"
        f"updated: {date}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"**Update trigger:** {ADR_UPDATE_TRIGGER}\n\n"
        f"**Verdict:** {verdict}\n\n"
        "## Alternatives considered\n\n"
        f"{alt_md}\n\n"
        "## Findings\n\n"
        f"{findings_text}\n"
    )


def write_arch_adr(vault, *, architecture_home, slug, title, verdict, alternatives, findings_text):
    """Writes the ADR as a new file (the create row's own shape: one complete payload, never a
    two-step) under the architecture home; `vault.write()` reads it back through the file to confirm.
    Returns the ADR's vault-relative path."""
    content = render_adr(title=title, verdict=verdict, alternatives=alternatives,
                         findings_text=findings_text)
    path = f"{architecture_home.rstrip('/')}/{slug}.md"
    vault.write(path, content)
    return path


# --- activation: the engine decides; this writes only on its say-so (it-36 slice F) ---------------------
PROCESS_PY = pathlib.Path(__file__).resolve().parent / "process.py"
ACTIVATION_TRANSITION = "design-doc.draft->active.machinery"


def _default_transition_check(path):
    proc = subprocess.run(
        ["python3", str(PROCESS_PY), "transition-check", ACTIVATION_TRANSITION, "--path", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    ok = proc.returncode == 0
    return ok, ("" if ok else (proc.stderr or proc.stdout or "").strip())


def activate_draft(*, path, draft_text, vault, vault_path, architecture_home, adr_slug, adr_title,
                   arch_result, who, accept_date=None, transition_check=None):
    """The activation act: ask the engine first (`process.py transition-check
    design-doc.draft->active.machinery --path <path>` — the guards D declares, the triage license and
    the independence evaluator, are what decide; this never re-implements them) and write only on
    exit 0. On pass: the ADR (through the vault client, into `architecture_home`), the draft's body
    plus its `YR-ACCEPT` line (`who` = the App slug), and the `status: active` frontmatter set (the
    payload in `value`) — every write read back through the file by the vault client itself. An
    unreachable/refused vault interface raises `VaultUnreachable` — a loud stop, never a retry into a
    filesystem write."""
    check = transition_check or _default_transition_check
    ok, detail = check(path)
    if not ok:
        return {"activated": False, "reason": detail or "the transition check refused"}

    adr_path = write_arch_adr(vault, architecture_home=architecture_home, slug=adr_slug,
                              title=adr_title, verdict=arch_result["verdict"],
                              alternatives=arch_result["alternatives"],
                              findings_text=arch_result.get("findings_text", ""))

    date = accept_date or _utcnow().strftime("%Y-%m-%d")
    accept_line = f"\n\nYR-ACCEPT: who={who} date={date}\n"
    full_text = draft_text.rstrip("\n") + accept_line
    vault.write(vault_path, full_text)
    vault.patch_frontmatter(vault_path, "status", "active")

    return {"activated": True, "adr_path": adr_path}


BLOCKED_MARKER = "YR-TRIAGE-PACK-BLOCKED"


def render_blocked_pack_body(seed, verdict, alternatives):
    """The flagged pack line a `block` verdict (after one fold) posts back to the triage issue — the
    same paste-ready shape `_render_pack_body` uses for an undecided seed, marked BLOCKED instead so
    the sweep's own reader never mistakes it for a fresh, undecided pack."""
    alt_md = "\n".join(f"- {a}" for a in alternatives)
    return (
        f"{BLOCKED_MARKER}\n"
        f"  seed: {seed}\n\n"
        f"**verdict:** {verdict} (after one fold — the architect's mandate did not clear)\n\n"
        f"**alternatives considered:**\n{alt_md}\n\n"
        "This draft is NOT activated. A new `go` disposition (or a revised draft) is required "
        "before it can be re-reviewed."
    )


def flag_block(gh, repo, triage_issue, seed, verdict, alternatives):
    _comment(gh, repo, triage_issue, render_blocked_pack_body(seed, verdict, alternatives))


# --- the activation target: a local component root -> its REST-relative vault paths ---------------------
def vault_rel_path(local_path, *, vault_root=None):
    """A local vault-mirror path's REST-relative form (relative to `VAULT_ROOT`/`YR_VAULT_ROOT` —
    the same root `tools/design_resolver.py` reads locally). Falls back to the path as given when it
    does not sit under the root at all (an operator-misconfigured root is a loud, visible path in the
    CLI's own output, never a silent guess)."""
    root = pathlib.Path(vault_root or VAULT_ROOT).resolve()
    p = pathlib.Path(local_path).resolve()
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def next_iteration_slug(component_root, seed_stem):
    """The next iteration folder's own ordinal — one past the highest existing `N-*` folder under
    `component_root/iterations/` (folder ordinals record ranking SLOT, monotonic, never reused —
    documentation-model.md's own *Iterations are ordered by slot* rule) — paired with the seed's own
    stem as the iteration's kebab slug."""
    iterations_dir = pathlib.Path(component_root) / "iterations"
    max_n = 0
    if iterations_dir.is_dir():
        for child in iterations_dir.iterdir():
            if child.is_dir():
                m = re.match(r"^(\d+)-", child.name)
                if m:
                    max_n = max(max_n, int(m.group(1)))
    return f"{max_n + 1}-{seed_stem}"


def resolve_activation_paths(component_root, seed_stem, *, vault_root=None):
    """The activation's two REST-relative destinations: the draft's own iteration path
    (`iterations/<n>-<seed>/01-<seed>.md`) and the component's architecture home (`architecture/`)."""
    root_rel = vault_rel_path(component_root, vault_root=vault_root)
    slug = next_iteration_slug(component_root, seed_stem)
    return {
        "vault_path": f"{root_rel}/iterations/{slug}/01-{seed_stem}.md",
        "architecture_home": f"{root_rel}/architecture",
    }


def _cli_resolve_paths(argv):
    ap = argparse.ArgumentParser(description="resolve a seed's activation-time vault paths")
    ap.add_argument("--component-root", required=True)
    ap.add_argument("--seed", required=True)
    args = ap.parse_args(argv)
    print(json.dumps(resolve_activation_paths(args.component_root, args.seed)))
    return 0


# --- main(): real repo discovery (item P's own human provisioning) --------------------------------------
def _resolve_entry(raw):
    entry = {"repo": raw["repo"], "triage_issue": raw["triage_issue"], "epic_issue": raw.get("epic_issue")}
    try:
        seeds = rank.ranked_seeds(pathlib.Path(raw["component_root"]))
        entry["seeds"] = {"ok": True, "value": seeds}
    except OSError as e:
        entry["seeds"] = {"ok": False, "error": str(e)}
    ok, text = sources.vault_doc(pathlib.Path(raw["strategy_doc"]))
    if not ok:
        entry["strategy"] = {"ok": False, "error": text}
    else:
        try:
            entry["strategy"] = {"ok": True, "value": strategy.parse_strategy(text)}
        except strategy.StrategyError as e:
            entry["strategy"] = {"ok": False, "error": str(e)}
    return entry


def _cli_evaluate(argv):
    ap = argparse.ArgumentParser(description="the design/epic triage-license evaluator")
    ap.add_argument("--path", default="")
    ap.add_argument("--issue", default="")
    args = ap.parse_args(argv)
    rc, token = evaluate(path=args.path or None, issue=args.issue or None)
    if token:
        print(token)
    return rc


def _cli_independence(argv):
    ap = argparse.ArgumentParser(description="the design-doc activation independence evaluator")
    ap.add_argument("--path", required=True)
    args = ap.parse_args(argv)
    rc, token = cli_independence(args.path)
    if token:
        print(token)
    return rc


def _cli_activate(argv):
    ap = argparse.ArgumentParser(description="activate a reviewed design draft (it-36 slice F)")
    ap.add_argument("--path", required=True, help="the local, folded+fit+arch-reviewed draft file")
    ap.add_argument("--vault-path", required=True, help="the REST-relative destination in the vault")
    ap.add_argument("--architecture-home", required=True)
    ap.add_argument("--adr-slug", required=True)
    ap.add_argument("--adr-title", required=True)
    ap.add_argument("--arch-result", required=True, help="path to the arch stage's parsed JSON "
                    '(from `parse-arch`): {"verdict", "alternatives", "findings_text"}')
    ap.add_argument("--who", required=True)
    args = ap.parse_args(argv)
    draft_text = pathlib.Path(args.path).read_text(encoding="utf-8")
    arch_result = json.loads(pathlib.Path(args.arch_result).read_text())
    try:
        result = activate_draft(path=args.path, draft_text=draft_text, vault=vault_api.VaultClient(),
                                vault_path=args.vault_path, architecture_home=args.architecture_home,
                                adr_slug=args.adr_slug, adr_title=args.adr_title,
                                arch_result=arch_result, who=args.who)
    except vault_api.VaultUnreachable as e:
        # a refused/unreachable vault interface is a loud stop, never a silent fallback — reported
        # plainly, never as a bare traceback, but the process still ends non-zero either way.
        print(f"design_gate: activation stopped — {e}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0 if result.get("activated") else 1


def _cli_parse_arch(argv):
    ap = argparse.ArgumentParser(description="parse the arch stage's raw output (verdict grammar)")
    ap.add_argument("--in", dest="in_path", required=True)
    args = ap.parse_args(argv)
    try:
        result = parse_arch_output(pathlib.Path(args.in_path).read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"design_gate: arch stage output malformed: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


def _cli_parse_fit(argv):
    ap = argparse.ArgumentParser(description="parse the fit stage's raw output (verdict-only grammar)")
    ap.add_argument("--in", dest="in_path", required=True)
    args = ap.parse_args(argv)
    try:
        verdict = parse_verdict(pathlib.Path(args.in_path).read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"design_gate: fit stage output malformed: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"verdict": verdict}))
    return 0


def _cli_flag_block(argv):
    ap = argparse.ArgumentParser(description="return a blocked draft to the triage issue")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--triage-issue", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--arch-result", required=True, help="the arch stage's parsed JSON (`parse-arch`)")
    args = ap.parse_args(argv)
    result = json.loads(pathlib.Path(args.arch_result).read_text())
    flag_block(_gh, args.repo, args.triage_issue, args.seed, result["verdict"], result["alternatives"])
    return 0


_SUBCOMMANDS = {
    "evaluate": _cli_evaluate,
    "independence": _cli_independence,
    "activate": _cli_activate,
    "parse-arch": _cli_parse_arch,
    "parse-fit": _cli_parse_fit,
    "flag-block": _cli_flag_block,
    "resolve-paths": _cli_resolve_paths,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in _SUBCOMMANDS:
        return _SUBCOMMANDS[argv[0]](argv[1:])

    ap = argparse.ArgumentParser(description="the design sweep (it-36 slice E, #470)")
    ap.add_argument("--config", default=os.environ.get(
        "YR_PM_CONFIG", str(pathlib.Path(DEV_RUNNER_HOME) / "pm-repos.json")),
        help="JSON config naming each repo's triage issue + vault component root/strategy doc "
             "(item P's own human provisioning; this tool reads it, never invents it) — "
             '{"repos": [{"repo": "owner/name", "triage_issue": N, "component_root": "...", '
             '"strategy_doc": "...", "epic_issue": N}]}')
    args = ap.parse_args(argv)
    try:
        raw_repos = json.loads(pathlib.Path(args.config).read_text()).get("repos") or []
    except OSError as e:
        print(f"design_gate: no repo config at {args.config} ({e}) — nothing to sweep", file=sys.stderr)
        return 0
    entries = [_resolve_entry(r) for r in raw_repos]
    actions = sweep_designs(repos=entries)

    # the close sweep (it-36 slice H, #473): discovered per configured repo, real but untested here
    # (mirrors `_resolve_entry`'s own real-vault-read role) — `sweep_close`'s own core is what
    # `tests/test_design_gate_close_sweep.py` drives, with a `FakeGh` and no live search. Each found
    # epic gets ITS OWN repo's `component_root`/`strategy_doc` from the SAME config entry
    # `_resolve_entry` already reads (B3, #472 fold review) — a search result names no config of its
    # own, so `main()` is the one attaching it.
    close_epics = []
    for r in raw_repos:
        try:
            found = _default_discover_close_hold(_gh, r["repo"])
        except Exception as e:  # noqa: BLE001 — a discovery failure is loud, never fatal to the sweep
            print(f"design_gate: close-hold discovery failed for {r['repo']}: {e}", file=sys.stderr)
            continue
        for f in found:
            f["component_root"] = r.get("component_root", "")
            f["strategy_doc"] = r.get("strategy_doc", "")
        close_epics.extend(found)
    actions += sweep_close(epics=close_epics)

    print(json.dumps(actions, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
