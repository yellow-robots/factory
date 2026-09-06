"""Acceptance tests for tools/design_gate.py — the design sweep (it-36 slice E, #470).

Derived from the issue's acceptance criteria, not the implementation's internals: every test drives
the module's one public, pure entry point, `sweep_designs(*, gh=None, repos, ...)`, with a stateful
FakeGh (mirrors tests/test_epic_gate.py's own style) and injected `design_active`/`spawn_stage`/
`kill_stage_group`/`ledger_spent_usd` callables — no live network, no live vault, no real pidfiles or
subprocess spawns.
"""
import datetime
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import design_gate  # noqa: E402
import stage_usage  # noqa: E402

REPO = "acme/widgets"
OWNER = "the-owner"
NOW = datetime.datetime(2026, 9, 6, tzinfo=datetime.timezone.utc)


# ---- fixture builders -----------------------------------------------------------------------------

def _seed(stem, *, value=5, effort="M", summary="do a thing"):
    discount = {"S": 0, "M": 0.5, "L": 1}[effort]
    return {"path": f"ideas/{stem}.md", "status": "open", "summary": summary,
            "value": value, "effort": effort, "rank": round(value - discount, 1), "findings": []}


def _theme(repos, *, theme_id="theme-1"):
    return {"id": theme_id, "goal": "grow it", "target": "north star", "repos": list(repos),
            "budget_usd": 500, "stop_when": "done"}


def _strategy(repos, *, loop_budget=None, theme_id="theme-1"):
    return {"themes": [_theme(repos, theme_id=theme_id)], "constraints": [], "kpi_targets": {},
            "loop_budget_usd_per_week": loop_budget, "factory_cap": None}


def _entry(*, repo=REPO, seeds=None, strategy=None, triage_issue=99, epic_issue=None,
           seeds_ok=True, strategy_ok=True):
    seeds_res = {"ok": True, "value": seeds or []} if seeds_ok else {"ok": False, "error": "vault unreachable"}
    strategy_res = ({"ok": True, "value": strategy if strategy is not None else _strategy([repo])}
                    if strategy_ok else {"ok": False, "error": "vault unreachable"})
    return {"repo": repo, "triage_issue": triage_issue, "epic_issue": epic_issue,
            "seeds": seeds_res, "strategy": strategy_res}


def _usage_comment(model, input_tokens, output_tokens=0):
    record = {"stage": "implement", "model": model, "input_tokens": input_tokens,
              "output_tokens": output_tokens, "cache_write_tokens": 0, "cache_read_tokens": 0,
              "duration_ms": 1000}
    return stage_usage.render_summary_comment(stage_usage.build_summary([record]))


class FakeGh:
    """Injectable `gh`. `comments` is a single triage issue's own trail — a list of (author_login,
    body) pairs, chronological, shared by every issue number queried (the single-repo tests' own
    convenience: only one triage issue is ever addressed). `comments_by_issue` (issue number -> that
    same shape) opts a test into PER-ISSUE trails instead, for exercising more than one repo's triage
    issue in the same sweep without one repo's posts leaking into another's. Either way, a trail is
    mutated in place as `issue comment` calls land — so a second sweep call against the SAME instance
    sees exactly what the first one posted (how idempotence is proven).

    `pr_numbers` are the repo's canned "merged runner PRs"; `pr_usage_bodies` maps a PR number to the
    `### dev-runner usage` comment body `sources.pr_usage_from_texts` parses (a PR with no entry has
    no priced comment). `epic_state`/`epic_status` answer the governing-epic license GraphQL read."""

    def __init__(self, *, comments=None, comments_by_issue=None, pr_numbers=None, pr_usage_bodies=None,
                 epic_state="OPEN", epic_status="Ready"):
        self._shared_trail = list(comments or [])
        self._per_issue = ({str(k): list(v) for k, v in comments_by_issue.items()}
                            if comments_by_issue is not None else None)
        self.pr_numbers = list(pr_numbers or [])
        self.pr_usage_bodies = dict(pr_usage_bodies or {})
        self.epic_state = epic_state
        self.epic_status = epic_status
        self.posted = []      # every body this sweep posted via `issue comment`, any issue
        self.calls = []

    def _trail(self, issue):
        if self._per_issue is not None:
            return self._per_issue.setdefault(str(issue), [])
        return self._shared_trail

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["issue", "view"]:
            trail = self._trail(argv[2])
            return {"body": "", "comments": [{"body": b, "author": {"login": a}} for a, b in trail]}
        if argv[:2] == ["issue", "comment"]:
            body = argv[argv.index("--body") + 1]
            self._trail(argv[2]).append(("yr-pm[bot]", body))
            self.posted.append(body)
            return ""
        if argv[:2] == ["pr", "list"]:
            return [{"number": n} for n in self.pr_numbers]
        if argv[:2] == ["pr", "view"]:
            number = int(argv[2])
            body = self.pr_usage_bodies.get(number)
            return {"body": "", "comments": ([{"body": body}] if body else [])}
        if argv[:2] == ["api", "graphql"]:
            status = {"name": self.epic_status} if self.epic_status else None
            return {"data": {"repository": {"issue": {
                "state": self.epic_state,
                "projectItems": {"nodes": [{"project": {"number": 1}, "status": status}]},
            }}}}
        raise AssertionError(f"FakeGh: unexpected argv {argv}")


