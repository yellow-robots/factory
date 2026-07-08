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
import datetime
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


def _status_select(name, updated_at=None):
    """A Status field-value node, optionally carrying `updatedAt` (the stranded-claim clock read)."""
    if not name:
        return None
    node = {"name": name}
    if updated_at is not None:
        node["updatedAt"] = updated_at
    return node


def _child(number, *, itype="Task", state="OPEN", pi_id=None, project_number=1,
           status=None, reason=None, repo=REPO, updated_at=None):
    """A sub-issue node, as EPIC_QUERY returns it. `pi_id` present => the child is on our board.
    `updated_at` sets the Status field value's `updatedAt` (when the claim's age is measured from)."""
    pis = []
    if pi_id is not None:
        pis.append({
            "id": pi_id,
            "project": {"number": project_number},
            "status": _status_select(status, updated_at),
            "reason": _select(reason),
        })
    return {
        "number": number,
        "state": state,
        "issueType": _select(itype),
        "repository": {"nameWithOwner": repo},
        "projectItems": {"nodes": pis},
    }


def _epic_detail(*, comments, children, body=""):
    return {
        "body": body,
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
    """Injectable `gh`. Serves board / epic reads from canned JSON, records + applies writes.

    `open_prs` is a flat list of open PRs' `headRefName` (across all repos — tests use a single repo, so
    no per-repo bucketing is needed) — served for `gh pr list --repo … --state open …`, the stranded-claim
    check's "no open task/<n>-… PR" read."""

    def __init__(self, board_nodes, epic_details, open_prs=None):
        self.board_nodes = board_nodes
        self.epic_details = epic_details
        self.open_prs = list(open_prs or [])
        self.edits = []       # (item_id, field_id, opt)
        self.comments = []    # (repo, number, body)
        self.closes = []      # (repo, number, reason)
        self.edit_argv = []   # raw argv of each item-edit
        self.comment_argv = []
        self.close_argv = []
        self.pr_list_argv = []
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
            self._apply_comment(int(argv[2]), f["--body"])
            return ""
        if argv[:2] == ["issue", "close"]:
            f = _flags(argv)
            number = int(argv[2])
            self.closes.append((f["--repo"], argv[2], f["--reason"]))
            self.close_argv.append(argv)
            self._apply_close(number)
            return ""
        if argv[:2] == ["pr", "list"]:
            self.pr_list_argv.append(argv)
            return json.dumps([{"number": i, "headRefName": b} for i, b in enumerate(self.open_prs)])
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

    def _apply_comment(self, number, body):
        """A posted comment is fed back onto that issue's own canned detail (when it has one), so a later
        tick's per-issue comments read sees it — this is how the fake proves a comment-marker idempotency
        check (e.g. the debt-epic hold comment) across ticks."""
        detail = self.epic_details.get(number)
        if detail is not None:
            detail.setdefault("comments", {"nodes": []})["nodes"].append({"body": body})


def _sweep(fake, *, now=None, build_lock_held=None, stranded_after_min=None):
    """Run one sweep against `fake`. `now`/`build_lock_held`/`stranded_after_min`, left unset, fall back
    to the module's real defaults — fine for every test that never puts a child in the stranded-claim
    check's path (no `updatedAt` on its Status field value short-circuits before either is called)."""
    kwargs = dict(
        gh=fake, org="yellow-robots", project_number=1,
        status_field_id=STATUS_FIELD, reason_field_id=REASON_FIELD,
        status_opt=STATUS_OPT, reason_opt=REASON_OPT,
    )
    if now is not None:
        kwargs["now"] = now
    if build_lock_held is not None:
        kwargs["build_lock_held"] = build_lock_held
    if stranded_after_min is not None:
        kwargs["stranded_after_min"] = stranded_after_min
    return epic_gate.sweep_epics(**kwargs)


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
# #89 — a debt epic (body carries `YR-ITERATION-KIND: tech-debt`) holds its close for a ledger verdict
# ============================================================================

DEBT_BODY = "Some epic description.\n\nYR-ITERATION-KIND: tech-debt\n\nMore prose."

VALID_LEDGER = (
    "YR-DEBT-LEDGER\n"
    "items: 3\n"
    "net-lines: -412\n"
    "files-removed: 2\n"
    "deps-removed: 1\n"
    "pins-added: 0\n"
    "suite-duration: 4m12s\n"
    "incidents: none"
)


def _debt_epic_detail(*, comments, epic_reason=None):
    """A finished epic (both children closed, one COMPLETED) with a debt-kind body — the shape every
    hold/close-verdict test starts from."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", reason=epic_reason)]
    epics = {100: _epic_detail(
        comments=comments, body=DEBT_BODY,
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    return board, epics


def test_finished_non_debt_epic_closes_byte_for_byte_as_today():
    """No debt-kind line in the body -> today's close, unchanged."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD], body="",
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]
    assert fake.comments == []
    assert actions == [{"epic": 100, "action": "close", "reason": "completed"}]


