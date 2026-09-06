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
import ledger
import rank
import sources
import strategy
import textutil

# --- record grammar (records.toml, it-36 slice D, #469 — minted there; read here) ----------------------
TRIAGE_MARKER = "YR-TRIAGE:"
PACK_MARKER = "YR-TRIAGE-PACK"
ESCALATION_MARKER = "YR-ESCALATION:"

# S/M/L effort factor (the Base's own vocabulary, tools/rank.py); an unrecognized effort falls to the
# L factor — the same discount rank.py's own `compute_rank` gives an unrecognized effort.
EFFORT_FACTOR = {"S": 1, "M": 3, "L": 6}

DEV_RUNNER_HOME = os.environ.get("DEV_RUNNER_HOME", str(pathlib.Path.home() / ".cache" / "dev-runner"))
DESIGN_RUNNER = os.environ.get("DESIGN_RUNNER", str(pathlib.Path(__file__).resolve().parent / "design-runner.sh"))


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


def main(argv=None):
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
    print(json.dumps(actions, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