def _sweep(gh, entries, *, owner_login=OWNER, ledger_spent_usd=None, design_active_state=None):
    """Drives `sweep_designs` with in-memory `design_active`/`spawn_stage`/`kill_stage_group` —
    `design_active_state` (repo -> bool) is mutated by spawn/kill exactly like the real pidfile would
    be, so a test can pre-seed "a design is already in flight" or observe one starting/stopping."""
    state = design_active_state if design_active_state is not None else {}
    spawned, killed = [], []

    def design_active(repo, seed):
        return state.get(repo, False)

    def spawn_stage(repo, seed):
        spawned.append((repo, seed))
        state[repo] = True

    def kill_stage_group(repo):
        killed.append(repo)
        state[repo] = False

    actions = design_gate.sweep_designs(
        gh=gh, repos=entries, now=lambda: NOW, owner_login=owner_login,
        ledger_spent_usd=ledger_spent_usd or (lambda repo, now: 0.0),
        design_active=design_active, spawn_stage=spawn_stage, kill_stage_group=kill_stage_group,
    )
    return actions, spawned, killed, state


# ---- pack comments: posted once, never re-posted -----------------------------------------------------

def test_pack_posted_once_never_reposted():
    gh = FakeGh()
    entries = [_entry(seeds=[_seed("foo")])]

    actions1, spawned1, killed1, state = _sweep(gh, entries)
    assert any(a["action"] == "pack-posted" and a["seed"] == "foo" for a in actions1)
    packs1 = [b for b in gh.posted if design_gate.PACK_MARKER in b]
    assert len(packs1) == 1
    assert "seed: foo" in packs1[0]

    # a second sweep, same FakeGh (so it now sees its own first posted pack in the trail) — must not
    # post a second pack for the same undecided seed.
    actions2, *_ = _sweep(gh, entries, design_active_state=state)
    packs2 = [b for b in gh.posted if design_gate.PACK_MARKER in b]
    assert len(packs2) == 1
    assert all(a["action"] != "pack-posted" for a in actions2)


def test_pack_body_names_scope_value_cost_theme_and_carries_an_indented_record_line():
    gh = FakeGh(pr_numbers=[101],
                pr_usage_bodies={101: _usage_comment("claude-sonnet-5", 1_000_000)})
    entries = [_entry(seeds=[_seed("foo", value=7, effort="M", summary="scope text here")])]

    _sweep(gh, entries)
    body = gh.posted[0]
    assert "scope text here" in body                     # scope
    assert "**value:** 7" in body                          # value
    assert "**theme:** theme-1" in body                     # theme
    # cost: mean usage cost ($3.00 for 1e6 input tokens @ $3/Mtok) x the M effort factor (3) = $9.00
    assert "$9.00" in body

    lines = body.splitlines()
    marker_lines = [ln for ln in lines if ln.strip() == design_gate.PACK_MARKER]
    assert len(marker_lines) == 1 and marker_lines[0] == design_gate.PACK_MARKER  # column 0, unindented

    record_lines = [ln for ln in lines if "YR-TRIAGE:" in ln]
    assert record_lines, "no paste-ready YR-TRIAGE sample line found"
    for ln in record_lines:
        assert ln.startswith("    "), f"the sample record line must be indented in a code span: {ln!r}"
        assert not ln.startswith("YR-TRIAGE:")  # never at column 0 — it must never self-trigger


def test_pack_cost_unknown_when_no_priced_merged_pr_exists():
    gh = FakeGh(pr_numbers=[])   # no merged runner PRs at all
    entries = [_entry(seeds=[_seed("foo")])]
    _sweep(gh, entries)
    assert "unknown" in gh.posted[0]


# ---- YR-TRIAGE records: owner-only, last-per-seed wins -------------------------------------------------

def test_non_owner_triage_record_is_ignored():
    gh = FakeGh(comments=[("an-intruder", "YR-TRIAGE: seed=foo disposition=go who=@an-intruder")])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == []
    assert any(a["action"] == "idle" and a["reason"] == "no-candidate" for a in actions)


