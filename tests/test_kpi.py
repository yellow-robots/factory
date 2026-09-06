"""Acceptance tests for tools/kpi.py — the KPI report on demand (it-36 slice J, #475).

Derived from the issue's acceptance criteria (the spec), not from kpi.py's own internals: the
report tool named on the Deliverable line writes the month's KPI note stating velocity, cycle
time, blocked/repair/revert rates, spend, backlog age, inflow-vs-outflow, the product-vs-factory
ratio and deploy lag — each read from a native surface (PR-usage comments, issue timelines, the
board, git, the deploy trail, the ideas folder) against the strategy doc's own targets — and posts
YR-KPI (and YR-STRATEGY when the doc changes).
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import kpi            # noqa: E402
import records        # noqa: E402
import round_record   # noqa: E402
import stage_usage    # noqa: E402


# ============ small fixture builders ============

def _seed(**kw):
    base = {"path": "ideas/x.md", "status": "open", "created": "", "updated": "", "crossed_to": ""}
    base.update(kw)
    return base


def _board_node(number, *, repo="yellow-robots/factory", state="OPEN"):
    return {
        "content": {"number": number, "title": f"item {number}", "state": state,
                    "createdAt": f"2026-09-01T00:00:{number % 60:02d}Z",
                    "issueType": {"name": "Task"}, "repository": {"nameWithOwner": repo}},
        "status": {"name": "Ready"},
    }


def _full_inputs(**overrides):
    base = {
        "merge_dates": ["2026-09-01T00:00:00Z"],
        "cycle_events": [{"created": "2026-08-30T00:00:00Z", "ready_at": None,
                          "merged": "2026-09-01T00:00:00Z"}],
        "pr_trails": [["clean, no bounce"]],
        "pr_usages": [{"stages": [], "cost_usd": 1.0}],
        "commit_subjects": ["fix a bug"],
        "board_rows": [{"createdAt": "2026-08-25T00:00:00Z"}],
        "ideas_seeds": [_seed(created="2026-09-01T00:00:00Z")],
        "deploy_dates": ["2026-09-02T00:00:00Z"],
        "now": "2026-09-08T00:00:00Z",
    }
    base.update(overrides)
    return base


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_component_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "T"], root)
    return root


def _commit(root, message, when_iso):
    (root / "f.txt").write_text(message)
    _git(["add", "f.txt"], root)
    env = {**os.environ, "GIT_AUTHOR_DATE": when_iso, "GIT_COMMITTER_DATE": when_iso}
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=str(root), env=env, check=True)


STRATEGY_DOC = """---
status: active
---
# Strategy

