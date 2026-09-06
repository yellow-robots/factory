"""Acceptance tests for tools/design_gate.py's it-36 slice F additions (#471) — the architect's arch
review and the activation machinery. Derived from the issue's acceptance criteria, not the
implementation's internals:

  - the architect's verdict grammar (fit/refit/block) and its at-least-one-argued-alternative
    mandate, and the ADR (type `research`, naming *write at ship*) written through a fake vault
    client;
  - activation asks the engine (`process.py transition-check`) first and writes only on exit 0;
  - the independence guard: a review run id equal to the drafting run's own, held in the PM's own
    ledger, fails the check and nothing is written;
  - the triage-license guard: no `go` disposition fails the check;
  - a `block` verdict after one fold returns the draft to the triage issue as a flagged pack line,
    never activated.

Every external (the transition check, the vault client, `gh`) is injected — no live process.py
subprocess, no live vault, no live network. Where the real `VaultClient` is exercised, it runs
against an in-memory fake transport (tests/test_vault_api.py's own style) so the read-back
confirmation is genuinely exercised, not merely assumed.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import design_gate  # noqa: E402
import ledger  # noqa: E402
import vault_api  # noqa: E402


# ============================================================================================
# the arch stage's verdict grammar: VERDICT: fit|refit|block, >=1 ALTERNATIVE: line
# ============================================================================================

def test_parse_verdict_accepts_each_valid_verdict():
    for v in ("fit", "refit", "block"):
        assert design_gate.parse_verdict(f"some findings\nVERDICT: {v}\n") == v


def test_parse_verdict_is_case_insensitive_on_the_value():
    assert design_gate.parse_verdict("VERDICT: FIT\n") == "fit"
    assert design_gate.parse_verdict("VERDICT: Block\n") == "block"


def test_parse_verdict_last_line_anchored_verdict_wins():
    text = "VERDICT: block\nsome more reasoning\nVERDICT: fit\n"
    assert design_gate.parse_verdict(text) == "fit"


def test_parse_verdict_requires_column_zero_no_leading_whitespace():
    # an indented VERDICT: line is not line-anchored — it must not satisfy the grammar.
    text = "  VERDICT: fit\n"
    with pytest.raises(ValueError):
        design_gate.parse_verdict(text)


def test_parse_verdict_raises_on_no_verdict_line():
    with pytest.raises(ValueError):
        design_gate.parse_verdict("just some prose, no verdict at all\n")


def test_parse_verdict_raises_on_unrecognized_verdict_word():
    with pytest.raises(ValueError):
        design_gate.parse_verdict("VERDICT: maybe\n")


def test_parse_alternatives_collects_every_alternative_line_in_order():
    text = "findings\nALTERNATIVE: use a queue instead\nmore text\nALTERNATIVE: use a cron job instead\n"
    assert design_gate.parse_alternatives(text) == [
        "use a queue instead", "use a cron job instead",
    ]


def test_parse_alternatives_returns_empty_list_when_none_present():
    assert design_gate.parse_alternatives("no alternatives named here\n") == []


def test_parse_arch_output_combines_verdict_and_alternatives():
    text = (
        "The abstraction is sound.\n"
        "ALTERNATIVE: a shared base class instead of composition\n"
        "VERDICT: fit\n"
    )
    result = design_gate.parse_arch_output(text)
    assert result["verdict"] == "fit"
    assert result["alternatives"] == ["a shared base class instead of composition"]
    assert result["findings_text"] == text.strip()


def test_parse_arch_output_raises_when_no_alternative_named_even_with_a_valid_verdict():
    # the architect's mandate names AT LEAST ONE argued alternative — a verdict alone is not enough.
    text = "VERDICT: fit\n"
    with pytest.raises(ValueError):
        design_gate.parse_arch_output(text)


def test_parse_arch_output_raises_when_verdict_missing_even_with_alternatives():
    text = "ALTERNATIVE: do it differently\n"
    with pytest.raises(ValueError):
        design_gate.parse_arch_output(text)


# ============================================================================================
# the ADR: type `research`, naming *write at ship*, written through the vault client
# ============================================================================================

def test_render_adr_carries_type_research_and_the_write_at_ship_trigger():
    text = design_gate.render_adr(
        title="Architecture decision — foo", verdict="fit",
        alternatives=["alt one", "alt two"], findings_text="the reasoning",
        today="2026-09-06",
    )
    assert "type: research" in text
    assert "write at ship" in text.lower()
    assert "fit" in text
    assert "alt one" in text and "alt two" in text
    assert "the reasoning" in text


def test_render_adr_records_the_verdict_given():
    text = design_gate.render_adr(title="t", verdict="refit", alternatives=["a"],
                                   findings_text="f", today="2026-09-06")
    assert "refit" in text


class FakeVault:
    """Records every write/patch call — the fake vault client the ADR/activation tests drive, since
    the acceptance criteria's own scope is "write via a fake vault client", not the real transport
    (tests/test_vault_api.py covers the real client's read-back contract)."""

    def __init__(self, *, read_values=None):
        self.writes = []          # (path, content)
        self.patches = []         # (path, key, value)
        self._read_values = dict(read_values or {})

    def write(self, path, content):
        self.writes.append((path, content))
        self._read_values[path] = content
        return content

    def patch_frontmatter(self, path, key, value):
        self.patches.append((path, key, value))
        return self._read_values.get(path, "")

    def read(self, path):
        return self._read_values[path]


def test_write_arch_adr_writes_a_new_file_under_the_architecture_home():
    vault = FakeVault()
    adr_path = design_gate.write_arch_adr(
        vault, architecture_home="components/widget/architecture", slug="2026-09-06-foo-arch-decision",
        title="Architecture decision — foo", verdict="fit", alternatives=["alt one"],
        findings_text="reasoning",
    )
    assert adr_path == "components/widget/architecture/2026-09-06-foo-arch-decision.md"
    assert len(vault.writes) == 1
    written_path, written_content = vault.writes[0]
    assert written_path == adr_path
    assert "type: research" in written_content
    assert "write at ship" in written_content.lower()
    assert "alt one" in written_content


def test_write_arch_adr_strips_a_trailing_slash_on_the_architecture_home():
    vault = FakeVault()
    adr_path = design_gate.write_arch_adr(
        vault, architecture_home="components/widget/architecture/", slug="slug",
        title="t", verdict="fit", alternatives=["a"], findings_text="f",
    )
    assert adr_path == "components/widget/architecture/slug.md"


# ============================================================================================
# activation: the engine decides first; writes only on exit 0; every write read back
# ============================================================================================

def _arch_result(verdict="fit", alternatives=None):
    return {"verdict": verdict, "alternatives": alternatives or ["an argued alternative"],
            "findings_text": "the architect's findings"}


def test_activation_refuses_and_writes_nothing_when_the_transition_check_fails():
    vault = FakeVault()

    def failing_check(path):
        return False, "triage_licensed"

    result = design_gate.activate_draft(
        path="/tmp/draft-final.md", draft_text="the draft body", vault=vault,
        vault_path="iterations/1-foo/01-foo.md", architecture_home="components/widget/architecture",
        adr_slug="slug", adr_title="title", arch_result=_arch_result(), who="yr-pm",
        transition_check=failing_check,
    )
    assert result["activated"] is False
    assert result["reason"] == "triage_licensed"
    assert vault.writes == []
    assert vault.patches == []


def test_activation_writes_adr_draft_and_status_when_the_transition_check_passes():
    vault = FakeVault()

    def passing_check(path):
        return True, ""

    result = design_gate.activate_draft(
        path="/tmp/draft-final.md", draft_text="the draft body", vault=vault,
        vault_path="iterations/1-foo/01-foo.md", architecture_home="components/widget/architecture",
        adr_slug="2026-09-06-foo-arch-decision", adr_title="Architecture decision — foo",
        arch_result=_arch_result(alternatives=["alt one"]), who="yr-pm-bot",
        transition_check=passing_check, accept_date="2026-09-06",
    )
    assert result["activated"] is True
    assert result["adr_path"] == "components/widget/architecture/2026-09-06-foo-arch-decision.md"

    # the ADR write
    assert (result["adr_path"], ) == (vault.writes[0][0],)
    assert "alt one" in vault.writes[0][1]

    # the draft write: original body + a YR-ACCEPT line naming `who` = the App slug
    draft_write_path, draft_write_content = vault.writes[1]
    assert draft_write_path == "iterations/1-foo/01-foo.md"
    assert "the draft body" in draft_write_content
    assert "YR-ACCEPT: who=yr-pm-bot" in draft_write_content
    assert "2026-09-06" in draft_write_content

    # the status flip: frontmatter set, payload is the VALUE (never re-implemented as a raw write)
    assert vault.patches == [("iterations/1-foo/01-foo.md", "status", "active")]


def test_activation_calls_the_transition_check_with_the_draft_path():
    vault = FakeVault()
    seen = {}

    def check(path):
        seen["path"] = path
        return True, ""

    design_gate.activate_draft(
        path="/tmp/some/run-dir/draft-final.md", draft_text="body", vault=vault,
        vault_path="iterations/1-foo/01-foo.md", architecture_home="components/widget/architecture",
        adr_slug="slug", adr_title="title", arch_result=_arch_result(), who="yr-pm",
        transition_check=check,
    )
    assert seen["path"] == "/tmp/some/run-dir/draft-final.md"


def test_activation_defaults_to_asking_process_py_transition_check_by_transition_id():
    # the acceptance criterion's own literal shape: `process.py transition-check
    # design-doc.draft->active(.machinery) --path <doc>`, invoked only when no transition_check is
    # injected — proven here via the module's own constants rather than a live subprocess.
    assert design_gate.ACTIVATION_TRANSITION == "design-doc.draft->active.machinery"
    assert design_gate.PROCESS_PY.name == "process.py"


def test_activation_through_the_real_vault_client_confirms_every_write_via_read_back():
    """The full plumbing (not the fake) — a FakeTransport standing in for the vault app's REST
    surface — proving `activate_draft` really does route writes through a client that reads every
    one back through the file, not merely a client that promises to."""
    class FakeTransport:
        def __init__(self):
            self.store = {}

        def __call__(self, method, url, headers, data):
            path = url.split("/vault/", 1)[1]
            import urllib.parse
            path = urllib.parse.unquote(path)
            if method in ("PUT",):
                self.store[path] = data.decode("utf-8")
                return 200, b""
            if method == "PATCH":
                # the JSON-instruction body mode (it-36 slice H, #473 fold, B1/N7): the whole
                # instruction rides as the PATCH body, never Target-Type/Target headers.
                import textutil
                text = self.store.get(path, "---\n---\n\n")
                meta, body = textutil.split_frontmatter(text)
                instruction = json.loads(data)
                assert instruction["targetType"] == "frontmatter"
                key = instruction["target"]
                value = instruction["value"]
                meta[key] = value
                lines = ["---"] + [f"{k}: {v}" for k, v in meta.items()] + ["---", "", body.lstrip("\n")]
                self.store[path] = "\n".join(lines)
                return 200, b""
            if method == "GET":
                return 200, self.store.get(path, "").encode("utf-8")
            raise AssertionError(method)

    transport = FakeTransport()
    vault = vault_api.VaultClient(api_key="k", base_url="http://127.0.0.1:27123", fetch=transport)

    result = design_gate.activate_draft(
        path="/tmp/draft-final.md", draft_text="body text", vault=vault,
        vault_path="iterations/1-foo/01-foo.md", architecture_home="components/widget/architecture",
        adr_slug="slug", adr_title="title", arch_result=_arch_result(), who="yr-pm",
        transition_check=lambda path: (True, ""), accept_date="2026-09-06",
    )
    assert result["activated"] is True
    assert "body text" in transport.store["iterations/1-foo/01-foo.md"]
    assert "YR-ACCEPT: who=yr-pm" in transport.store["iterations/1-foo/01-foo.md"]
    assert "status: active" in transport.store["iterations/1-foo/01-foo.md"]
    assert "type: research" in transport.store["components/widget/architecture/slug.md"]


def test_activation_raises_vault_unreachable_when_the_vault_refuses_and_writes_nothing_more():
    class RefusingVault:
        def write(self, path, content):
            raise vault_api.VaultUnreachable("refused")

    with pytest.raises(vault_api.VaultUnreachable):
        design_gate.activate_draft(
            path="/tmp/draft-final.md", draft_text="body", vault=RefusingVault(),
            vault_path="iterations/1-foo/01-foo.md", architecture_home="components/widget/architecture",
            adr_slug="slug", adr_title="title", arch_result=_arch_result(), who="yr-pm",
            transition_check=lambda path: (True, ""),
        )


# ============================================================================================
# the independence evaluator: a review run id equal to the drafting run's own fails the check
# ============================================================================================

def _row(run_id, task, stage, kind="design"):
    return {"schema": ledger.ROW_SCHEMA, "kind": kind, "run_id": run_id, "task": task, "stage": stage}


def test_independence_passes_when_review_run_id_differs_from_the_drafting_run():
    rows = [
        _row("design-acme-widgets-100", "acme/widgets#foo", "product"),
        _row("design-review-acme-widgets-200", "acme/widgets#foo", "arch"),
    ]
    assert design_gate.independence("design-review-acme-widgets-200", ledger_rows=rows) is True


def test_independence_fails_when_the_reviewing_run_id_equals_the_drafting_run_id():
    # the pathological case the guard exists to catch: the SAME run id drafted and "reviewed".
    rows = [
        _row("design-acme-widgets-100", "acme/widgets#foo", "product"),
        _row("design-acme-widgets-100", "acme/widgets#foo", "arch"),
    ]
    assert design_gate.independence("design-acme-widgets-100", ledger_rows=rows) is False


def test_independence_unknown_when_reviewing_run_id_has_no_ledger_row_at_all():
    assert design_gate.independence("no-such-run", ledger_rows=[]) is None


def test_independence_unknown_when_drafting_run_row_is_missing():
    rows = [_row("design-review-acme-widgets-200", "acme/widgets#foo", "arch")]
    assert design_gate.independence("design-review-acme-widgets-200", ledger_rows=rows) is None


def test_cli_independence_fails_when_run_ids_are_equal(tmp_path):
    run_dir = tmp_path / "runs" / "design-review-acme-widgets-100"
    run_dir.mkdir(parents=True)
    (run_dir / "review-run-id.txt").write_text("design-acme-widgets-100")
    ledger_dir = tmp_path / "ledger"
    ledger.append_row(str(ledger_dir), _row("design-acme-widgets-100", "acme/widgets#foo", "product"))
    ledger.append_row(str(ledger_dir), _row("design-acme-widgets-100", "acme/widgets#foo", "arch"))

    rc, token = design_gate.cli_independence(str(run_dir / "draft-final.md"), ledger_dir=str(ledger_dir))
    assert rc == 1
    assert token == "independent"


def test_cli_independence_passes_when_run_ids_differ(tmp_path):
    run_dir = tmp_path / "runs" / "design-review-acme-widgets-200"
    run_dir.mkdir(parents=True)
    (run_dir / "review-run-id.txt").write_text("design-review-acme-widgets-200")
    ledger_dir = tmp_path / "ledger"
    ledger.append_row(str(ledger_dir), _row("design-acme-widgets-100", "acme/widgets#foo", "product"))
    ledger.append_row(str(ledger_dir), _row("design-review-acme-widgets-200", "acme/widgets#foo", "arch"))

    rc, token = design_gate.cli_independence(str(run_dir / "draft-final.md"), ledger_dir=str(ledger_dir))
    assert rc == 0
    assert token == ""


def test_cli_independence_fails_when_no_review_run_id_sidecar_present(tmp_path):
    run_dir = tmp_path / "runs" / "no-sidecar"
    run_dir.mkdir(parents=True)
    rc, token = design_gate.cli_independence(str(run_dir / "draft-final.md"), ledger_dir=str(tmp_path / "ledger"))
    assert rc == 1
    assert token == "independent"


# ============================================================================================
# the triage-license evaluator: no `go` disposition (or a non-`go` one) fails the check
# ============================================================================================

def test_triage_license_passes_on_a_go_disposition():
    assert design_gate.triage_license("acme/widgets#foo", dispositions={"foo": "go"}) is True


def test_triage_license_fails_on_park_or_reject():
    assert design_gate.triage_license("acme/widgets#foo", dispositions={"foo": "park"}) is False
    assert design_gate.triage_license("acme/widgets#foo", dispositions={"foo": "reject"}) is False


def test_triage_license_unknown_when_no_record_at_all():
    assert design_gate.triage_license("acme/widgets#foo", dispositions={}) is None


class FakeGhTrail:
    """A minimal fake `gh` serving one repo's `issue view --json body,comments` trail — enough for
    `evaluate()`'s own `_fetch_triage_trail` call, no live network."""

    def __init__(self, trail):
        self.trail = trail   # list of (author_login, body)

    def __call__(self, argv):
        if argv[:2] == ["issue", "view"]:
            return {"body": "", "comments": [{"body": b, "author": {"login": a}} for a, b in self.trail]}
        raise AssertionError(f"unexpected argv {argv}")


def test_evaluate_by_path_passes_when_the_seeds_go_disposition_is_recorded(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/widgets", "triage_issue": 99}]}))
    run_dir = tmp_path / "runs" / "design-review-1"
    run_dir.mkdir(parents=True)
    (run_dir / "task.txt").write_text("acme/widgets#foo")
    gh = FakeGhTrail([("the-owner", "YR-TRIAGE: seed=foo disposition=go who=@the-owner")])

    rc, token = design_gate.evaluate(path=str(run_dir / "draft-final.md"), gh=gh,
                                      config_path=str(config), owner_login="the-owner")
    assert rc == 0
    assert token == ""


def test_evaluate_by_path_fails_when_no_go_disposition_is_recorded(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/widgets", "triage_issue": 99}]}))
    run_dir = tmp_path / "runs" / "design-review-1"
    run_dir.mkdir(parents=True)
    (run_dir / "task.txt").write_text("acme/widgets#foo")
    gh = FakeGhTrail([])   # no triage record at all

    rc, token = design_gate.evaluate(path=str(run_dir / "draft-final.md"), gh=gh,
                                      config_path=str(config), owner_login="the-owner")
    assert rc == 1
    assert token == "triage_licensed"


def test_evaluate_fails_when_the_last_record_reversed_the_go_to_park(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/widgets", "triage_issue": 99}]}))
    run_dir = tmp_path / "runs" / "design-review-1"
    run_dir.mkdir(parents=True)
    (run_dir / "task.txt").write_text("acme/widgets#foo")
    gh = FakeGhTrail([
        ("the-owner", "YR-TRIAGE: seed=foo disposition=go who=@the-owner"),
        ("the-owner", "YR-TRIAGE: seed=foo disposition=park who=@the-owner"),
    ])

    rc, token = design_gate.evaluate(path=str(run_dir / "draft-final.md"), gh=gh,
                                      config_path=str(config), owner_login="the-owner")
    assert rc == 1
    assert token == "triage_licensed"


def test_evaluate_no_scope_at_all_is_a_loud_failure(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": []}))
    rc, token = design_gate.evaluate(path=None, issue=None, config_path=str(config))
    assert rc == 1
    assert token == "no_scope"


def test_evaluate_unconfigured_repo_is_a_loud_failure(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/other", "triage_issue": 1}]}))
    run_dir = tmp_path / "runs" / "design-review-1"
    run_dir.mkdir(parents=True)
    (run_dir / "task.txt").write_text("acme/widgets#foo")
    rc, token = design_gate.evaluate(path=str(run_dir / "draft-final.md"), gh=FakeGhTrail([]),
                                      config_path=str(config))
    assert rc == 1
    assert token == "repo_unconfigured"


# ============================================================================================
# a `block` verdict after one fold: flagged back to the triage issue, never activated
# ============================================================================================

class FakeGhComment:
    def __init__(self):
        self.posted = []

    def __call__(self, argv):
        if argv[:2] == ["issue", "comment"]:
            self.posted.append(argv[argv.index("--body") + 1])
            return ""
        raise AssertionError(f"unexpected argv {argv}")


def test_render_blocked_pack_body_names_the_verdict_and_alternatives():
    body = design_gate.render_blocked_pack_body("foo", "block", ["alt one", "alt two"])
    assert design_gate.BLOCKED_MARKER in body
    assert "seed: foo" in body
    assert "block" in body
    assert "alt one" in body and "alt two" in body
    assert "NOT activated" in body


def test_flag_block_posts_the_blocked_pack_body_to_the_triage_issue():
    gh = FakeGhComment()
    design_gate.flag_block(gh, "acme/widgets", 99, "foo", "block", ["alt one"])
    assert len(gh.posted) == 1
    assert design_gate.BLOCKED_MARKER in gh.posted[0]
    assert "foo" in gh.posted[0]
    assert "alt one" in gh.posted[0]


def test_blocked_pack_body_is_distinguishable_from_the_undecided_pack_marker():
    # the sweep's own reader must never mistake a blocked-and-returned draft for a fresh, undecided
    # seed still awaiting its first triage record: the undecided-pack SENTINEL line match (exact-line
    # equality, textutil.marker_line_matches mode="sentinel") must not fire on the blocked body, even
    # though BLOCKED_MARKER shares PACK_MARKER as a text prefix.
    import textutil
    assert design_gate.BLOCKED_MARKER != design_gate.PACK_MARKER
    body = design_gate.render_blocked_pack_body("foo", "block", ["alt"])
    lines = body.splitlines()
    assert not any(textutil.marker_line_matches(ln, design_gate.PACK_MARKER, mode="sentinel")
                   for ln in lines)
    assert any(textutil.marker_line_matches(ln, design_gate.BLOCKED_MARKER, mode="sentinel")
               for ln in lines)


# ============================================================================================
# the activation target: local component root -> REST-relative vault paths
# ============================================================================================

def test_next_iteration_slug_starts_at_one_when_no_iterations_exist(tmp_path):
    assert design_gate.next_iteration_slug(tmp_path, "foo") == "1-foo"


def test_next_iteration_slug_is_one_past_the_highest_existing_ordinal(tmp_path):
    (tmp_path / "iterations" / "1-bar").mkdir(parents=True)
    (tmp_path / "iterations" / "3-baz").mkdir(parents=True)
    assert design_gate.next_iteration_slug(tmp_path, "foo") == "4-foo"


def test_vault_rel_path_relative_to_the_vault_root(tmp_path):
    root = tmp_path / "vault"
    component = root / "04 projects" / "widget"
    component.mkdir(parents=True)
    rel = design_gate.vault_rel_path(component, vault_root=root)
    assert rel == "04 projects/widget"


def test_resolve_activation_paths_shapes_iteration_and_architecture_home(tmp_path):
    root = tmp_path / "vault"
    component = root / "04 projects" / "widget"
    component.mkdir(parents=True)
    paths = design_gate.resolve_activation_paths(component, "foo", vault_root=root)
    assert paths["vault_path"] == "04 projects/widget/iterations/1-foo/01-foo.md"
    assert paths["architecture_home"] == "04 projects/widget/architecture"


# ============================================================================================
# evaluate(issue=...) — the epic-triage-license scope (it-36 slice G, #472, cold-review B5):
# the epic issue NUMBER is never the seed; the config entry's own `seed` field (written by
# tools/cross.py at filing time, alongside `epic_issue`, via update_pm_config_entry) names it.
# ============================================================================================

def test_evaluate_by_issue_passes_for_a_conformant_seed_keyed_go_record(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [
        {"repo": "acme/widgets", "triage_issue": 99, "epic_issue": 7, "seed": "pm-agent"}]}))
    gh = FakeGhTrail([("the-owner", "YR-TRIAGE: seed=pm-agent disposition=go who=@the-owner")])

    rc, token = design_gate.evaluate(issue="7", gh=gh, config_path=str(config), owner_login="the-owner")
    assert rc == 0
    assert token == ""


def test_evaluate_by_issue_refuses_without_a_seed_keyed_record(tmp_path):
    """The defect the cold review caught: a record keyed by the epic issue NUMBER (`seed=7`) must
    NEVER license the flip — only a record keyed by the real seed stem does."""
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [
        {"repo": "acme/widgets", "triage_issue": 99, "epic_issue": 7, "seed": "pm-agent"}]}))
    gh = FakeGhTrail([("the-owner", "YR-TRIAGE: seed=7 disposition=go who=@the-owner")])

    rc, token = design_gate.evaluate(issue="7", gh=gh, config_path=str(config), owner_login="the-owner")
    assert rc == 1
    assert token == "triage_licensed"


def test_evaluate_by_issue_refuses_with_no_record_at_all(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [
        {"repo": "acme/widgets", "triage_issue": 99, "epic_issue": 7, "seed": "pm-agent"}]}))
    rc, token = design_gate.evaluate(issue="7", gh=FakeGhTrail([]), config_path=str(config),
                                     owner_login="the-owner")
    assert rc == 1
    assert token == "triage_licensed"


