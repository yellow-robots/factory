"""The one home for the board's plumbing — tools/board_plumbing.py (issue #388).

Derived from the issue's acceptance criteria (the spec), not the module's internals:

  - "Every board identifier ... is declared in ONE home, with its environment-variable override and its
    default resolved there and nowhere else." → every one of the eleven resolvers here returns its shipped
    default when its env var is unset and its override when set. This file is where the identifier LITERALS
    are asserted, once, against the home — the assertion that migrated off test_epic_gate.py, and the one
    the wall-11 guard (tests/test_board_home_wall.py) leaves standing.
  - "The FIELD WRITE has one implementation, used by all four of today's call sites, including the clear
    variant." → set_field's set and clear argv shapes.
  - "The PER-ISSUE project-item read and its selection rule have one implementation." → select_project_item
    and read_issue_item, including the >1-candidate selection and the present-but-none-matching case.
  - "The spawn-environment allowlist derives its board identifier names from the same home." →
    IDENTIFIER_ENV_NAMES is the single source those names come from.
  - "No new dependencies." → the home imports stdlib only.

The behavioural consequence at each of the real call sites (the runner, the sweep, the three operator
scripts) is pinned separately by tests/test_board_plumbing_pins.py; this file exercises the home's own
surface directly through its injected-`gh` seam, no live `gh`.

Guard-hygiene note: this file asserts the three PVT-prefixed literals, but NEVER on a line that also
carries that identifier's UPPERCASE env-var name — so the wall-11 guard's declaration-line predicate does
not count these behavioural assertions as a second home (see test_board_home_wall.py).

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import ast
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOME = ROOT / "tools" / "board_plumbing.py"
sys.path.insert(0, str(ROOT / "tools"))
import board_plumbing  # noqa: E402

# the eleven board identifier env-var names (the same set the home exports as IDENTIFIER_ENV_NAMES; kept
# here as an independent expectation so a drift in the home's tuple is caught, not mirrored)
BOARD_ENV_NAMES = (
    "PROJECT_NUMBER", "PROJECT_ID", "STATUS_FIELD_ID", "REASON_FIELD_ID",
    "OPT_BACKLOG", "OPT_READY", "OPT_INPROGRESS", "OPT_INREVIEW", "OPT_DONE",
    "OPT_NEEDSINFO", "OPT_BLOCKED",
)


def _flags(argv):
    d, i = {}, 0
    while i < len(argv):
        if isinstance(argv[i], str) and argv[i].startswith("--"):
            d[argv[i]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            i += 1
    return d


def _recording_gh(sink, ret=""):
    def gh(argv):
        sink.append(list(argv))
        return ret
    return gh


# ============================================================================
# The identifiers — default (env unset) and override (env set), resolved in the home and nowhere else.
# The literal is asserted against the home HERE; the uppercase env-var name is kept off every literal line.
# ============================================================================

def test_project_number_default_is_one_and_is_an_int(monkeypatch):
    monkeypatch.delenv("PROJECT_NUMBER", raising=False)
    assert board_plumbing.project_number() == 1
    assert isinstance(board_plumbing.project_number(), int)


def test_project_id_default(monkeypatch):
    monkeypatch.delenv("PROJECT_ID", raising=False)
    assert board_plumbing.project_id() == "PVT_kwDOEEAo0M4Ba6Ls"


def test_status_field_id_default(monkeypatch):
    monkeypatch.delenv("STATUS_FIELD_ID", raising=False)
    assert board_plumbing.status_field_id() == "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw"


def test_reason_field_id_default(monkeypatch):
    monkeypatch.delenv("REASON_FIELD_ID", raising=False)
    assert board_plumbing.reason_field_id() == "PVTSSF_lADOEEAo0M4Ba6LszhVzoxI"


def test_status_opt_defaults(monkeypatch):
    for n in ("OPT_BACKLOG", "OPT_READY", "OPT_INPROGRESS", "OPT_INREVIEW", "OPT_DONE"):
        monkeypatch.delenv(n, raising=False)
    assert board_plumbing.status_opt() == {
        "Backlog": "b863a902", "Ready": "c85eb5c1", "In Progress": "14e415a3",
        "In Review": "da2e6a49", "Done": "e614f531",
    }


def test_reason_opt_defaults(monkeypatch):
    for n in ("OPT_NEEDSINFO", "OPT_BLOCKED"):
        monkeypatch.delenv(n, raising=False)
    assert board_plumbing.reason_opt() == {"Needs-info": "803a86fb", "Blocked": "fe4d566c"}


def test_project_number_env_override(monkeypatch):
    monkeypatch.setenv("PROJECT_NUMBER", "77")
    assert board_plumbing.project_number() == 77


def test_project_id_env_override(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "OVR-PROJECT")
    assert board_plumbing.project_id() == "OVR-PROJECT"


def test_status_field_id_env_override(monkeypatch):
    monkeypatch.setenv("STATUS_FIELD_ID", "OVR-STATUS")
    assert board_plumbing.status_field_id() == "OVR-STATUS"


def test_reason_field_id_env_override(monkeypatch):
    monkeypatch.setenv("REASON_FIELD_ID", "OVR-REASON")
    assert board_plumbing.reason_field_id() == "OVR-REASON"


def test_status_opt_every_option_is_env_overridable(monkeypatch):
    overrides = {"OPT_BACKLOG": "b0", "OPT_READY": "r0", "OPT_INPROGRESS": "p0",
                 "OPT_INREVIEW": "v0", "OPT_DONE": "d0"}
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)
    assert board_plumbing.status_opt() == {
        "Backlog": "b0", "Ready": "r0", "In Progress": "p0", "In Review": "v0", "Done": "d0",
    }


def test_reason_opt_every_option_is_env_overridable(monkeypatch):
    monkeypatch.setenv("OPT_NEEDSINFO", "ni0")
    monkeypatch.setenv("OPT_BLOCKED", "bl0")
    assert board_plumbing.reason_opt() == {"Needs-info": "ni0", "Blocked": "bl0"}


# ============================================================================
# The one field write — the set variant and the clear variant, one implementation.
# ============================================================================

def test_set_field_set_variant_carries_item_project_field_and_option_id(monkeypatch):
    monkeypatch.delenv("PROJECT_ID", raising=False)
    calls = []
    board_plumbing.set_field(_recording_gh(calls), "ITEM-1",
                             board_plumbing.status_field_id(), "OPT-XYZ")
    argv = calls[0]
    assert argv[:2] == ["project", "item-edit"]
    f = _flags(argv)
    assert f["--id"] == "ITEM-1"
    assert f["--project-id"] == board_plumbing.project_id()
    assert f["--field-id"] == board_plumbing.status_field_id()
    assert f["--single-select-option-id"] == "OPT-XYZ"
    assert "--clear" not in argv


def test_set_field_clear_variant_carries_the_clear_flag_not_an_option_id():
    calls = []
    board_plumbing.set_field(_recording_gh(calls), "ITEM-1",
                             board_plumbing.reason_field_id(), None)
    argv = calls[0]
    assert argv[:2] == ["project", "item-edit"]
    f = _flags(argv)
    assert f["--id"] == "ITEM-1"
    assert f["--field-id"] == board_plumbing.reason_field_id()
    assert "--clear" in argv
    assert "--single-select-option-id" not in f


def test_set_field_uses_the_resolved_project_id_so_an_override_flows_through(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "OVR-PROJECT")
    calls = []
    board_plumbing.set_field(_recording_gh(calls), "ITEM-1", "FIELD-1", "OPT-1")
    assert _flags(calls[0])["--project-id"] == "OVR-PROJECT"


# ============================================================================
# The one per-issue read + its selection rule — used by the sweep and the two operator reads.
# ============================================================================

def test_select_project_item_picks_the_node_whose_project_number_matches(monkeypatch):
    monkeypatch.delenv("PROJECT_NUMBER", raising=False)   # default board #1
    nodes = [
        {"id": "WRONG", "project": {"number": 99}},
        {"id": "RIGHT", "project": {"number": 1}},        # not nodes[0] — rules out "just take the first"
    ]
    assert board_plumbing.select_project_item(nodes)["id"] == "RIGHT"


def test_select_project_item_returns_none_when_no_node_matches(monkeypatch):
    monkeypatch.delenv("PROJECT_NUMBER", raising=False)
    assert board_plumbing.select_project_item([{"id": "X", "project": {"number": 99}}]) is None


def test_select_project_item_handles_empty_and_missing_nodes():
    assert board_plumbing.select_project_item([]) is None
    assert board_plumbing.select_project_item(None) is None


def test_select_project_item_respects_the_project_number_override(monkeypatch):
    monkeypatch.setenv("PROJECT_NUMBER", "42")
    nodes = [{"id": "A", "project": {"number": 1}}, {"id": "B", "project": {"number": 42}}]
    assert board_plumbing.select_project_item(nodes)["id"] == "B"


def test_select_project_item_explicit_project_num_beats_the_environment(monkeypatch):
    monkeypatch.setenv("PROJECT_NUMBER", "1")
    nodes = [{"id": "A", "project": {"number": 1}}, {"id": "B", "project": {"number": 7}}]
    assert board_plumbing.select_project_item(nodes, 7)["id"] == "B"


def _issue_response(nodes, *, state="OPEN", itype="Task", wrap_data=True):
    issue = {"state": state, "issueType": ({"name": itype} if itype else None),
             "projectItems": {"nodes": nodes}}
    body = {"repository": {"issue": issue}}
    return json.dumps({"data": body} if wrap_data else body)


def test_read_issue_item_uses_the_graphql_api_read_and_selects_the_matching_node(monkeypatch):
    monkeypatch.delenv("PROJECT_NUMBER", raising=False)
    calls = []
    nodes = [
        {"id": "WRONG", "project": {"number": 99}, "status": {"name": "Backlog"}, "reason": None},
        {"id": "RIGHT", "project": {"number": 1}, "status": {"name": "Ready"},
         "reason": {"name": "Blocked"}},
    ]
    gh = _recording_gh(calls, ret=_issue_response(nodes))
    state, itype, item_id, status, reason = board_plumbing.read_issue_item(gh, "o", "r", "7")
    assert (state, itype, item_id, status, reason) == ("OPEN", "Task", "RIGHT", "Ready", "Blocked")
    # the per-issue read is the `gh api graphql` family — deliberately NOT the runner's `project item-list`
    assert calls[0][:2] == ["api", "graphql"]
    assert not any(c[:2] == ["project", "item-list"] for c in calls)


def test_read_issue_item_missing_item_yields_empty_id_status_and_reason():
    gh = _recording_gh([], ret=_issue_response([]))
    state, itype, item_id, status, reason = board_plumbing.read_issue_item(gh, "o", "r", "7")
    assert (item_id, status, reason) == ("", "", "")
    assert (state, itype) == ("OPEN", "Task")


def test_read_issue_item_accepts_already_parsed_and_unwrapped_payloads():
    """`gh` may hand back a parsed object, and a real `gh api graphql` wraps under a top-level `data` key —
    the reader tolerates both a JSON string and a parsed dict, wrapped or not."""
    nodes = [{"id": "N", "project": {"number": 1}, "status": {"name": "Done"}, "reason": None}]
    parsed = json.loads(_issue_response(nodes))            # dict, wrapped under "data"
    _, _, item_id, status, _ = board_plumbing.read_issue_item(_recording_gh([], ret=parsed), "o", "r", "7")
    assert (item_id, status) == ("N", "Done")
    unwrapped = json.loads(_issue_response(nodes, wrap_data=False))
    _, _, item_id2, status2, _ = board_plumbing.read_issue_item(
        _recording_gh([], ret=unwrapped), "o", "r", "7")
    assert (item_id2, status2) == ("N", "Done")


# ============================================================================
# The `sh-exports` mechanism — the single invocation the shell consumers reach the home through.
# ============================================================================

def _sh_exports(env):
    r = subprocess.run([sys.executable, str(HOME), "sh-exports"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    out = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition("=")
        if v and v[0] == "'" and v[-1] == "'":
            v = v[1:-1]
        out[k] = v
    return out


def test_sh_exports_emits_the_home_resolved_identifiers(monkeypatch):
    # clear any override in BOTH the parent (so the in-process resolver reads the default too) and the
    # subprocess, so the comparison is default-vs-default, never a restated literal
    for name in BOARD_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    env = dict(os.environ)
    got = _sh_exports(env)
    assert got["PROJECT_NUMBER"] == str(board_plumbing.project_number())
    assert got["PROJECT_ID"] == board_plumbing.project_id()
    assert got["STATUS_FIELD_ID"] == board_plumbing.status_field_id()
    assert got["REASON_FIELD_ID"] == board_plumbing.reason_field_id()


def test_sh_exports_honours_env_overrides():
    env = dict(os.environ)
    env.update({"PROJECT_NUMBER": "77", "PROJECT_ID": "OVR-PROJECT",
                "STATUS_FIELD_ID": "OVR-STATUS", "REASON_FIELD_ID": "OVR-REASON"})
    got = _sh_exports(env)
    assert got["PROJECT_NUMBER"] == "77"
    assert got["PROJECT_ID"] == "OVR-PROJECT"
    assert got["STATUS_FIELD_ID"] == "OVR-STATUS"
    assert got["REASON_FIELD_ID"] == "OVR-REASON"


# ============================================================================
# The spawn-allowlist name source, and the no-new-dependencies constraint.
# ============================================================================

def test_identifier_env_names_is_the_single_source_of_the_eleven_names():
    assert tuple(board_plumbing.IDENTIFIER_ENV_NAMES) == BOARD_ENV_NAMES


def test_the_home_imports_stdlib_only_no_new_dependency():
    tree = ast.parse(HOME.read_text(encoding="utf-8"))
    tops = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            tops.add(node.module.split(".")[0])
    third_party = {m for m in tops if m not in sys.stdlib_module_names}
    assert not third_party, (
        f"tools/board_plumbing.py imports non-stdlib module(s) {sorted(third_party)} — the home must add "
        "no new dependency (issue #388)"
    )