def test_owner_go_record_licenses_a_spawn():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == [(REPO, "foo")]
    assert any(a["action"] == "spawned" and a["seed"] == "foo" for a in actions)


def test_last_record_per_seed_wins_park_after_go_never_spawns():
    gh = FakeGh(comments=[
        (OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER),
        (OWNER, "YR-TRIAGE: seed=foo disposition=park who=@" + OWNER),
    ])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == []                                     # the LAST record (park) wins, not the first (go)
    assert any(a["action"] == "idle" and a["reason"] == "no-candidate" for a in actions)


def test_last_record_per_seed_wins_go_after_park_spawns():
    gh = FakeGh(comments=[
        (OWNER, "YR-TRIAGE: seed=foo disposition=park who=@" + OWNER),
        (OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER),
    ])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == [(REPO, "foo")]


# ---- reversal: park/reject after go stops an in-flight design ------------------------------------------

def test_reversal_kills_the_in_flight_group_and_notes_it():
    gh = FakeGh(comments=[
        (OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER),
        (OWNER, "YR-TRIAGE: seed=foo disposition=park who=@" + OWNER),
    ])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, state = _sweep(gh, entries, design_active_state={REPO: True})
    assert killed == [REPO]
    assert state[REPO] is False
    assert any(a["action"] == "reversed" and a["seed"] == "foo" for a in actions)
    assert any("stopped" in b and "foo" in b for b in gh.posted)


def test_reversal_is_a_no_op_when_nothing_was_in_flight():
    gh = FakeGh(comments=[
        (OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER),
        (OWNER, "YR-TRIAGE: seed=foo disposition=reject who=@" + OWNER),
    ])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries, design_active_state={REPO: False})
    assert killed == []
    assert not any(a["action"] == "reversed" for a in actions)


def test_a_go_never_resumes_without_a_fresh_go_record_after_reversal():
    """The reversal comes with NO third record — a `go` must never fire again off the same stale trail."""
    gh = FakeGh(comments=[
        (OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER),
        (OWNER, "YR-TRIAGE: seed=foo disposition=park who=@" + OWNER),
    ])
    entries = [_entry(seeds=[_seed("foo")])]
    _sweep(gh, entries, design_active_state={REPO: True})
    # a second, later tick over the SAME (unchanged) trail must not re-spawn
    actions2, spawned2, killed2, state2 = _sweep(gh, entries, design_active_state={REPO: False})
    assert spawned2 == []
    assert any(a["action"] == "idle" and a["reason"] == "no-candidate" for a in actions2)


# ---- the governing epic's license: un-Readied or closed withdraws it -----------------------------------

def test_epic_un_readied_withdraws_the_license_and_stops_an_in_flight_design():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)],
                epic_state="OPEN", epic_status="Backlog")   # Ready -> Backlog: un-Readied
    entries = [_entry(seeds=[_seed("foo")], epic_issue=5)]
    actions, spawned, killed, state = _sweep(gh, entries, design_active_state={REPO: True})
    assert killed == [REPO]
    assert any(a["action"] == "withdrawn" for a in actions)
    assert any("un-Readied or closed" in b for b in gh.posted)


def test_epic_closed_withdraws_the_license():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)],
                epic_state="CLOSED", epic_status="Ready")
    entries = [_entry(seeds=[_seed("foo")], epic_issue=5)]
    actions, spawned, killed, state = _sweep(gh, entries, design_active_state={REPO: True})
    assert killed == [REPO]
    assert any(a["action"] == "withdrawn" for a in actions)


def test_epic_withdrawn_never_licenses_a_fresh_spawn():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)],
                epic_state="OPEN", epic_status="Backlog")
    entries = [_entry(seeds=[_seed("foo")], epic_issue=5)]
    actions, spawned, killed, _ = _sweep(gh, entries, design_active_state={REPO: False})
    assert spawned == []
    assert any(a["action"] == "idle" and a["reason"] == "no-candidate" for a in actions)


def test_epic_readied_and_open_licenses_a_spawn():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)],
                epic_state="OPEN", epic_status="Ready")
    entries = [_entry(seeds=[_seed("foo")], epic_issue=5)]
    actions, spawned, killed, _ = _sweep(gh, entries, design_active_state={REPO: False})
    assert spawned == [(REPO, "foo")]


# ---- idling, loudly, and never substituting factory work ------------------------------------------------