def test_body_mentioning_kind_sentinel_inline_is_not_a_debt_epic():
    """A backticked/prose mention inside a longer line never matches the exact-line test -> closes as
    a normal (non-debt) epic, not held."""
    body = "See the `YR-ITERATION-KIND: tech-debt` sentinel grammar for details on debt epics."
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD], body=body,
        children=[_child(101, state="CLOSED", pi_id="PI-101")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]
    assert fake.comments == []


def test_debt_epic_with_no_verdict_holds_instead_of_closing():
    board, epics = _debt_epic_detail(comments=[])
    fake = FakeGh(board, epics)
    actions = _sweep(fake)

    assert fake.closes == []                                # never closed
    assert actions == [{"epic": 100, "action": "hold"}]
    # hold comment posted on the epic, opening with the marker on its own line
    assert len(fake.comments) == 1
    repo, number, comment_body = fake.comments[0]
    assert repo == REPO and number == "100"
    lines = comment_body.splitlines()
    assert lines[0] == "YR-DEBT-HOLD"
    assert "YR-DEBT-LEDGER" in comment_body
    for field in ("items", "net-lines", "files-removed", "deps-removed", "pins-added",
                  "suite-duration", "incidents"):
        assert field in comment_body
    assert "items:" in comment_body and "net-lines:" in comment_body
    low = comment_body.lower()
    assert "next sweep" in low and "self-close" in low
    assert "clear" in low and "reason" in low
    # Reason set to Needs-info
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits


def test_debt_epic_hold_comment_and_reason_set_exactly_once_across_two_ticks():
    board, epics = _debt_epic_detail(comments=[])
    fake = FakeGh(board, epics)
    _sweep(fake)
    hold_comments_after_1 = [c for c in fake.comments if c[1] == "100"]
    reason_edits_after_1 = _reason_edits(fake)
    assert len(hold_comments_after_1) == 1
    assert reason_edits_after_1 == [("EI-100", REASON_FIELD, "NeedsInfo")]

    _sweep(fake)                                             # identical second tick
    assert [c for c in fake.comments if c[1] == "100"] == hold_comments_after_1   # no duplicate
    assert _reason_edits(fake) == reason_edits_after_1                           # no re-set
    assert fake.closes == []                                                     # never closed


def test_stale_needs_info_reason_does_not_suppress_the_hold_comment():
    """The epic already carries Needs-info (e.g. left over from an earlier approval raise while children
    were still open). Idempotency is judged by the HOLD marker comment, not the Reason -> the hold comment
    still posts; the Reason edit is skipped only because it's already set to the right value."""
    board, epics = _debt_epic_detail(comments=[], epic_reason="Needs-info")
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert actions == [{"epic": 100, "action": "hold"}]
    hold_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(hold_comments) == 1
    assert "YR-DEBT-HOLD" in hold_comments[0][2]
    assert fake.closes == []
    # Reason was already Needs-info -> no edit needed/made
    assert _reason_edits(fake) == []


def test_ledger_marker_mentioned_midline_is_not_a_verdict():
    body = "Per YR-DEBT-LEDGER items: 3 net-lines: -100 we're done here."
    board, epics = _debt_epic_detail(comments=[body])
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == []
    assert any(c[1] == "100" and "YR-DEBT-HOLD" in c[2] for c in fake.comments)


