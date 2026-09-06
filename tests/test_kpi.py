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
    assert kpi.cycle_time_hours([]) == {"mean_total_hours": None, "mean_queue_hours": None, "count": 0}


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
    state_path = tmp_path / "hash.txt"
    assert kpi.strategy_doc_changed("doc v1", state_path) is True
    assert kpi.strategy_doc_changed("doc v1", state_path) is False, "no change since the last observation"
    assert kpi.strategy_doc_changed("doc v2", state_path) is True


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
    component_root = tmp_path / "component"
    _init_component_repo(component_root)
    _commit(component_root, "add feature A", "2026-09-05T00:00:00+00:00")
    _commit(component_root, 'Revert "add feature A"', "2026-09-06T00:00:00+00:00")

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
            return {"body": "", "comments": [{"body": usage_comment}]}
        if argv[:2] == ["api", "graphql"]:
            return {"data": {"organization": {"projectV2": {"items": {
                "nodes": [_board_node(1, repo="acme/widgets")],
                "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        raise AssertionError(f"unexpected gh call: {argv}")

    monkeypatch.setattr(kpi.sources, "issue_trail_timed",
                        lambda repo, issue: (True, [("2026-09-11T00:00:00Z", "YR-DEPLOY: who=x rel=y\n")]))

    inputs = kpi.gather_report_inputs(gh=fake_gh, repo="acme/widgets", org="yellow-robots", project=1,
                                      component_root=str(component_root), period="2026-09",
                                      now="2026-09-15T00:00:00Z")

    assert inputs["merge_dates"] == ["2026-09-10T00:00:00Z"]
    assert len(inputs["pr_usages"]) == 1 and inputs["pr_usages"][0]["cost_usd"] > 0
    assert inputs["commit_subjects"] == ['Revert "add feature A"', "add feature A"]
    assert len(inputs["board_rows"]) == 1 and inputs["board_rows"][0]["createdAt"]
    assert {s["path"] for s in inputs["ideas_seeds"]} == {"ideas/seed-a.md", "ideas/seed-b.md"}
    assert inputs["deploy_dates"] == ["2026-09-11T00:00:00Z"]

    report = kpi.compute_report(inputs, period="2026-09")
    assert report["revert"] == {"reverts": 1, "total": 2, "rate": 0.5}
    assert report["inflow_outflow"] == {"inflow": 1, "outflow": 1}
    assert report["product_factory_ratio"] == {"product": 1, "factory": 0, "ratio": float("inf")}
    assert report["spend_usd"] > 0


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
    assert result == {"period": "2026-09", "wrote_note": True, "posted_kpi": True, "posted_strategy": True}
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