```yr-strategy
loop_budget_usd_per_week = 500
factory_cap = 3

[[themes]]
id = "theme-a"
goal = "Ship X"
target = "metric > 10"
repos = ["owner/repo-a"]
budget_usd = 1000
stop_when = "metric <= 10"

[constraints]
max_parallel = 2

[kpi_targets]
velocity_per_week = 5
```
"""


# ============ velocity: merged PRs per week ============

def test_velocity_per_week_counts_merges_and_normalizes_to_a_weekly_rate():
    merges = ["2026-09-01T00:00:00Z", "2026-09-08T00:00:00Z",
             "2026-09-15T00:00:00Z", "2026-09-22T00:00:00Z"]
    r = kpi.velocity_per_week(merges, start="2026-09-01T00:00:00Z", end="2026-09-29T00:00:00Z")
    assert r["merged"] == 4
    assert r["weeks"] == 4.0
    assert r["per_week"] == 1.0


def test_velocity_per_week_zero_merges_is_zero_not_a_crash():
    r = kpi.velocity_per_week([], start="2026-09-01T00:00:00Z", end="2026-10-01T00:00:00Z")
    assert r["merged"] == 0
    assert r["per_week"] == 0.0


# ============ cycle time: created -> Ready -> merged ============

def test_cycle_time_hours_reports_lead_time_and_queue_time_separately():
    events = [
        {"created": "2026-09-01T00:00:00Z", "ready_at": "2026-09-01T12:00:00Z",
         "merged": "2026-09-02T00:00:00Z"},
        {"created": "2026-09-03T00:00:00Z", "ready_at": None, "merged": "2026-09-04T00:00:00Z"},
    ]
    r = kpi.cycle_time_hours(events)
    assert r["count"] == 2
    assert r["mean_total_hours"] == 24.0
    assert r["mean_queue_hours"] == 12.0, "only the event carrying ready_at contributes to queue time"


def test_cycle_time_hours_empty_events_reports_none_not_a_crash():
    assert kpi.cycle_time_hours([]) == {"mean_total_hours": None, "mean_queue_hours": None, "count": 0,
                                        "gap_reason": "no PR merged this window"}


# ============ blocked rate: the runner's own bounce/block prose ============

def test_blocked_rate_counts_a_pr_once_regardless_of_repeated_bounce_comments():
    trails = [
        [round_record.NEEDS_INFO_PREFIX + " some reason", round_record.NEEDS_INFO_PREFIX + " again"],
        [round_record.BLOCKED_PREFIX + "stuck"],
        ["clean PR, no bounce at all"],
    ]
    r = kpi.blocked_rate(trails)
    assert r == {"blocked": 2, "total": 3, "rate": round(2 / 3, 3)}


def test_blocked_rate_zero_prs_reports_none_rate_not_a_zero_division():
    assert kpi.blocked_rate([])["rate"] is None


# ============ repair rate: a PR counts once regardless of how many *_repair stages ============

def test_repair_rate_counts_a_pr_once_when_any_stage_name_ends_repair():
    usages = [
        {"stages": [{"stage": "implement"}, {"stage": "check_repair"}, {"stage": "review_repair"}]},
        {"stages": [{"stage": "implement"}]},
        {"stages": []},
    ]
    r = kpi.repair_rate(usages)
    assert r == {"repaired": 1, "total": 3, "rate": round(1 / 3, 3)}


# ============ revert rate: GitHub's own `Revert "..."` grammar ============

def test_revert_rate_reads_githubs_own_revert_commit_grammar():
    subjects = ['Revert "add feature X"', "fix bug", "add feature Y"]
    r = kpi.revert_rate(subjects)
    assert r == {"reverts": 1, "total": 3, "rate": round(1 / 3, 3)}


def test_revert_rate_never_matches_a_mid_line_mention_of_revert():
    subjects = ["please do not revert this later", "normal commit"]
    assert kpi.revert_rate(subjects)["reverts"] == 0


def test_revert_rate_is_a_three_none_triple_when_the_surface_was_never_declared():
    """B2, #475 fold review round 1: `None` in (`--code-root` absent) -> a three-`None` triple,
    distinct from `[]` in (code root declared, genuinely zero commits this window) — conflating the
    two would let the note print "0/0" as though someone actually looked."""
    assert kpi.revert_rate(None) == {"reverts": None, "total": None, "rate": None}


# ============ spend: pr_usage's own cost_usd, summed ============

def test_total_spend_usd_sums_cost_usd_treating_missing_as_zero():
    usages = [{"cost_usd": 1.5}, {"cost_usd": None}, {}]
    assert kpi.total_spend_usd(usages) == 1.5


# ============ backlog age: the board, with createdAt ============

def test_backlog_age_days_means_age_of_every_open_board_row():
    rows = [{"createdAt": "2026-09-01T00:00:00Z"}, {"createdAt": "2026-09-06T00:00:00Z"}]
    r = kpi.backlog_age_days(rows, now="2026-09-08T00:00:00Z")
    assert r["count"] == 2
    assert r["mean_days"] == 4.5   # (7 + 2) / 2


def test_backlog_age_days_drops_rows_missing_createdat_from_the_mean():
    rows = [{"createdAt": ""}, {"createdAt": "2026-09-01T00:00:00Z"}]
    r = kpi.backlog_age_days(rows, now="2026-09-02T00:00:00Z")
    assert r["count"] == 1


# ============ inflow / outflow: the ideas folder's own frontmatter ============

def test_inflow_counts_seeds_captured_inside_the_window():
    seeds = [_seed(created="2026-09-05T00:00:00Z"), _seed(created="2026-08-20T00:00:00Z")]
    r = kpi.inflow_outflow(seeds, start="2026-09-01T00:00:00Z", end="2026-10-01T00:00:00Z")
    assert r["inflow"] == 1


def test_outflow_counts_seeds_that_left_open_custody_inside_the_window():
    seeds = [
        _seed(status="go", updated="2026-09-10T00:00:00Z"),           # left open, inside window
        _seed(status="open", updated="2026-09-10T00:00:00Z"),         # still open: not outflow
        _seed(status="reject", updated="2026-08-01T00:00:00Z"),       # left, but outside the window
    ]
    r = kpi.inflow_outflow(seeds, start="2026-09-01T00:00:00Z", end="2026-10-01T00:00:00Z")
    assert r["outflow"] == 1


# ============ product-vs-factory ratio: crossed_to's own repo ============

def test_product_factory_ratio_splits_by_the_crossed_to_repo():
    seeds = [
        _seed(crossed_to="acme/product#1"),
        _seed(crossed_to="acme/product#2"),
        _seed(crossed_to="yellow-robots/factory#3"),
        _seed(crossed_to=""),   # never shipped: excluded
    ]
    r = kpi.product_factory_ratio(seeds, factory_repo="yellow-robots/factory")
    assert r == {"product": 2, "factory": 1, "ratio": 2.0}


def test_product_factory_ratio_is_none_with_no_delivered_seeds():
    assert kpi.product_factory_ratio([_seed(crossed_to="")]) == {"product": 0, "factory": 0, "ratio": None}


def test_product_factory_ratio_is_infinite_with_product_only_and_no_factory_deliveries():
    r = kpi.product_factory_ratio([_seed(crossed_to="acme/product#1")], factory_repo="yellow-robots/factory")
    assert r["ratio"] == float("inf")


def test_product_factory_ratio_classifies_by_strategy_theme_membership_when_available():
    """I5, #475 fold review round 1: with a parsed strategy, `strategy.matching_theme` is the ONLY
    classifier — a repo no theme names is factory, whatever it's called, not just literally
    "yellow-robots/factory" (the pre-fold-review rule, now the fallback only)."""
    parsed_strategy = {"themes": [{"id": "theme-a", "repos": ["acme/product"]}]}
    seeds = [
        _seed(crossed_to="acme/product#1"),    # a theme names it -> product
        _seed(crossed_to="acme/unlisted#2"),   # NO theme names it -> factory, despite not being
                                                # literally "yellow-robots/factory"
    ]
    r = kpi.product_factory_ratio(seeds, parsed_strategy=parsed_strategy)
    assert r == {"product": 1, "factory": 1, "ratio": 1.0}


def test_product_factory_ratio_falls_back_to_the_factory_repo_constant_without_a_parsed_strategy():
    """The SAME seeds classified the OLD way (I5's stated fallback) when no parsed strategy is
    available at all: `acme/unlisted` is product (not literally the factory), the literal factory
    repo is factory."""
    seeds = [
        _seed(crossed_to="acme/unlisted#2"),
        _seed(crossed_to="yellow-robots/factory#3"),
    ]
    r = kpi.product_factory_ratio(seeds, parsed_strategy=None, factory_repo="yellow-robots/factory")
    assert r == {"product": 1, "factory": 1, "ratio": 1.0}


# ============ deploy lag: the YR-DEPLOY trail ============

def test_deploy_lag_hours_measures_time_to_the_next_deploy_at_or_after_merge():
    merges = ["2026-09-01T00:00:00Z", "2026-09-05T00:00:00Z"]
    deploys = ["2026-09-02T00:00:00Z", "2026-09-10T00:00:00Z"]
    r = kpi.deploy_lag_hours(merges, deploys)
    assert r["count"] == 2
    assert r["pending"] == 0
    assert r["mean_hours"] == 72.0   # (24 + 120) / 2


def test_deploy_lag_hours_marks_a_merge_with_no_later_deploy_as_pending_never_dropped():
    merges = ["2026-09-01T00:00:00Z", "2026-09-20T00:00:00Z"]
    deploys = ["2026-09-02T00:00:00Z"]
    r = kpi.deploy_lag_hours(merges, deploys)
    assert r["count"] == 1
    assert r["pending"] == 1


def test_deploy_records_timed_counts_only_well_formed_records():
    """I4, #475 fold review round 1: well-formedness is judged through tools/drift.py's own shared
    `parse_deploy_records` (surface + commit required) — a comment merely MENTIONING the marker
    without those fields is never counted as a real record."""
    rows = [
        ("2026-09-01T00:00:00Z", "YR-DEPLOY: no fields here\n"),
        ("2026-09-02T00:00:00Z",
         "YR-DEPLOY:\nsurface: dev-runner\ncommit: 1111111111111111111111111111111111111111\nwho: x\n"),
    ]
    assert kpi.deploy_records_timed(rows) == ["2026-09-02T00:00:00Z"]


# ============ the combined report + against-targets ============

def test_compute_report_reports_every_acceptance_criterion_metric():
    report = kpi.compute_report(_full_inputs(), period="2026-09")
    assert report["period"] == "2026-09"
    for key in ("velocity", "cycle_time", "blocked", "repair", "revert", "spend_usd",
               "backlog_age", "inflow_outflow", "product_factory_ratio", "deploy_lag"):
        assert key in report


def test_against_targets_only_pairs_metrics_the_strategy_doc_names():
    report = kpi.compute_report(_full_inputs(), period="2026-09")
    targets = kpi.against_targets(report, {"velocity_per_week": 5, "an_unrelated_key": 1})
    assert targets["velocity_per_week"] == {"actual": report["velocity"]["per_week"], "target": 5}
    assert "an_unrelated_key" not in targets, "a target key the report never computes is simply never shown"


def test_render_kpi_note_shows_the_period_header_and_actual_vs_target():
    report = kpi.compute_report(_full_inputs(), period="2026-09")
    targets = kpi.against_targets(report, {"velocity_per_week": 3, "spend_usd": 100})
    note = kpi.render_kpi_note(report, targets=targets)
    assert "# KPI — 2026-09" in note
    assert "target: 3" in note
    assert "target: 100" in note


def test_render_kpi_note_carries_frontmatter_so_the_vault_plugin_can_stamp_it():
    """N3, #475 fold review round 1; corrected NEW-2, round 2: `type: note` + `status: active`
    ONLY — documentation-model.md:219's stamping rule forbids hand-stamping `created`/`updated` at
    all ("the vault's update-time plugin stamps both ... supply `created` only to backdate"). Those
    two, alone, still give the plugin something well-formed to modify on the note's first write
    (AGENTS.md: "writes nothing at all when the frontmatter cannot be parsed")."""
    report = kpi.compute_report(_full_inputs(), period="2026-09")
    note = kpi.render_kpi_note(report, targets={})
    assert note.startswith("---\n")
    assert "type: note\n" in note
    assert "status: active\n" in note
    assert "created:" not in note, "hand-stamping created/updated is the vault plugin's job alone"
    assert "updated:" not in note


def test_render_kpi_note_labels_velocity_as_runner_prs_only():
    """N1, #475 fold review round 1: velocity narrows to runner-authored merges (`merged_runner_prs`'s
    own `--search "Produced by dev-runner in:body"` filter) — say so in the note's own line, never
    let a bare "merged" count read as every merge this window."""
    report = kpi.compute_report(_full_inputs(), period="2026-09")
    note = kpi.render_kpi_note(report, targets={})
    assert "runner PRs merged" in note and "attended PRs excluded" in note


def test_render_kpi_note_states_when_cycle_time_and_revert_were_never_read():
    """B1/B2, #475 fold review round 1: a None actual with no reason reads as a blank fact; the
    note must SAY why nothing computed rather than print a bare "None"."""
    inputs = _full_inputs(cycle_events=[], commit_subjects=None)
    report = kpi.compute_report(inputs, period="2026-09")
    note = kpi.render_kpi_note(report, targets={})
    assert "cycle_time_hours**: None — no PR merged this window" in note
    assert "revert_rate**: None — --code-root not declared" in note


def test_render_kpi_note_distinguishes_no_linked_issue_from_a_failed_issue_read():
    """B1, #475 fold review round 2: the legibility line must not blur "this PR named no linked
    issue" and "it named one but the read failed" into one bare reason — they are different facts
    about different failure surfaces."""
    events_no_link = [{"created": None, "ready_at": None, "merged": "2026-09-01T00:00:00Z",
                       "link_status": "no_linked_issue"}]
    r = kpi.cycle_time_hours(events_no_link)
    assert r["gap_reason"] == "no merged PR named a linked issue this window"

    events_failed = [{"created": None, "ready_at": None, "merged": "2026-09-01T00:00:00Z",
                      "link_status": "read_failed"}]
    r2 = kpi.cycle_time_hours(events_failed)
    assert r2["gap_reason"] == "the linked issue's own read failed for every merged PR this window"

    events_mixed = events_no_link + events_failed
    r3 = kpi.cycle_time_hours(events_mixed)
    assert r3["gap_reason"] == "1 merged PR(s) named no linked issue, 1 linked-issue read(s) failed"


def test_note_path_names_one_note_per_month_in_the_operations_home():
    assert kpi.note_path("04 projects/acme/operations", "2026-09") == \
        "04 projects/acme/operations/kpi-2026-09.md"
    assert kpi.note_path("04 projects/acme/operations/", "2026-09") == \
        "04 projects/acme/operations/kpi-2026-09.md"


# ============ month bounds ============

def test_month_bounds_end_is_the_exclusive_first_instant_of_next_month():
    start, end = kpi.month_bounds("2026-02")
    assert start == "2026-02-01T00:00:00Z"
    assert end == "2026-03-01T00:00:00Z"


def test_month_bounds_rolls_december_into_next_year():
    start, end = kpi.month_bounds("2026-12")
    assert start == "2026-12-01T00:00:00Z"
    assert end == "2027-01-01T00:00:00Z"


# ============ YR-KPI / YR-STRATEGY records ============

def test_yr_kpi_line_matches_the_registered_grammar():
    reg = records.load()
    marker = records.get(reg, "YR-KPI")["marker"]
    line = kpi.render_yr_kpi_line(who="machinery", period="2026-09")
    assert line.startswith(marker)
    assert "who=machinery" in line and "period=2026-09" in line


def test_yr_strategy_line_matches_the_registered_grammar():
    reg = records.load()
    marker = records.get(reg, "YR-STRATEGY")["marker"]
    line = kpi.render_yr_strategy_line(who="machinery", doc="strategy/note.md")
    assert line.startswith(marker)
    assert "who=machinery" in line and "doc=strategy/note.md" in line


def test_kpi_already_posted_is_idempotent_per_period_only():
    line = kpi.render_yr_kpi_line(who="machinery", period="2026-09")
    assert kpi.kpi_already_posted([line], "2026-09") is True
    assert kpi.kpi_already_posted([line], "2026-10") is False
    assert kpi.kpi_already_posted(["nothing here"], "2026-09") is False


def test_yr_strategy_comment_embeds_the_docs_own_fence_verbatim():
    comment = kpi.render_yr_strategy_comment(who="machinery", doc="strategy/note.md", doc_text=STRATEGY_DOC)
    assert comment.startswith("YR-STRATEGY: who=machinery doc=strategy/note.md")
    assert "```yr-strategy" in comment
    assert 'id = "theme-a"' in comment


def test_yr_strategy_comment_falls_back_to_the_line_alone_when_the_doc_has_no_fence():
    comment = kpi.render_yr_strategy_comment(who="machinery", doc="strategy/note.md", doc_text="# no fence here")
    assert comment == kpi.render_yr_strategy_line(who="machinery", doc="strategy/note.md")


def test_strategy_doc_changed_is_true_on_first_observation_and_false_once_stable(tmp_path):
    """I6, #475 fold review round 1: `strategy_doc_changed` returns `(changed, digest)` and is
    READ-ONLY — the caller persists via `_persist_strategy_hash` itself, separately."""
    state_path = tmp_path / "hash.txt"
    changed1, digest1 = kpi.strategy_doc_changed("doc v1", state_path)
    assert changed1 is True
    kpi._persist_strategy_hash(state_path, digest1)

    changed2, _ = kpi.strategy_doc_changed("doc v1", state_path)
    assert changed2 is False, "no change since the last observation"

    changed3, digest3 = kpi.strategy_doc_changed("doc v2", state_path)
    assert changed3 is True
    kpi._persist_strategy_hash(state_path, digest3)
    changed4, _ = kpi.strategy_doc_changed("doc v2", state_path)
    assert changed4 is False


def test_strategy_doc_changed_never_persists_by_itself(tmp_path):
    """I6, #475 fold review round 1: the OLD shape persisted the new digest as a side effect of the
    same call that decided YR-STRATEGY should post — a transient gh failure on the comment that
    followed still left the digest updated, silently losing the doc's own change forever. Read-only
    now: a repeated call with the SAME text keeps reporting `changed=True` until something else
    calls `_persist_strategy_hash`."""
    state_path = tmp_path / "hash.txt"
    changed1, _ = kpi.strategy_doc_changed("doc v1", state_path)
    assert changed1 is True
    assert not state_path.exists(), "the read alone must never write the state file"
    changed_again, _ = kpi.strategy_doc_changed("doc v1", state_path)
    assert changed_again is True, "still True — nothing has persisted yet"


# ============ the board's own python reader: createdAt + paging beyond 100 ============

def test_board_items_pages_beyond_first_hundred_and_carries_createdat():
    page1_nodes = [_board_node(i) for i in range(100)]
    page2_nodes = [_board_node(i) for i in range(100, 130)]
    calls = []

    def fake_gh(argv):
        calls.append(argv)
        cursor = None
        for i, a in enumerate(argv):
            if a == "-F" and argv[i + 1].startswith("cursor="):
                cursor = argv[i + 1].split("=", 1)[1]
        if cursor is None:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": page1_nodes, "pageInfo": {"hasNextPage": True, "endCursor": "page2"}}}}}}
        assert cursor == "page2"
        return {"data": {"organization": {"projectV2": {"items": {
            "nodes": page2_nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}

    rows = kpi.board_items(fake_gh, "yellow-robots", 1, "yellow-robots/factory")
    assert len(rows) == 130, "items past the first page must not be silently dropped"
    assert {r["number"] for r in rows} == set(range(130))
    assert all(r["createdAt"] for r in rows), "every row must carry createdAt for the backlog-age metric"
    assert sum(1 for c in calls if c[:2] == ["api", "graphql"]) == 2


def test_board_items_filters_closed_and_other_repo_rows():
    nodes = [_board_node(1), _board_node(2, state="CLOSED"), _board_node(3, repo="other/repo")]

    def fake_gh(argv):
        return {"data": {"organization": {"projectV2": {"items": {
            "nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}

    rows = kpi.board_items(fake_gh, "yellow-robots", 1, "yellow-robots/factory")
    assert [r["number"] for r in rows] == [1]


# ============ gather_report_inputs: fixture PR-usage comments, board JSON, timelines ============

def test_gather_report_inputs_reads_every_native_surface(tmp_path, monkeypatch):
    # component_root: the VAULT MIRROR — ideas/ only, git-initialized with its OWN, DIFFERENT commit
    # (B2, #475 fold review round 1: proving revert detection never reads this history).
    component_root = tmp_path / "component"
    _init_component_repo(component_root)
    _commit(component_root, "vault: capture seed-b", "2026-09-04T00:00:00+00:00")

    # code_root: the SEPARATE product code checkout — the ONLY thing revert detection may read.
    code_root = tmp_path / "code"
    _init_component_repo(code_root)
    _commit(code_root, "add feature A", "2026-09-05T00:00:00+00:00")
    _commit(code_root, 'Revert "add feature A"', "2026-09-06T00:00:00+00:00")

    ideas = component_root / "ideas"
    ideas.mkdir()
    (ideas / "seed-a.md").write_text(
        "---\nstatus: open\ncreated: 2026-09-03T00:00:00Z\nupdated: 2026-09-03T00:00:00Z\n"
        'crossed_to: ""\n---\n# A\n')
    (ideas / "seed-b.md").write_text(
        "---\nstatus: go\ncreated: 2026-08-01T00:00:00Z\nupdated: 2026-09-04T00:00:00Z\n"
        "crossed_to: acme/product#9\n---\n# B\n")

    usage_comment = stage_usage.render_summary_comment(stage_usage.build_summary(
        [{"stage": "implement", "model": "claude-sonnet-5", "input_tokens": 1000, "output_tokens": 1000,
          "cache_write_tokens": 0, "cache_read_tokens": 0, "duration_ms": 1000}]))

    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return [{"number": 7, "mergedAt": "2026-09-10T00:00:00Z"}]
        if argv[:2] == ["pr", "view"]:
            # B1, #475 fold review round 2: the REAL pr-view projection (verified live against
            # yellow-robots/factory#431) — id/number/repository/url ONLY, no createdAt anywhere.
            return {"body": "", "comments": [{"body": usage_comment}],
                    "closingIssuesReferences": [
                        {"id": "I_x", "number": 3, "repository": {"name": "factory"},
                         "url": "https://github.com/yellow-robots/factory/issues/3"}]}
        if argv[0] == "api" and argv[1].startswith("repos/"):
            # the SEPARATE REST issue read — snake_case created_at, never the projection above.
            assert argv[1] == "repos/acme/widgets/issues/3"
            return {"number": 3, "created_at": "2026-09-01T00:00:00Z"}
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [_board_node(1, repo="acme/widgets")],
                "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        raise AssertionError(f"unexpected gh call: {argv}")

    monkeypatch.setattr(kpi.sources, "issue_trail_timed",
                        lambda repo, issue: (True, [
                            ("2026-09-11T00:00:00Z",
                             "YR-DEPLOY:\nsurface: dev-runner\n"
                             "commit: 1111111111111111111111111111111111111111\nwho: x\n"),
                        ]))

    inputs = kpi.gather_report_inputs(gh=fake_gh, repo="acme/widgets", org="yellow-robots", project=1,
                                      component_root=str(component_root), code_root=str(code_root),
                                      period="2026-09", now="2026-09-15T00:00:00Z")

    assert inputs["merge_dates"] == ["2026-09-10T00:00:00Z"]
    assert len(inputs["pr_usages"]) == 1 and inputs["pr_usages"][0]["cost_usd"] > 0
    assert inputs["cycle_events"] == [
        {"created": "2026-09-01T00:00:00Z", "ready_at": None, "merged": "2026-09-10T00:00:00Z",
         "link_status": "linked"}]
    assert inputs["commit_subjects"] == ['Revert "add feature A"', "add feature A"], \
        "revert detection must read ONLY code_root — the vault mirror's own commit never appears"
    assert len(inputs["board_rows"]) == 1 and inputs["board_rows"][0]["createdAt"]
    assert {s["path"] for s in inputs["ideas_seeds"]} == {"ideas/seed-a.md", "ideas/seed-b.md"}
    assert inputs["deploy_dates"] == ["2026-09-11T00:00:00Z"]

    report = kpi.compute_report(inputs, period="2026-09")
    assert report["cycle_time"]["mean_total_hours"] is not None
    assert report["revert"] == {"reverts": 1, "total": 2, "rate": 0.5}
    assert report["inflow_outflow"] == {"inflow": 1, "outflow": 1}
    assert report["product_factory_ratio"] == {"product": 1, "factory": 0, "ratio": float("inf")}
    assert report["spend_usd"] > 0


def test_gather_report_inputs_never_reads_createdat_off_the_pr_view_projection(monkeypatch):
    """B1, #475 fold review round 2: `gh pr view --json closingIssuesReferences` is a NARROW
    projection — verified live against a real PR (yellow-robots/factory#431): id/number/repository/
    url ONLY, no `createdAt` anywhere on it. Pins BOTH real shapes so a future edit can't silently
    reintroduce the fabricated-field bug: the pr-view response below carries no createdAt/created_at
    key at all (the honest shape), and `created` can ONLY come from the separate
    `gh api repos/<owner>/<repo>/issues/<n>` REST read (snake_case `created_at`)."""
    calls = []

    def fake_gh(argv):
        calls.append(argv)
        if argv[:2] == ["pr", "list"]:
            return [{"number": 7, "mergedAt": "2026-09-10T00:00:00Z"}]
        if argv[:2] == ["pr", "view"]:
            return {"body": "", "comments": [],
                    "closingIssuesReferences": [
                        {"id": "I_x", "number": 3, "repository": {"name": "factory"},
                         "url": "https://github.com/yellow-robots/factory/issues/3"}]}
        if argv[0] == "api" and argv[1].startswith("repos/"):
            return {"number": 3, "created_at": "2026-09-01T00:00:00Z"}
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        raise AssertionError(f"unexpected gh call: {argv}")

    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (False, "unreachable"))
    inputs = kpi.gather_report_inputs(gh=fake_gh, repo="acme/widgets", org="yellow-robots", project=1,
                                      component_root="/nonexistent", period="2026-09",
                                      now="2026-09-15T00:00:00Z")

    assert inputs["cycle_events"][0]["created"] == "2026-09-01T00:00:00Z"
    assert inputs["cycle_events"][0]["link_status"] == "linked"

    pr_view_calls = [c for c in calls if c[:2] == ["pr", "view"]]
    assert pr_view_calls and all("createdAt" not in " ".join(c) for c in pr_view_calls), \
        "pr view must never even ASK for createdAt — this projection never serves it"
    assert any(c[0] == "api" and c[1].startswith("repos/") for c in calls), \
        "createdAt must come from the separate issues REST read, never the pr-view projection"


def test_gather_report_inputs_distinguishes_no_link_from_a_failed_issue_read(monkeypatch):
    """B1, #475 fold review round 2: a PR with NO closingIssuesReferences entry gets
    `link_status: no_linked_issue`; a PR whose linked issue exists but whose REST read fails gets
    `link_status: read_failed` — two different facts, never collapsed into the same bare `None`."""
    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return [{"number": 7, "mergedAt": "2026-09-10T00:00:00Z"},
                    {"number": 8, "mergedAt": "2026-09-11T00:00:00Z"}]
        if argv[:2] == ["pr", "view"] and argv[2] == "7":
            return {"body": "", "comments": [], "closingIssuesReferences": []}
        if argv[:2] == ["pr", "view"] and argv[2] == "8":
            return {"body": "", "comments": [],
                    "closingIssuesReferences": [{"number": 9}]}
        if argv[0] == "api" and argv[1].startswith("repos/"):
            raise RuntimeError("gh api failed (stub)")
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        raise AssertionError(f"unexpected gh call: {argv}")

    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (False, "unreachable"))
    inputs = kpi.gather_report_inputs(gh=fake_gh, repo="acme/widgets", org="yellow-robots", project=1,
                                      component_root="/nonexistent", period="2026-09",
                                      now="2026-09-15T00:00:00Z")
    by_merge = {e["merged"]: e for e in inputs["cycle_events"]}
    assert by_merge["2026-09-10T00:00:00Z"]["link_status"] == "no_linked_issue"
    assert by_merge["2026-09-10T00:00:00Z"]["created"] is None
    assert by_merge["2026-09-11T00:00:00Z"]["link_status"] == "read_failed"
    assert by_merge["2026-09-11T00:00:00Z"]["created"] is None


def test_gather_report_inputs_commit_subjects_is_none_when_code_root_is_not_declared(tmp_path, monkeypatch):
    """B2, #475 fold review round 1: `--code-root` absent -> `commit_subjects` is `None` (fail-
    closed), never a silently-empty `[]` that reads as "declared, zero reverts"."""
    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (False, "unreachable"))

    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return []
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        raise AssertionError(f"unexpected gh call: {argv}")

    inputs = kpi.gather_report_inputs(gh=fake_gh, repo="acme/widgets", org="yellow-robots", project=1,
                                      component_root=str(tmp_path / "component"), period="2026-09",
                                      now="2026-09-15T00:00:00Z")
    assert inputs["commit_subjects"] is None
    assert kpi.revert_rate(inputs["commit_subjects"]) == {"reverts": None, "total": None, "rate": None}


def test_gather_report_inputs_degrades_a_failed_surface_to_empty_never_a_crash(tmp_path, monkeypatch):
    def failing_gh(argv):
        raise RuntimeError("gh is unreachable")

    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (False, "unreachable"))
    inputs = kpi.gather_report_inputs(gh=failing_gh, repo="acme/widgets", org="yellow-robots", project=1,
                                      component_root=str(tmp_path / "nonexistent"), period="2026-09",
                                      now="2026-09-15T00:00:00Z")
    assert inputs["merge_dates"] == []
    assert inputs["board_rows"] == []
    assert inputs["deploy_dates"] == []
    assert inputs["ideas_seeds"] == []


# ============ run_report: writes the note, posts YR-KPI, posts YR-STRATEGY on doc change ============

class FakeVault:
    def __init__(self):
        self.writes = []

    def write(self, path, content):
        self.writes.append((path, content))


def test_run_report_writes_the_note_posts_yr_kpi_and_is_idempotent_per_period(tmp_path, monkeypatch):
    monkeypatch.setattr(kpi, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (True, []))

    trail = []   # the KPI issue's own trail: what sources.issue_trail("acme/widgets", "55") reports back
    posted = []  # every body this run_report call posted, this call only (cleared between calls)

    monkeypatch.setattr(kpi.sources, "issue_trail", lambda repo, issue: (True, list(trail)))

    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return []
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        if argv[:2] == ["issue", "comment"]:
            body = argv[argv.index("--body") + 1]
            posted.append(body)
            trail.append(body)
            return ""
        raise AssertionError(f"unexpected gh call: {argv}")

    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text(STRATEGY_DOC)
    component_root = tmp_path / "component"
    component_root.mkdir()
    vault = FakeVault()

    def _run():
        return kpi.run_report(
            gh=fake_gh, vault=vault, repo="acme/widgets", issue="55", org="yellow-robots", project=1,
            component_root=str(component_root), strategy_doc=str(strategy_doc),
            operations_home="04 projects/acme/operations", who="machinery", period="2026-09")

    result = _run()
    assert result == {"period": "2026-09", "wrote_note": True, "posted_kpi": True, "posted_strategy": True,
                      "kpi_post_failed": False, "strategy_post_failed": False}
    assert len(vault.writes) == 1
    path, content = vault.writes[0]
    assert path == "04 projects/acme/operations/kpi-2026-09.md"
    assert "# KPI — 2026-09" in content
    assert "YR-KPI: who=machinery period=2026-09" in content
    assert any("YR-KPI: who=machinery period=2026-09" in p for p in posted)
    assert any(p.startswith("YR-STRATEGY: who=machinery") for p in posted), \
        "the first run has no stored hash yet — the doc counts as changed"

    # same period, same doc: the note regenerates but nothing re-posts
    posted.clear()
    result2 = _run()
    assert result2["posted_kpi"] is False
    assert result2["posted_strategy"] is False
    assert posted == []
    assert len(vault.writes) == 2, "the vault note itself is regenerated every run regardless"

    # the doc changes: YR-STRATEGY posts again; YR-KPI stays idempotent for this period
    strategy_doc.write_text(STRATEGY_DOC.replace("velocity_per_week = 5", "velocity_per_week = 9"))
    posted.clear()
    result3 = _run()
    assert result3["posted_strategy"] is True
    assert result3["posted_kpi"] is False


def test_run_report_refuses_to_post_yr_kpi_when_the_trail_is_unreadable(tmp_path, monkeypatch):
    """N5, #475 fold review round 1: the OLD shape failed OPEN (`already = False` whenever the
    trail read failed), risking a DUPLICATE YR-KPI post. Fail CLOSED instead — refuse to post at
    all when idempotence can't be verified, naming why, never a silent duplicate risk."""
    monkeypatch.setattr(kpi, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (True, []))
    monkeypatch.setattr(kpi.sources, "issue_trail", lambda repo, issue: (False, "trail unreachable"))

    posted = []

    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return []
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        if argv[:2] == ["issue", "comment"]:
            posted.append(argv[argv.index("--body") + 1])
            return ""
        raise AssertionError(f"unexpected gh call: {argv}")

    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("# no fence here")
    component_root = tmp_path / "component"
    component_root.mkdir()
    vault = FakeVault()

    result = kpi.run_report(
        gh=fake_gh, vault=vault, repo="acme/widgets", issue="55", org="yellow-robots", project=1,
        component_root=str(component_root), strategy_doc=str(strategy_doc),
        operations_home="04 projects/acme/operations", who="machinery", period="2026-09")

    assert result["posted_kpi"] is False
    assert result["kpi_post_failed"] is True
    assert not any("YR-KPI" in p for p in posted), "an unreadable trail must never risk a duplicate post"
    assert result["wrote_note"] is True, "the note itself still writes — only the post is refused"


