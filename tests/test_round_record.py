"""Acceptance tests for tools/round_record.py — the close stage's own records module (it-36 slice H,
#473). Derived from the issue's acceptance criteria, not the module's internals:

  - `YR-ROUND-RECORD`'s four counts compute from fixture trails alone (refusals on the child trails,
    records-demanded on the epic trail, detector-findings over the round's own trails, escalations
    across the round); the `deployed` field parses from a fixture deploy trail — never a ledger read.
  - `YR-CROSSOVER` computes from PR usage with a verdict derived from the strategy doc's own theme
    budget.
  - the close-walk stage's own output grammar (a living-reference section edit by heading, plus
    superseded declarations) parses and applies through an injected vault client — the ONLY vault
    write path, never a filesystem write.
  - no rendered close record spells a mandated field of one of the OTHER two records at column 0 —
    the column-0 rule, pinned directly.

No live network, no live vault, no live gh — every core function here is pure over given texts/dicts;
the CLI's own `gh`/vault wiring is exercised only through the injected seams above it.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_trail    # noqa: E402
import records        # noqa: E402
import round_record   # noqa: E402
import vault_api       # noqa: E402

REG = records.load()


# ---- refusals: the runner's own bounce/block comment prose, child trails only -----------------------

def test_count_refusals_counts_needs_info_and_blocked_comments():
    texts = [
        "dev-runner: bounced to **Needs-info** — missing acceptance criteria. Fix it, then set Status back to Ready.",
        "an ordinary comment",
        "dev-runner: **Blocked** — check failed.",
        "dev-runner: **Blocked** — a second failure on retry.",
    ]
    assert round_record.count_refusals(texts) == 3


def test_count_refusals_zero_on_a_clean_child_trail():
    assert round_record.count_refusals(["a normal comment", "another one"]) == 0


def test_count_refusals_requires_the_prefix_at_the_start_not_a_mid_comment_mention():
    # a comment that only MENTIONS the runner's bounce prose mid-text is never a refusal itself.
    texts = ["earlier the run had said dev-runner: bounced to **Needs-info** — but this comment is not that"]
    assert round_record.count_refusals(texts) == 0


# ---- records-demanded: YR-EPIC-GATE / YR-CLOSE-HOLD raises on the epic trail --------------------------

def test_count_records_demanded_counts_epic_gate_and_close_hold_raises():
    epic_texts = [
        "the epic body",
        "YR-EPIC-GATE: gate-touching\n  commit: abc123\n\nnext open child declares itself gate-touching",
        "YR-EPIC-GATE: not-a-task\n  commit: abc123\n\nan untyped child",
        "YR-CLOSE-HOLD\n  commit: abc123\n\nmissing records",
    ]
    assert round_record.count_records_demanded(epic_texts, REG) == 3


def test_count_records_demanded_zero_with_no_raises():
    assert round_record.count_records_demanded(["just the epic body"], REG) == 0


def test_count_records_demanded_one_comment_matching_two_rows_counts_once():
    # contrived, but the rule under test: one comment, one raise event.
    combo = "YR-EPIC-GATE: not-onboarded\n  commit: abc\n\nYR-CLOSE-HOLD\n  commit: abc\n"
    assert round_record.count_records_demanded([combo], REG) == 1


# ---- escalations: YR-ESCALATION across the round -------------------------------------------------------

def test_count_escalations_counts_across_epic_and_child_texts():
    texts = [
        "YR-ESCALATION: act=park why=external-dependency\n\nparked for review",
        "an ordinary comment",
        "YR-ESCALATION: act=idle why=loop-budget-exhausted\n  spent: $10\n",
    ]
    assert round_record.count_escalations(texts, REG) == 2


def test_count_escalations_zero_with_none_present():
    assert round_record.count_escalations(["nothing here"], REG) == 0


# ---- detector-findings: the close lane's own trail-shape check, over the round's own trails -----------

def test_count_detector_findings_nonzero_when_close_records_absent():
    n = round_record.count_detector_findings(REG, ["epic body, no close records"], {})
    assert n == len(check_trail.check_texts(REG, "close", {"issue-trail": ["epic body, no close records"]}))
    assert n > 0


def test_count_detector_findings_pools_epic_and_child_texts():
    round_rec = round_record.round_record_body(
        refusals=0, records_demanded=0, detector_findings=0, escalations=0, deployed="none", reg=REG)
    ship_walk = round_record.ship_walk_body(who="@human", scope="this epic's slices", reg=REG)
    n = round_record.count_detector_findings(REG, [round_rec], {"acme/widgets#101": [ship_walk]})
    assert n == 0   # both mandated close-lane records present, pooled across epic + child


# ---- deployed: the latest YR-DEPLOY record on #464, parsed the same way drift.py reads it -------------

def test_deployed_field_is_none_with_no_deploy_record():
    assert round_record.deployed_field([]) == "none"


def test_deployed_field_renders_the_latest_well_formed_record():
    deploy_texts = [
        "YR-DEPLOY:\nsurface: dispatch\ncommit: 1111111111111111111111111111111111111111\nwho: @human\nrestart: no\n",
        "YR-DEPLOY:\nsurface: dispatch,dev-runner,epic-gate\ncommit: 2222222222222222222222222222222222222222\nwho: @human\nrestart: yes\n",
    ]
    value = round_record.deployed_field(deploy_texts)
    assert value == "surface=dispatch,dev-runner,epic-gate commit=222222222222 restart=yes"


def test_deployed_field_ignores_a_malformed_record_missing_a_required_grammar_field():
    deploy_texts = ["YR-DEPLOY:\nsurface: dispatch\n"]   # no commit field -> skipped by the shared parser
    assert round_record.deployed_field(deploy_texts) == "none"


# ---- YR-CROSSOVER: PR usage + strategy theme budget -----------------------------------------------------

def test_crossover_verdict_within_budget():
    assert round_record.crossover_verdict(100.0, 500) == "within-budget"


def test_crossover_verdict_over_budget():
    assert round_record.crossover_verdict(600.0, 500) == "over-budget"


def test_crossover_verdict_exactly_at_budget_is_within():
    assert round_record.crossover_verdict(500.0, 500) == "within-budget"


def test_crossover_verdict_no_budget_declared():
    assert round_record.crossover_verdict(100.0, None) == "no-budget-declared"


def test_crossover_from_pr_usages_sums_cost_and_counts_prs():
    pr_usages = {"acme/widgets#10": {"cost_usd": 3.5}, "acme/widgets#11": {"cost_usd": 4.5}}
    result = round_record.crossover_from_pr_usages(pr_usages, 500)
    assert result == {"cost_usd": 8.0, "pr_count": 2, "verdict": "within-budget"}


def test_crossover_from_pr_usages_empty_is_zero_cost_zero_prs():
    result = round_record.crossover_from_pr_usages({}, 500)
    assert result == {"cost_usd": 0, "pr_count": 0, "verdict": "within-budget"}


def test_matching_theme_budget_finds_the_first_theme_naming_the_repo():
    strategy = {"themes": [
        {"id": "t1", "repos": ["acme/other"], "budget_usd": 100},
        {"id": "t2", "repos": ["acme/widgets"], "budget_usd": 500},
    ]}
    assert round_record.matching_theme_budget(strategy, "acme/widgets") == 500


def test_matching_theme_budget_none_when_no_theme_targets_the_repo():
    strategy = {"themes": [{"id": "t1", "repos": ["acme/other"], "budget_usd": 100}]}
    assert round_record.matching_theme_budget(strategy, "acme/widgets") is None


# ---- grammar: every render function satisfies its own registry row -------------------------------------

def test_round_record_body_satisfies_its_own_registry_row():
    row = records.get(REG, "YR-ROUND-RECORD")
    body = round_record.round_record_body(refusals=1, records_demanded=2, detector_findings=0,
                                          escalations=0, deployed="none", reg=REG)
    assert check_trail._marker_present(row, [body])
    assert check_trail._missing_fields(row, [body]) == []


def test_crossover_body_satisfies_its_own_registry_row():
    row = records.get(REG, "YR-CROSSOVER")
    body = round_record.crossover_body(cost_usd=1.23, pr_count=2, budget_usd=500,
                                       verdict="within-budget", who="@human", reg=REG)
    assert check_trail._marker_present(row, [body])
    assert check_trail._missing_fields(row, [body]) == []


def test_crossover_body_with_no_budget_declared_still_satisfies_its_own_row():
    row = records.get(REG, "YR-CROSSOVER")
    body = round_record.crossover_body(cost_usd=1.23, pr_count=2, budget_usd=None,
                                       verdict="no-budget-declared", who="@human", reg=REG)
    assert check_trail._missing_fields(row, [body]) == []


def test_ship_walk_body_satisfies_its_own_registry_row():
    row = records.get(REG, "YR-SHIP-WALK")
    body = round_record.ship_walk_body(who="@human", scope="this epic's slices", reg=REG)
    assert check_trail._marker_present(row, [body])
    assert check_trail._missing_fields(row, [body]) == []


# ---- the column-0 rule, pinned directly: no render function's body ever satisfies one of the -----------
#      OTHER two records' own presence check (acceptance criterion 3) ----------------------------------

_RENDERERS = {
    "YR-ROUND-RECORD": lambda: round_record.round_record_body(
        refusals=3, records_demanded=5, detector_findings=2, escalations=1, deployed="none", reg=REG),
    "YR-CROSSOVER": lambda: round_record.crossover_body(
        cost_usd=12.34, pr_count=3, budget_usd=500, verdict="within-budget", who="@human", reg=REG),
    "YR-SHIP-WALK": lambda: round_record.ship_walk_body(who="@human", scope="this epic's slices", reg=REG),
}


@pytest.mark.parametrize("own_name", sorted(_RENDERERS))
def test_no_render_function_body_satisfies_a_different_records_own_presence_check(own_name):
    body = _RENDERERS[own_name]()
    for other_name, other_render in _RENDERERS.items():
        if other_name == own_name:
            continue
        other_row = records.get(REG, other_name)
        assert not check_trail._marker_present(other_row, [body]), (
            f"{own_name}'s body accidentally satisfies {other_name}'s own marker — "
            "a body must never carry another record's marker at column 0"
        )


def test_each_render_function_body_carries_exactly_one_of_the_three_markers():
    """Each of the three close records rides its OWN separate comment body — never combined — so a
    mandated field can never be misread as belonging to a marker it does not ride under."""
    names = list(_RENDERERS)
    for name in names:
        body = _RENDERERS[name]()
        present = [n for n in names if check_trail._marker_present(records.get(REG, n), [body])]
        assert present == [name]


# ---- the close-walk stage's own output grammar: living-reference section edit + superseded ------------

_SHIP_WALK_OUTPUT = """Some prose from the model, ignored.
===LIVING-REFERENCE===
path: 04 projects/acme/architecture/README.md
heading: ## Build hosts
===CONTENT===
The build host is yr-host. Updated at this round's close.
===END-CONTENT===
===END-LIVING-REFERENCE===
===SUPERSEDED===
04 projects/acme/architecture/old-research.md: 04 projects/acme/architecture/new-research.md
04 projects/acme/architecture/untouched.md: none
===END-SUPERSEDED===
"""


def test_parse_ship_walk_output_extracts_living_reference_and_superseded():
    parsed = round_record.parse_ship_walk_output(_SHIP_WALK_OUTPUT)
    assert parsed["living_reference"] == {
        "path": "04 projects/acme/architecture/README.md",
        "heading_path": ["## Build hosts"],
        "content": "The build host is yr-host. Updated at this round's close.",
    }
    assert parsed["superseded"] == [
        ("04 projects/acme/architecture/old-research.md", "04 projects/acme/architecture/new-research.md"),
    ]


def test_parse_ship_walk_output_supports_nested_headings():
    raw = (
        "===LIVING-REFERENCE===\n"
        "path: p.md\n"
        "heading: ## Parent::### Child\n"
        "===CONTENT===\ntext\n===END-CONTENT===\n"
        "===END-LIVING-REFERENCE===\n"
    )
    parsed = round_record.parse_ship_walk_output(raw)
    assert parsed["living_reference"]["heading_path"] == ["## Parent", "### Child"]


def test_parse_ship_walk_output_with_superseded_only_no_living_reference():
    raw = (
        "===SUPERSEDED===\n"
        "a.md: b.md\n"
        "===END-SUPERSEDED===\n"
    )
    parsed = round_record.parse_ship_walk_output(raw)
    assert parsed["living_reference"] is None
    assert parsed["superseded"] == [("a.md", "b.md")]


def test_parse_ship_walk_output_raises_when_completely_empty():
    with pytest.raises(ValueError):
        round_record.parse_ship_walk_output("just prose, no blocks at all")


def test_parse_ship_walk_output_raises_on_unterminated_living_reference_block():
    raw = "===LIVING-REFERENCE===\npath: p.md\nheading: ## H\n===CONTENT===\ntext\n"
    with pytest.raises(ValueError):
        round_record.parse_ship_walk_output(raw)


def test_parse_ship_walk_output_raises_on_malformed_superseded_line():
    raw = "===SUPERSEDED===\nnot a colon-separated line\n===END-SUPERSEDED===\n"
    with pytest.raises(ValueError):
        round_record.parse_ship_walk_output(raw)


# ---- apply_ship_walk: through an injected vault client, the ONLY vault write path ----------------------

class FakeVault:
    def __init__(self, *, document_map_result=None):
        self.calls = []
        self._document_map_result = document_map_result or {"version": "v1"}

    def document_map(self, path):
        self.calls.append(("document_map", path))
        return self._document_map_result

    def patch_section(self, path, heading_path, content, *, if_match=None, **kw):
        self.calls.append(("patch_section", path, tuple(heading_path), content, if_match))
        return "ok"

    def patch_frontmatter(self, path, key, value):
        self.calls.append(("patch_frontmatter", path, key, value))
        return "ok"


def test_apply_ship_walk_updates_the_living_reference_via_a_heading_targeted_patch():
    parsed = round_record.parse_ship_walk_output(_SHIP_WALK_OUTPUT)
    vault = FakeVault(document_map_result={"version": "v42"})
    result = round_record.apply_ship_walk(vault, parsed)
    assert ("document_map", "04 projects/acme/architecture/README.md") in vault.calls
    assert (
        "patch_section", "04 projects/acme/architecture/README.md", ("## Build hosts",),
        "The build host is yr-host. Updated at this round's close.", "v42",
    ) in vault.calls
    assert result["living_reference"]["path"] == "04 projects/acme/architecture/README.md"


def test_apply_ship_walk_anchors_the_section_edit_to_the_document_map_version_read_first():
    parsed = round_record.parse_ship_walk_output(_SHIP_WALK_OUTPUT)
    vault = FakeVault(document_map_result={"version": "the-token"})
    round_record.apply_ship_walk(vault, parsed)
    doc_map_idx = [i for i, c in enumerate(vault.calls) if c[0] == "document_map"][0]
    patch_idx = [i for i, c in enumerate(vault.calls) if c[0] == "patch_section"][0]
    assert doc_map_idx < patch_idx   # the version is read BEFORE it anchors the edit
    assert vault.calls[patch_idx][-1] == "the-token"


def test_apply_ship_walk_stamps_every_superseded_pair_as_two_frontmatter_writes():
    parsed = round_record.parse_ship_walk_output(_SHIP_WALK_OUTPUT)
    vault = FakeVault()
    result = round_record.apply_ship_walk(vault, parsed)
    assert ("patch_frontmatter", "04 projects/acme/architecture/old-research.md",
           "status", "superseded") in vault.calls
    assert ("patch_frontmatter", "04 projects/acme/architecture/old-research.md",
           "superseded_by", "04 projects/acme/architecture/new-research.md") in vault.calls
    assert result["superseded"] == [
        {"path": "04 projects/acme/architecture/old-research.md",
         "superseded_by": "04 projects/acme/architecture/new-research.md"},
    ]


def test_apply_ship_walk_with_superseded_only_never_touches_document_map_or_patch_section():
    raw = "===SUPERSEDED===\na.md: b.md\n===END-SUPERSEDED===\n"
    parsed = round_record.parse_ship_walk_output(raw)
    vault = FakeVault()
    round_record.apply_ship_walk(vault, parsed)
    assert all(c[0] == "patch_frontmatter" for c in vault.calls)


def test_apply_ship_walk_propagates_vault_unreachable_and_writes_nothing_more():
    class RefusingVault(FakeVault):
        def document_map(self, path):
            raise vault_api.VaultUnreachable("refused")

    parsed = round_record.parse_ship_walk_output(_SHIP_WALK_OUTPUT)
    vault = RefusingVault()
    with pytest.raises(vault_api.VaultUnreachable):
        round_record.apply_ship_walk(vault, parsed)
    assert vault.calls == []   # no superseded stamp attempted after the living-reference edit refused