def test_ledger_marker_line_without_both_fields_is_not_a_verdict():
    for comment in (
        "YR-DEBT-LEDGER\nitems: 3\n",                    # missing net-lines
        "YR-DEBT-LEDGER\nnet-lines: -50\n",              # missing items
        "YR-DEBT-LEDGER\nitems:\nnet-lines: -50\n",      # empty items
        "YR-DEBT-LEDGER\n",                              # marker alone
    ):
        board, epics = _debt_epic_detail(comments=[comment])
        fake = FakeGh(board, epics)
        _sweep(fake)
        assert fake.closes == [], f"comment={comment!r} should not count as a verdict"


def test_ledger_marker_and_fields_split_across_two_comments_is_not_a_verdict():
    """The marker line and the two machine-checked fields must land in the SAME comment -- a marker-only
    comment plus a separate comment that happens to carry `items:`/`net-lines:` text does not add up to a
    verdict."""
    marker_only = "YR-DEBT-LEDGER\n"
    fields_elsewhere = "Unrelated note: items: 3, net-lines: -50"
    board, epics = _debt_epic_detail(comments=[marker_only, fields_elsewhere])
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == []
    assert actions == [{"epic": 100, "action": "hold"}]


def test_debt_epic_with_valid_verdict_closes_exactly_as_today():
    board, epics = _debt_epic_detail(comments=[VALID_LEDGER])
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]
    assert actions == [{"epic": 100, "action": "close", "reason": "completed"}]
    # no hold comment, no Reason edit -- closes exactly like the non-debt path
    assert not any(c[1] == "100" and "YR-DEBT-HOLD" in c[2] for c in fake.comments)
    assert _reason_edits(fake) == []


def test_hold_action_shape_and_main_print(capsys, monkeypatch):
    board, epics = _debt_epic_detail(comments=[])
    fake = FakeGh(board, epics)
    monkeypatch.setattr(epic_gate, "_gh", fake)
    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "epic-gate: held epic #100" in out
    assert "ledger" in out.lower()


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


# ============================================================================
# AC12 (#17) — stranded-claim detection: an In-Progress child with no Reason, no live build, and no PR,
# left unchanged past the staleness bound, is raised (Reason=Blocked + comment) so it stops the epic line.
# ============================================================================

FIXED_NOW = datetime.datetime(2026, 7, 4, 12, 0, 0)


def _now():
    """Fixed `now` clock injected into the sweep, so a child's claim age is deterministic."""
    return FIXED_NOW