def test_evaluate_by_issue_refuses_when_the_epic_issue_is_not_yet_configured(tmp_path):
    """Before `tools/cross.py` writes `epic_issue` back (the epic didn't exist until it filed it),
    the lookup by issue number finds nothing — fails closed, never a traceback."""
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/widgets", "triage_issue": 99}]}))
    rc, token = design_gate.evaluate(issue="7", gh=FakeGhTrail([]), config_path=str(config))
    assert rc == 1
    assert token == "repo_unconfigured"


def test_evaluate_by_issue_refuses_when_the_entry_has_no_seed_at_all(tmp_path):
    """`epic_issue` matched but `seed` was never written (a malformed config) — fails closed rather
    than matching an empty-string seed against an equally-empty disposition key."""
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [
        {"repo": "acme/widgets", "triage_issue": 99, "epic_issue": 7}]}))
    gh = FakeGhTrail([("the-owner", "YR-TRIAGE: seed= disposition=go who=@the-owner")])
    rc, token = design_gate.evaluate(issue="7", gh=gh, config_path=str(config), owner_login="the-owner")
    assert rc == 1
    assert token == "triage_licensed"


def test_evaluate_by_path_behaviour_is_untouched_by_the_issue_scope_fix(tmp_path):
    """Byte-identical regression: the --path scope never reads `seed`/`epic_issue` at all — it keeps
    deriving the seed from the drafting run's own task.txt sidecar."""
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/widgets", "triage_issue": 99}]}))
    run_dir = tmp_path / "runs" / "design-review-1"
    run_dir.mkdir(parents=True)
    (run_dir / "task.txt").write_text("acme/widgets#foo")
    gh = FakeGhTrail([("the-owner", "YR-TRIAGE: seed=foo disposition=go who=@the-owner")])
    rc, token = design_gate.evaluate(path=str(run_dir / "draft-final.md"), gh=gh,
                                     config_path=str(config), owner_login="the-owner")
    assert rc == 0
    assert token == ""


