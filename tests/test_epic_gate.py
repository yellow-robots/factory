"""Acceptance tests for tools/epic_gate.py — the epic-gate promotion engine (`sweep_epics`).

Stubbed-`gh` style (mirrors test_dev_runner.py / test_dispatch.py): a fake `gh(argv)` callable is
injected. It serves canned board / subIssues / comments JSON for the GraphQL reads and RECORDS every
write (`gh project item-edit` / `gh issue comment`), so each test asserts on the exact edits and comments
the sweep made and their targets — no live `gh`, no network.

Tests are derived from the acceptance criteria (the spec), not the implementation internals. The fake is
STATEFUL: an `item-edit` is applied back onto the canned board/child state, so a genuine second identical
tick sees the world the first tick left behind — that is how idempotency is proven.

Field/option ids are overridden to readable strings (STATUSFIELD / Ready / NeedsInfo …) for legible
assertions; the defaults themselves (reuse of the runner's ids) are asserted separately.
"""
import importlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import epic_gate  # noqa: E402

REPO = "yellow-robots/yellow-robots"

# readable ids injected into the sweep, so assertions read like English
STATUS_FIELD = "STATUSFIELD"
REASON_FIELD = "REASONFIELD"
STATUS_OPT = {"Backlog": "Backlog", "Ready": "Ready", "In Progress": "InProgress",
              "In Review": "InReview", "Done": "Done"}
REASON_OPT = {"Needs-info": "NeedsInfo", "Blocked": "Blocked"}
INV_STATUS = {v: k for k, v in STATUS_OPT.items()}
INV_REASON = {v: k for k, v in REASON_OPT.items()}

VALID_RECORD = "YR-EPIC-APPROVAL\ndesign: [[product-spec/robots]]\nreview: 2026-07-03 APPROVE by human"


# ---- canned-shape builders (the GraphQL node shapes the sweep reads) ----

def _select(name):
    return {"name": name} if name else None


def _item(number, *, item_id, itype, state="OPEN", status=None, reason=None, repo=REPO):
    """A board (projectV2) item node, as BOARD_QUERY returns it."""
    return {
        "id": item_id,
        "content": {
            "number": number,
            "state": state,
            "issueType": _select(itype),
            "repository": {"nameWithOwner": repo},
        },
        "status": _select(status),
        "reason": _select(reason),
    }


def _child(number, *, itype="Task", state="OPEN", pi_id=None, project_number=1,
           status=None, reason=None, repo=REPO):
    """A sub-issue node, as EPIC_QUERY returns it. `pi_id` present => the child is on our board."""
    pis = []
    if pi_id is not None:
        pis.append({
            "id": pi_id,
            "project": {"number": project_number},
            "status": _select(status),
            "reason": _select(reason),
        })
    return {
        "number": number,
        "state": state,
        "issueType": _select(itype),
        "repository": {"nameWithOwner": repo},
        "projectItems": {"nodes": pis},
    }


def _epic_detail(*, comments, children):
    return {
        "comments": {"nodes": [{"body": b} for b in comments]},
        "subIssues": {"nodes": children},
    }