def _iso(minutes_ago):
    """A GraphQL DateTime scalar `minutes_ago` minutes before the fixed `_now()`."""
    return (FIXED_NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lock_free():
    return False


def _lock_held():
    return True


def _run_stranded_candidate(*, age_min, reason=None, open_prs=None, build_lock_held=_lock_free,
                            stranded_after_min=None, second_child=True):
    """One Ready epic; its first open child is In Progress with the given age/Reason/PR state. A second
    open Task child sits behind it (so a wrongly-promoted #102 would be visible)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    children = [_child(101, pi_id="PI-101", status="In Progress", reason=reason, updated_at=_iso(age_min))]
    if second_child:
        children.append(_child(102, pi_id="PI-102", status="Backlog"))
    epics = {100: _epic_detail(comments=[VALID_RECORD], children=children)}
    fake = FakeGh(board, epics, open_prs=open_prs)
    _sweep(fake, now=_now, build_lock_held=build_lock_held, stranded_after_min=stranded_after_min)
    return fake


def test_stranded_claim_raised_past_bound_no_pr_lock_free():
    """In Progress, no Reason, no PR, age > 45min (default bound), lock free -> Reason=Blocked + comment,
    and the epic line is held (no promotion of the later child #102)."""
    fake = _run_stranded_candidate(age_min=60)

    assert ("PI-101", REASON_FIELD, "Blocked") in fake.edits
    comments = [c for c in fake.comments if c[1] == "101"]
    assert len(comments) == 1
    body = comments[0][2].lower()
    assert "stranded" in body
    assert "60" in comments[0][2]                  # the age is reported in the comment
    assert "no live build" in body
    assert "dispatch.md" in body

    # holds the line: the second open Task child is never promoted while #101 is off-track
    assert not any(e[0] == "PI-102" for e in fake.edits)
    assert not any(c[1] == "102" for c in fake.comments)


def test_no_raise_while_build_lock_held():
    """A build is live (lock held) -> the sweep defers, even though the claim looks stale."""
    fake = _run_stranded_candidate(age_min=60, build_lock_held=_lock_held)
    assert fake.edits == [] and fake.comments == []


def test_no_raise_under_staleness_bound():
    """Age under the (default 45 min) bound -> not yet suspect, no raise."""
    fake = _run_stranded_candidate(age_min=20)
    assert fake.edits == [] and fake.comments == []


def test_no_raise_exactly_at_bound():
    """"Longer than the bound" is strict: exactly 45 minutes does not raise."""
    fake = _run_stranded_candidate(age_min=45)
    assert fake.edits == [] and fake.comments == []


def test_no_raise_when_child_already_carries_reason():
    """A child already carrying an off-track Reason (runner-Blocked, or an earlier Needs-info) is already
    off-track -> never double-raised by the stranded check."""
    for existing_reason in ("Blocked", "Needs-info"):
        fake = _run_stranded_candidate(age_min=60, reason=existing_reason)
        assert fake.edits == [], f"reason={existing_reason!r} should not be touched"
        assert fake.comments == [], f"reason={existing_reason!r} should not be touched"


def test_no_raise_when_open_pr_exists_for_child():
    """An open `task/101-…` PR exists -> a completed build that only missed the In Review status write;
    do not false-raise it."""
    fake = _run_stranded_candidate(age_min=60, open_prs=["task/101-fix-thing"])
    assert fake.edits == [] and fake.comments == []


def test_pr_for_a_different_child_does_not_suppress_the_raise():
    """The PR check is prefix-matched per child number — an open PR for a *different* task does not mask
    #101's own stranded claim."""
    fake = _run_stranded_candidate(age_min=60, open_prs=["task/999-unrelated"])
    assert ("PI-101", REASON_FIELD, "Blocked") in fake.edits


def test_stranded_after_min_default_is_45():
    assert epic_gate.STRANDED_AFTER_MIN == 45


def test_stranded_after_min_env_overridable(monkeypatch):
    monkeypatch.setenv("STRANDED_AFTER_MIN", "10")
    try:
        importlib.reload(epic_gate)
        assert epic_gate.STRANDED_AFTER_MIN == 10
    finally:
        monkeypatch.undo()
        importlib.reload(epic_gate)   # restore pristine module for the rest of the suite


def test_stranded_after_min_param_overrides_the_default_bound():
    """The sweep's own `stranded_after_min` kwarg (not just the env var) governs the check — a 20 min
    claim is not stale against the 45 min default, but is against an explicit 10 min bound."""
    fake = _run_stranded_candidate(age_min=20, stranded_after_min=10)
    assert ("PI-101", REASON_FIELD, "Blocked") in fake.edits


def test_stranded_raise_never_clears_the_reason_it_sets():
    """The sweep only ever sets Reason=Blocked on the strand — it is never seen clearing any Reason."""
    fake = _run_stranded_candidate(age_min=60)
    reason_edits = [e for e in fake.edits if e[1] == REASON_FIELD]
    assert reason_edits == [("PI-101", REASON_FIELD, "Blocked")]


def test_stranded_raise_is_idempotent_across_ticks():
    """Tick 1 raises #101 (Reason -> Blocked, applied back by the fake). Tick 2 sees #101 already carrying
    Blocked -> no double-raise, no duplicate comment."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, pi_id="PI-101", status="In Progress", updated_at=_iso(60)),
                  _child(102, pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics, open_prs=[])
    _sweep(fake, now=_now, build_lock_held=_lock_free)
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)
    assert ("PI-101", REASON_FIELD, "Blocked") in edits_after_1

    _sweep(fake, now=_now, build_lock_held=_lock_free)                 # identical second tick
    assert fake.edits == edits_after_1                                 # no re-raise edit
    assert fake.comments == comments_after_1                           # no duplicate comment