def test_run_report_never_persists_the_strategy_digest_when_the_post_fails(tmp_path, monkeypatch):
    """I6, #475 fold review round 1: a failed YR-STRATEGY comment must leave the prior digest in
    place, so the NEXT run still sees the doc as changed and tries again — never silently losing
    the announcement to a transient gh failure."""
    monkeypatch.setattr(kpi, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (True, []))
    monkeypatch.setattr(kpi.sources, "issue_trail", lambda repo, issue: (True, []))

    def flaky_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return []
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        if argv[:2] == ["issue", "comment"]:
            body = argv[argv.index("--body") + 1]
            if body.startswith("YR-STRATEGY"):
                raise RuntimeError("gh issue comment failed (stub)")
            return ""
        raise AssertionError(f"unexpected gh call: {argv}")

    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text(STRATEGY_DOC)
    component_root = tmp_path / "component"
    component_root.mkdir()
    vault = FakeVault()

    def _run():
        return kpi.run_report(
            gh=flaky_gh, vault=vault, repo="acme/widgets", issue="55", org="yellow-robots", project=1,
            component_root=str(component_root), strategy_doc=str(strategy_doc),
            operations_home="04 projects/acme/operations", who="machinery", period="2026-09")

    result1 = _run()
    assert result1["posted_strategy"] is False
    assert result1["strategy_post_failed"] is True

    result2 = _run()
    assert result2["strategy_post_failed"] is True, \
        "the digest never persisted after the failed post — the doc still reads as changed"