def test_no_theme_idles_and_says_so():
    gh = FakeGh()
    entries = [_entry(seeds=[_seed("foo")], strategy=_strategy(["some/other-repo"]))]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == [] and killed == []
    assert any(a["action"] == "idle" and a["reason"] == "no-theme" for a in actions)
    assert len(gh.posted) == 1
    assert "no strategy theme" in gh.posted[0]
    assert "No factory work is substituted" in gh.posted[0]


def test_no_in_direction_go_candidate_idles_and_says_so():
    gh = FakeGh()   # no triage records at all -> nothing is licensed
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == []
    assert any(a["action"] == "idle" and a["reason"] == "no-candidate" for a in actions)
    assert any("No factory work is substituted" in b for b in gh.posted)


def test_loop_budget_exhausted_escalates_then_idles():
    gh = FakeGh()
    entries = [_entry(seeds=[_seed("foo")], strategy=_strategy([REPO], loop_budget=50.0))]
    actions, spawned, killed, _ = _sweep(gh, entries, ledger_spent_usd=lambda repo, now: 75.0)
    assert spawned == []
    assert any(a["action"] == "idle" and a["reason"] == "loop-budget" for a in actions)
    assert len(gh.posted) == 1
    assert design_gate.ESCALATION_MARKER in gh.posted[0]
    assert "why=loop-budget-exhausted" in gh.posted[0]


def test_loop_budget_escalation_posted_once_never_repeated():
    gh = FakeGh()
    entries = [_entry(seeds=[_seed("foo")], strategy=_strategy([REPO], loop_budget=50.0))]
    _sweep(gh, entries, ledger_spent_usd=lambda repo, now: 75.0)
    _sweep(gh, entries, ledger_spent_usd=lambda repo, now: 80.0)
    escalations = [b for b in gh.posted if design_gate.ESCALATION_MARKER in b]
    assert len(escalations) == 1


def test_loop_budget_under_threshold_does_not_escalate():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)])
    entries = [_entry(seeds=[_seed("foo")], strategy=_strategy([REPO], loop_budget=50.0))]
    actions, spawned, killed, _ = _sweep(gh, entries, ledger_spent_usd=lambda repo, now: 10.0)
    assert spawned == [(REPO, "foo")]
    assert not any(design_gate.ESCALATION_MARKER in b for b in gh.posted)


def test_vault_interface_down_idles_and_says_so():
    gh = FakeGh()
    entries = [_entry(seeds_ok=False)]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == []
    assert any(a["action"] == "idle" and a["reason"] == "vault-down" for a in actions)
    assert any("vault interface did not answer" in b for b in gh.posted)


def test_strategy_unreadable_also_idles_as_vault_down():
    gh = FakeGh()
    entries = [_entry(strategy_ok=False)]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert any(a["action"] == "idle" and a["reason"] == "vault-down" for a in actions)


# ---- one design in flight per repository -----------------------------------------------------------------

def test_no_second_spawn_while_a_design_is_already_in_flight_for_the_repo():
    gh = FakeGh(comments=[(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)])
    entries = [_entry(seeds=[_seed("foo")])]
    actions, spawned, killed, _ = _sweep(gh, entries, design_active_state={REPO: True})
    assert spawned == []
    assert any(a["action"] == "in-flight" and a["seed"] == "foo" for a in actions)


def test_top_ranked_go_candidate_is_the_one_spawned():
    gh = FakeGh(comments=[
        (OWNER, "YR-TRIAGE: seed=low disposition=go who=@" + OWNER),
        (OWNER, "YR-TRIAGE: seed=high disposition=go who=@" + OWNER),
    ])
    # entry["seeds"] arrives already ranked (rank.ranked_seeds's own contract, descending by rank) —
    # the sweep trusts that order and takes the FIRST licensed `go` it finds, never re-sorting.
    entries = [_entry(seeds=[_seed("high", value=9), _seed("low", value=2)])]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == [(REPO, "high")]


def test_multiple_repositories_are_swept_independently():
    other_repo = "acme/gadgets"
    gh = FakeGh(comments_by_issue={
        1: [(OWNER, "YR-TRIAGE: seed=foo disposition=go who=@" + OWNER)],   # REPO's own triage issue: go
        2: [],                                                              # other_repo's: undecided
    })
    entries = [
        _entry(repo=REPO, seeds=[_seed("foo")], triage_issue=1),
        _entry(repo=other_repo, seeds=[_seed("foo")], strategy=_strategy([other_repo]), triage_issue=2),
    ]
    actions, spawned, killed, _ = _sweep(gh, entries)
    assert spawned == [(REPO, "foo")]                     # only the repo with a `go` record spawns
    assert any(a["repo"] == other_repo and a["action"] == "pack-posted" for a in actions)
    assert any(a["repo"] == REPO and a["action"] == "spawned" for a in actions)