def _flags(argv):
    d, i = {}, 0
    while i < len(argv):
        if argv[i].startswith("--"):
            d[argv[i]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            i += 1
    return d


class FakeGh:
    """Injectable `gh`. Serves board / epic reads from canned JSON, records + applies writes."""

    def __init__(self, board_nodes, epic_details):
        self.board_nodes = board_nodes
        self.epic_details = epic_details
        self.edits = []       # (item_id, field_id, opt)
        self.comments = []    # (repo, number, body)
        self.closes = []      # (repo, number, reason)
        self.edit_argv = []   # raw argv of each item-edit
        self.comment_argv = []
        self.close_argv = []
        self._index = {}      # id -> the mutable node dict it names (board item or child projectItem)
        self._by_number = {}  # issue number -> its board item node (for applying a native close)
        for it in board_nodes:
            if it.get("id"):
                self._index[it["id"]] = it
            content = it.get("content") or {}
            if content.get("number") is not None:
                self._by_number[content["number"]] = it
        for detail in epic_details.values():
            for ch in (detail.get("subIssues") or {}).get("nodes") or []:
                for pi in (ch.get("projectItems") or {}).get("nodes") or []:
                    if pi.get("id"):
                        self._index[pi["id"]] = pi

    def __call__(self, argv):
        argv = list(argv)
        if argv[:2] == ["api", "graphql"]:
            number = None
            for a in argv:
                if a.startswith("number="):
                    number = int(a.split("=", 1)[1])
            if number is not None:                       # per-epic detail read (issue-side)
                detail = self.epic_details.get(number, {})
                return json.dumps({"data": {"repository": {"issue": detail}}})
            return json.dumps({"data": {"organization": {"projectV2": {"items": {"nodes": self.board_nodes}}}}})
        if argv[:2] == ["project", "item-edit"]:
            f = _flags(argv)
            self.edits.append((f["--id"], f["--field-id"], f["--single-select-option-id"]))
            self.edit_argv.append(argv)
            self._apply(f["--id"], f["--field-id"], f["--single-select-option-id"])
            return ""
        if argv[:2] == ["issue", "comment"]:
            f = _flags(argv)
            self.comments.append((f["--repo"], argv[2], f["--body"]))
            self.comment_argv.append(argv)
            return ""
        if argv[:2] == ["issue", "close"]:
            f = _flags(argv)
            number = int(argv[2])
            self.closes.append((f["--repo"], argv[2], f["--reason"]))
            self.close_argv.append(argv)
            self._apply_close(number)
            return ""
        raise AssertionError(f"unexpected gh call: {argv!r}")

    def _apply(self, item_id, field_id, opt):
        node = self._index.get(item_id)
        if node is None:
            return
        if field_id == STATUS_FIELD:
            node["status"] = _select(INV_STATUS.get(opt, opt))
        elif field_id == REASON_FIELD:
            node["reason"] = _select(INV_REASON.get(opt, opt))

    def _apply_close(self, number):
        """A native close flips the board item's issue state to CLOSED, so a later tick's board read no
        longer sees it as an OPEN candidate — this is how the fake proves self-close is idempotent."""
        item = self._by_number.get(number)
        if item is not None:
            item["content"]["state"] = "CLOSED"


def _sweep(fake):
    return epic_gate.sweep_epics(
        gh=fake, org="yellow-robots", project_number=1,
        status_field_id=STATUS_FIELD, reason_field_id=REASON_FIELD,
        status_opt=STATUS_OPT, reason_opt=REASON_OPT,
    )


def _status_ready_edits(fake):
    return [e for e in fake.edits if e[1] == STATUS_FIELD]


def _reason_edits(fake):
    return [e for e in fake.edits if e[1] == REASON_FIELD]


# ============================================================================
# AC1 — happy path: first open Task child promoted, YR-AUTO-PROMOTED on it, no other writes
# ============================================================================

def test_happy_path_promotes_first_open_task_child():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, pi_id="PI-101", status="Backlog"),
                  _child(102, pi_id="PI-102", status="Backlog")],
    )}
    fake = FakeGh(board, epics)
    _sweep(fake)

    # exactly one Status edit: child #101's project item -> Ready
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    # exactly one comment: YR-AUTO-PROMOTED on the child, naming the epic, marked automatic
    assert len(fake.comments) == 1
    repo, number, body = fake.comments[0]
    assert repo == REPO and number == "101"
    assert "YR-AUTO-PROMOTED" in body
    assert "#100" in body
    assert "automatic" in body.lower()
    # #102 (the later child) is untouched — no edit, no comment on it
    assert not any(e[0] == "PI-102" for e in fake.edits)
    assert not any(c[1] == "102" for c in fake.comments)


def test_happy_path_only_sets_status_to_ready():
    """The sweep never sets Status to anything but Ready (promotion) — never claims / opens PRs."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    for _id, field, opt in _status_ready_edits(fake):
        assert opt == "Ready"


# ============================================================================
# AC2 — no valid approval record -> raise Needs-info + comment, promote nothing
# ============================================================================

def _run_missing_record(comments, epic_reason=None):
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", reason=epic_reason)]
    epics = {100: _epic_detail(comments=comments,
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    return fake


def test_absent_record_raises_needs_info_no_promotion():
    fake = _run_missing_record(["just a normal comment, no sentinel"])
    # epic raised to Needs-info + one comment on the epic; no child promoted
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []                 # nothing promoted
    assert not any(e[0] == "PI-101" for e in fake.edits)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert "approval" in epic_comments[0][2].lower()
    assert not any(c[1] == "101" for c in fake.comments)   # no YR-AUTO-PROMOTED


def test_record_missing_design_is_invalid():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\nreview: 2026-07-03 APPROVE by human"])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_record_missing_review_is_invalid():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\ndesign: [[spec]]"])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_record_empty_field_is_invalid():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\ndesign:\nreview: 2026 APPROVE"])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_oneline_record_form_is_valid():
    """The one-line `YR-EPIC-APPROVAL design=… review=…` form is accepted -> promotes (no raise)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=["YR-EPIC-APPROVAL design=[[spec]] review=2026-07-03 APPROVE"],
        children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []                       # not raised