# ============ main(): exit code reflects a stated failure ============

def test_main_returns_nonzero_when_a_post_is_refused(tmp_path, monkeypatch):
    """NEW-6, #475 fold review round 2: `run_report` turns a failed/refused post into a stated
    `kpi_post_failed`/`strategy_post_failed` result field rather than raising — but a bare `return 0`
    from `main()` would still tell the caller (a shell, a cron wrapper) that the run succeeded."""
    monkeypatch.setattr(kpi, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setattr(kpi.vault_api, "VaultClient", lambda: FakeVault())
    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (True, []))
    # an unreadable trail (N5) refuses the YR-KPI post outright — kpi_post_failed=True.
    monkeypatch.setattr(kpi.sources, "issue_trail", lambda repo, issue: (False, "trail unreachable"))

    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return []
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        if argv[:2] == ["issue", "comment"]:
            return ""
        raise AssertionError(f"unexpected gh call: {argv}")

    monkeypatch.setattr(kpi, "_gh", fake_gh)

    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("# no fence here")
    component_root = tmp_path / "component"
    component_root.mkdir()

    rc = kpi.main(["report", "--repo", "acme/widgets", "--issue", "55", "--project", "1",
                  "--component-root", str(component_root), "--strategy-doc", str(strategy_doc),
                  "--operations-home", "04 projects/acme/operations", "--period", "2026-09"])
    assert rc != 0, "a stated failure must exit non-zero, never a bare success code"


def test_main_returns_zero_when_nothing_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(kpi, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setattr(kpi.vault_api, "VaultClient", lambda: FakeVault())
    monkeypatch.setattr(kpi.sources, "issue_trail_timed", lambda repo, issue: (True, []))
    monkeypatch.setattr(kpi.sources, "issue_trail", lambda repo, issue: (True, []))

    def fake_gh(argv):
        if argv[:2] == ["pr", "list"]:
            return []
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        if argv[:2] == ["issue", "comment"]:
            return ""
        raise AssertionError(f"unexpected gh call: {argv}")

    monkeypatch.setattr(kpi, "_gh", fake_gh)

    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("# no fence here")
    component_root = tmp_path / "component"
    component_root.mkdir()

    rc = kpi.main(["report", "--repo", "acme/widgets", "--issue", "55", "--project", "1",
                  "--component-root", str(component_root), "--strategy-doc", str(strategy_doc),
                  "--operations-home", "04 projects/acme/operations", "--period", "2026-09"])
    assert rc == 0