# ============================================================================================
# update_pm_config_entry: the crossing's own write-back — epic_issue/seed onto the repo's entry
# ============================================================================================

def test_update_pm_config_entry_creates_the_file_and_entry_when_absent(tmp_path):
    config = tmp_path / "pm-repos.json"
    design_gate.update_pm_config_entry(str(config), repo="acme/widgets", epic_issue=7, seed="pm-agent")
    data = json.loads(config.read_text())
    assert data["repos"] == [{"repo": "acme/widgets", "epic_issue": 7, "seed": "pm-agent"}]


def test_update_pm_config_entry_merges_onto_an_existing_entry_without_disturbing_others(tmp_path):
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [
        {"repo": "acme/widgets", "triage_issue": 99},
        {"repo": "acme/other", "triage_issue": 5, "epic_issue": 3, "seed": "other-seed"},
    ]}))
    design_gate.update_pm_config_entry(str(config), repo="acme/widgets", epic_issue=7, seed="pm-agent")
    data = json.loads(config.read_text())
    widgets = next(e for e in data["repos"] if e["repo"] == "acme/widgets")
    other = next(e for e in data["repos"] if e["repo"] == "acme/other")
    assert widgets == {"repo": "acme/widgets", "triage_issue": 99, "epic_issue": 7, "seed": "pm-agent"}
    assert other == {"repo": "acme/other", "triage_issue": 5, "epic_issue": 3, "seed": "other-seed"}


def test_update_pm_config_entry_is_reflected_by_a_later_evaluate_by_issue_call(tmp_path):
    """End to end: cross's own write-back is exactly what makes the evaluator resolvable afterward."""
    config = tmp_path / "pm-repos.json"
    config.write_text(json.dumps({"repos": [{"repo": "acme/widgets", "triage_issue": 99}]}))
    design_gate.update_pm_config_entry(str(config), repo="acme/widgets", epic_issue=7, seed="pm-agent")
    gh = FakeGhTrail([("the-owner", "YR-TRIAGE: seed=pm-agent disposition=go who=@the-owner")])
    rc, token = design_gate.evaluate(issue="7", gh=gh, config_path=str(config), owner_login="the-owner")
    assert rc == 0
    assert token == ""