# ============================================================================
# AC3 — a child in flight (Ready / In Progress / In Review) blocks further promotion
# ============================================================================

def _run_with_busy_status(busy_status):
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        # first child already in flight; a promotable Task sits behind it
        children=[_child(101, pi_id="PI-101", status=busy_status),
                  _child(102, pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    return fake


def test_child_ready_blocks_promotion():
    fake = _run_with_busy_status("Ready")
    assert fake.edits == [] and fake.comments == []


def test_child_in_progress_blocks_promotion():
    fake = _run_with_busy_status("In Progress")
    assert fake.edits == [] and fake.comments == []


def test_child_in_review_blocks_promotion():
    fake = _run_with_busy_status("In Review")
    assert fake.edits == [] and fake.comments == []


# ============================================================================
# AC3 (cont.) — a child carrying a Reason of Blocked / Needs-info blocks further promotion
# ============================================================================

def _run_with_busy_reason(busy_reason):
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, pi_id="PI-101", status="Backlog", reason=busy_reason),
                  _child(102, pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    return fake


def test_child_reason_blocked_blocks_promotion():
    fake = _run_with_busy_reason("Blocked")
    assert fake.edits == [] and fake.comments == []


def test_child_reason_needs_info_blocks_promotion():
    fake = _run_with_busy_reason("Needs-info")
    assert fake.edits == [] and fake.comments == []


# ============================================================================
# AC4 — first open child not a Task -> raise, promote nothing, do NOT skip to a later Task
# ============================================================================

def test_first_open_child_not_task_raises_and_does_not_skip():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        # first open child is a Feature (nested decomposition); a real Task sits behind it
        children=[_child(101, itype="Feature", pi_id="PI-101", status="Backlog"),
                  _child(102, itype="Task", pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)

    # epic raised; NO promotion of the later Task #102 (no skip-ahead)
    assert _status_ready_edits(fake) == []
    assert not any(e[0] == "PI-102" for e in fake.edits)
    assert not any(c[1] == "102" for c in fake.comments)
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert "#101" in epic_comments[0][2] and "task" in epic_comments[0][2].lower()


# ============================================================================
# AC5 — automatic promotion applies ONLY to children of a Ready epic; a standalone task is never touched
# ============================================================================

def test_standalone_task_never_touched():
    """A board item that is a Task with no epic parent is never a candidate -> no writes at all."""
    board = [_item(200, item_id="EI-200", itype="Task", status="Backlog")]
    fake = FakeGh(board, {})
    _sweep(fake)
    assert fake.edits == [] and fake.comments == []


def test_standalone_task_untouched_while_epic_promotes():
    """A standalone task sitting on the board next to a Ready epic is never modified by the sweep."""
    board = [
        _item(100, item_id="EI-100", itype="Feature", status="Ready"),
        _item(200, item_id="EI-200", itype="Task", status="Backlog"),   # standalone
    ]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    # only the epic's child is promoted; the standalone item id never appears in any write
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert not any(e[0] == "EI-200" for e in fake.edits)
    assert not any(c[1] == "200" for c in fake.comments)


# ============================================================================
# AC6 — an epic NOT Ready is never acted on; in-flight children left unchanged (cord-pull)
# ============================================================================

def test_epic_not_ready_is_never_acted_on():
    for epic_status in ("Backlog", "In Progress", "Done", None):
        board = [_item(100, item_id="EI-100", itype="Feature", status=epic_status)]
        epics = {100: _epic_detail(
            comments=[VALID_RECORD],
            # has a perfectly promotable child, and an in-flight one — cord-pull leaves both alone
            children=[_child(101, pi_id="PI-101", status="In Progress"),
                      _child(102, pi_id="PI-102", status="Backlog")])}
        fake = FakeGh(board, epics)
        _sweep(fake)
        assert fake.edits == [], f"epic status={epic_status!r} should be untouched"
        assert fake.comments == [], f"epic status={epic_status!r} should be untouched"


# ============================================================================
# AC7 — the sweep never CLEARS a Reason; it only sets Status/Reason and posts comments
# ============================================================================

def test_never_clears_reason_and_proceeds_despite_stale_reason():
    """A Ready epic still carrying a stale Needs-info Reason from an earlier raise, now with a valid
    record + a promotable child: the sweep promotes and does NOT touch (nor clear) the epic's Reason."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", reason="Needs-info")]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    # promotion proceeds (record + line are the checked facts, not the stale epic Reason)
    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits
    # the epic's Reason is never edited (no clear, no re-raise)
    assert not any(e[0] == "EI-100" for e in fake.edits)


# ============================================================================
# AC8 — authoritative reads: Status/Reason from issue-side projectItems; order from native subIssues
# ============================================================================

def test_promotion_order_follows_subissues_not_issue_number():
    """The next child is the first in the epic's native subIssues order, even when that is not the
    lowest issue number — the board has no sub-issue order."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        # subIssues order: #105 BEFORE #101 — promotion must pick #105
        children=[_child(105, pi_id="PI-105", status="Backlog"),
                  _child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-105", STATUS_FIELD, "Ready")]
    assert fake.comments[0][1] == "105"


def test_busy_decision_reads_child_projectitems():
    """The in-flight decision reads each child's own projectItems Status (issue-side authoritative),
    so a child whose projectItem Status is In Progress blocks promotion."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, pi_id="PI-101", status="In Progress")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [] and fake.comments == []


# ============================================================================
# AC (algorithm) — a childless epic is left alone (no promotion, no raise)
# ============================================================================

def test_childless_epic_untouched():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD], children=[])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [] and fake.comments == []


# ============================================================================
# AC9 — reuse of the runner's Projects field/option ids (env-overridable, same defaults) & mechanisms
# ============================================================================

def test_defaults_reuse_runner_ids():
    assert epic_gate.PROJECT_ID == "PVT_kwDOEEAo0M4Ba6Ls"
    assert epic_gate.STATUS_FIELD_ID == "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw"
    assert epic_gate.REASON_FIELD_ID == "PVTSSF_lADOEEAo0M4Ba6LszhVzoxI"
    assert epic_gate.STATUS_OPT == {
        "Backlog": "b863a902", "Ready": "c85eb5c1", "In Progress": "14e415a3",
        "In Review": "da2e6a49", "Done": "e614f531",
    }
    assert epic_gate.REASON_OPT == {"Needs-info": "803a86fb", "Blocked": "fe4d566c"}


def test_field_ids_env_overridable(monkeypatch):
    monkeypatch.setenv("STATUS_FIELD_ID", "OVERRIDE_STATUS")
    monkeypatch.setenv("PROJECT_ID", "OVERRIDE_PROJECT")
    try:
        importlib.reload(epic_gate)
        assert epic_gate.STATUS_FIELD_ID == "OVERRIDE_STATUS"
        assert epic_gate.PROJECT_ID == "OVERRIDE_PROJECT"
    finally:
        monkeypatch.undo()
        importlib.reload(epic_gate)   # restore pristine module for the rest of the suite


def test_writes_use_runner_gh_mechanisms():
    """A promotion edits via `gh project item-edit --id … --project-id … --field-id …
    --single-select-option-id …` and comments via `gh issue comment <n> --repo … --body …`."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)

    edit = fake.edit_argv[0]
    assert edit[:2] == ["project", "item-edit"]
    ef = _flags(edit)
    assert ef["--id"] == "PI-101"
    assert ef["--project-id"] == epic_gate.PROJECT_ID     # uses the runner's project id
    assert ef["--field-id"] == STATUS_FIELD
    assert ef["--single-select-option-id"] == "Ready"

    comment = fake.comment_argv[0]
    assert comment[:3] == ["issue", "comment", "101"]
    cf = _flags(comment)
    assert cf["--repo"] == REPO and cf["--body"]


# ============================================================================
# AC10 — idempotency: a second identical tick produces no duplicate promotion, edit, or raise comment
# ============================================================================

def test_promotion_is_idempotent_across_ticks():
    """Tick 1 promotes #101 (its project item -> Ready). Tick 2 sees #101 now in flight (the fake
    applied the edit) and promotes nothing more — no duplicate edit or comment."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, pi_id="PI-101", status="Backlog"),
                  _child(102, pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)
    assert edits_after_1 == [("PI-101", STATUS_FIELD, "Ready")]

    _sweep(fake)                                            # identical second tick
    assert fake.edits == edits_after_1                      # no new edit
    assert fake.comments == comments_after_1                # no duplicate YR-AUTO-PROMOTED


def test_raise_needs_info_is_idempotent_across_ticks():
    """A missing-record raise sets Needs-info once; the second tick sees the Reason already set and
    does not re-raise (no duplicate edit or comment)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=["no sentinel here"],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)

    _sweep(fake)                                            # identical second tick
    assert fake.edits == edits_after_1                      # no re-raise edit
    assert fake.comments == comments_after_1                # no duplicate raise comment


def test_raise_not_a_task_is_idempotent_across_ticks():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, itype="Feature", pi_id="PI-101", status="Backlog"),
                  _child(102, itype="Task", pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)

    _sweep(fake)                                            # identical second tick
    assert fake.edits == edits_after_1
    assert fake.comments == comments_after_1


# ============================================================================
# Multiple Ready epics interleave — each processed independently, no prioritization
# ============================================================================

# ============================================================================
# AC11 (#16) — a finished Ready epic (no open child left, has had >=1 child) self-closes natively
# ============================================================================

def test_finished_epic_with_completed_child_closes_completed():
    """All children closed, at least one COMPLETED -> the epic closes with reason completed; the sweep
    never edits Status directly (native close->Done automation is trusted to set it)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    fake = FakeGh(board, epics)
    _sweep(fake)

    assert fake.closes == [(REPO, "100", "completed")]
    close = fake.close_argv[0]
    assert close[:3] == ["issue", "close", "100"]
    # the sweep never sets Status=Done itself -- no Status field edit at all
    assert _status_ready_edits(fake) == []
    assert not any(e[0] == "EI-100" for e in fake.edits)
    assert fake.comments == []                              # no promote/raise noise alongside a close


def test_finished_epic_all_not_planned_closes_not_planned():
    """Every child closed as NOT_PLANNED (none COMPLETED) -> the epic closes with reason 'not planned'."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "NOT_PLANNED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    fake = FakeGh(board, epics)
    _sweep(fake)

    assert fake.closes == [(REPO, "100", "not planned")]


def test_childless_epic_never_closes():
    """A childless epic is never 'finished' -> no close (mirrors the existing no-promotion behavior)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD], children=[])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == []


def test_non_ready_epic_with_all_children_closed_never_closes():
    """Cord-pull: an epic not Status=Ready is never a sweep candidate, even if every child is closed."""
    for epic_status in ("Backlog", "In Progress", "Done", None):
        board = [_item(100, item_id="EI-100", itype="Feature", status=epic_status)]
        epics = {100: _epic_detail(
            comments=[VALID_RECORD],
            children=[_child(101, state="CLOSED", pi_id="PI-101")])}
        epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
        fake = FakeGh(board, epics)
        _sweep(fake)
        assert fake.closes == [], f"epic status={epic_status!r} should never self-close"


def test_open_child_remaining_blocks_self_close():
    """One child still OPEN -> no close; the epic instead follows the promotion/wait branch."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="OPEN", pi_id="PI-102", status="Backlog")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == []
    # the open child is instead promoted (business as usual) -- proves self-close is the mutually
    # exclusive "no open child" branch, not a bolt-on check
    assert fake.edits == [("PI-102", STATUS_FIELD, "Ready")]


def test_self_close_is_idempotent_across_ticks():
    """Tick 1 closes the finished epic (the fake flips its board content.state to CLOSED). Tick 2's board
    read no longer sees it OPEN, so it is not a candidate -> no second close call."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, state="CLOSED", pi_id="PI-101")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]

    _sweep(fake)                                             # identical second tick
    assert fake.closes == [(REPO, "100", "completed")]        # no duplicate close


# ============================================================================
# Multiple Ready epics interleave — each processed independently, no prioritization
# ============================================================================

def test_multiple_ready_epics_each_promote_independently():
    board = [
        _item(100, item_id="EI-100", itype="Feature", status="Ready"),
        _item(300, item_id="EI-300", itype="Feature", status="Ready"),
    ]
    epics = {
        100: _epic_detail(comments=[VALID_RECORD],
                          children=[_child(101, pi_id="PI-101", status="Backlog")]),
        300: _epic_detail(comments=[VALID_RECORD],
                          children=[_child(301, pi_id="PI-301", status="Backlog")]),
    }
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits
    assert ("PI-301", STATUS_FIELD, "Ready") in fake.edits
    promoted_children = sorted(c[1] for c in fake.comments)
    assert promoted_children == ["101", "301"]
