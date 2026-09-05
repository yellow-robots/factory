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
import inspect
import json
import pathlib
import pytest
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import epic_gate  # noqa: E402
import board_plumbing  # noqa: E402  (issue #388: the one home the epic gate now reads its ids from)

REPO = "yellow-robots/yellow-robots"


@pytest.fixture(autouse=True)
def _no_deploy_record_gh_reach(monkeypatch):
    """Structural hermeticity (it-33 slice 6 review, issue #462): `epic_gate.main()` folds
    `drift.deploy_record_findings` into every sweep, which — UNSTUBBED — reaches real
    `gh issue view 464` via `tools/sources.py` (network + auth, and a hang there can absorb
    GH_TIMEOUT per unstubbed `main()` call across this whole file). Autouse so EVERY test here is
    safe by default with zero per-test boilerplate; a test that wants to exercise the real
    integration re-patches `epic_gate.drift.deploy_record_findings` (or
    `epic_gate.drift.sources.issue_trail`) itself, inside its own body, AFTER this fixture has
    already run — the later `monkeypatch.setattr` on the same target simply wins."""
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", lambda repo_root, home: [])


# ============================================================================
# execution-context import (epic #126): production runs epic_gate.py as a bare script
# (tools/dispatch.py spawns `tools/epic_gate.py` directly, stderr routed to DEVNULL) — Python puts the
# script's OWN directory (tools/) at sys.path[0] in that mode, regardless of cwd. `import dispatch`
# (sibling, unprefixed) resolves there; a `tools.`-prefixed import resolves only under pytest's own
# sys.path setup (this file's `sys.path.insert(0, .../tools)` above, plus whatever pytest's rootdir
# insertion adds) and would crash the sweeper silently in production. This test runs in a FRESH
# subprocess (so no module already cached in this process's sys.modules can mask a real failure) with
# cwd deliberately NOT the repo root, and drives the module the same way `python3 tools/epic_gate.py`
# would: script-path execution, main() never invoked (run_name != "__main__", so no real GitHub I/O).
# ============================================================================

def test_epic_gate_resolves_the_sibling_dispatch_import_in_script_execution_context():
    # Faithfully reproduces `python3 tools/epic_gate.py`'s ONE relevant mechanic — sys.path[0] set to the
    # script's own directory, not the repo root — without ever invoking main() (which does real GitHub
    # I/O against the live board): __name__ is set to something other than "__main__", so the
    # `if __name__ == "__main__":` guard at the bottom of the file never fires. Only the module-level
    # `import dispatch` (and everything above it) actually executes.
    target = ROOT / "tools" / "epic_gate.py"
    probe = (
        "import sys\n"
        f"sys.path.insert(0, {str(target.parent)!r})\n"
        f"ns = {{'__name__': 'epic_gate_under_test', '__file__': {str(target)!r}}}\n"
        f"exec(compile(open({str(target)!r}).read(), {str(target)!r}, 'exec'), ns)\n"
        "print('OK:' + ns['dispatch'].repo_lock_path('o/r', lock_home='/x'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tempfile.gettempdir(),   # deliberately not the repo root — proves cwd-independence
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "OK:/x/dispatch-o--r.lock"

# readable ids injected into the sweep, so assertions read like English
STATUS_FIELD = "STATUSFIELD"
REASON_FIELD = "REASONFIELD"
STATUS_OPT = {"Backlog": "Backlog", "Ready": "Ready", "In Progress": "InProgress",
              "In Review": "InReview", "Done": "Done"}
REASON_OPT = {"Needs-info": "NeedsInfo", "Blocked": "Blocked"}
INV_STATUS = {v: k for k, v in STATUS_OPT.items()}
INV_REASON = {v: k for k, v in REASON_OPT.items()}

VALID_RECORD = (
    "YR-EPIC-APPROVAL\ndesign: [[product-spec/robots]]\nreview: 2026-07-03 APPROVE by human\n"
    "who: a human reviewer"
)

# The close-lane mandates, grammar-complete in one comment (it-31 slice 9: a finished non-debt epic
# holds until these exist on its trail — fixtures that expect the self-close carry them). `deployed`
# (it-33 slice 3, epic #455, v1.6.0) joined YR-ROUND-RECORD's fields alongside every other machinery
# record's new `commit` field — this fixture predates both, so it carries `deployed` explicitly.
CLOSE_RECORDS = (
    "YR-ROUND-RECORD: the round's observable counts\n"
    "refusals: 0\nrecords-demanded: 0\ndetector-findings: 0\nescalations: 0\ndeployed: none\n"
    "\n"
    "YR-SHIP-WALK: walked at close\nwho: @human\nscope: this epic's slices\n"
)


# ---- canned-shape builders (the GraphQL node shapes the sweep reads) ----

def _select(name):
    return {"name": name} if name else None


def _item(number, *, item_id, itype, state="OPEN", status=None, reason=None, repo=REPO,
          updated_at=None, parent=None):
    """A board (projectV2) item node, as BOARD_QUERY returns it. `updated_at` sets the Status field
    value's `updatedAt` (the standalone stranded-claim pass reads its clock straight off the board item,
    unlike the per-epic pass which reads a child's own issue-side projectItems). `parent` sets
    `content.parent.number` — GitHub's own sub-issues relationship, present on an epic child, absent
    (null) on a standalone claim, which is exactly how the standalone pass tells the two apart."""
    return {
        "id": item_id,
        "content": {
            "number": number,
            "state": state,
            "issueType": _select(itype),
            "repository": {"nameWithOwner": repo},
            "parent": {"number": parent} if parent is not None else None,
        },
        "status": _status_select(status, updated_at),
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
           status=None, reason=None, repo=REPO, updated_at=None, body=""):
    """A sub-issue node, as EPIC_QUERY returns it. `pi_id` present => the child is on our board.
    `updated_at` sets the Status field value's `updatedAt` (when the claim's age is measured from).
    `body` is the child's OWN issue body (issue #345's EPIC_QUERY addition) — distinct from the epic's
    own body set on `_epic_detail`; defaults to empty so every pre-#345 fixture stays byte-identical."""
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
        "body": body,
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
    check's "no open task/<n>-… PR" read.

    `manifest_repos` (repo -> raw `.yr/factory.toml` text) backs the admission wall's `_repo_has_manifest`
    probe (issue #125) — the SAME contents-API argv shape `_read_manifest_threshold` already reads
    (`FakeDebtGh` below shares this exact stub). `None` (the default) means every repo is onboarded — the
    wall never engages, so every test written before #125 keeps promoting/closing/raising exactly as
    before with no per-test change. A dict makes ONLY its keys onboarded; any other repo's read raises
    (missing = fail-closed), same as a real 404.

    `manifest_errors` (issue #140): repo -> a list of outcomes consumed one per contents-API call to that
    repo, in order — a list entry that's an `Exception` instance is raised, anything else is returned as
    the raw response text. Once only one entry remains, it repeats forever (so a one-element list models a
    persistent failure/success, and a longer list models "fails N times then recovers"). Checked BEFORE
    `manifest_repos`, so a repo can appear in both/either without conflict."""

    def __init__(self, board_nodes, epic_details, open_prs=None, *, manifest_repos=None,
                 manifest_errors=None):
        self.board_nodes = board_nodes
        self.epic_details = epic_details
        self.open_prs = list(open_prs or [])
        self.manifest_repos = manifest_repos
        self.manifest_errors = {k: list(v) for k, v in (manifest_errors or {}).items()}
        self.manifest_argv = []
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
        if argv[0] == "api" and len(argv) > 1 and "contents/.yr/factory.toml" in argv[1]:
            self.manifest_argv.append(argv)
            m = re.match(r"repos/([^/]+)/([^/]+)/contents/", argv[1])
            repo = f"{m.group(1)}/{m.group(2)}"
            if repo in self.manifest_errors:
                queue = self.manifest_errors[repo]
                outcome = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            if self.manifest_repos is None:
                return "# onboarded (default fixture)\n"
            if repo not in self.manifest_repos:
                raise RuntimeError(f"gh api {argv[1]} failed (404): Not Found")
            return self.manifest_repos[repo]
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


def test_promoted_body_carries_the_sweep_own_commit_statement():
    """it-33 slice 3 (epic #455): YR-AUTO-PROMOTED gained `commit` in records.toml's `fields` — the
    body must carry a `commit:` line the LIVE registry's field grammar accepts, indented under the
    marker (never a bare column-0 line — the debt hold's lesson generalized)."""
    import check_trail
    import records as records_mod
    body = epic_gate._promoted_body(100)
    assert body.splitlines()[0] == "YR-AUTO-PROMOTED"
    assert body.splitlines()[1] == f"  {epic_gate.COMMIT_STATEMENT}"
    reg = records_mod.load()
    row = records_mod.get(reg, "YR-AUTO-PROMOTED")
    assert check_trail._missing_fields(row, [body]) == []


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
# Issue #343 — the open-questions gate: an un-dispositioned `YR-OPEN-QUESTION:` marker in the epic
# BODY refuses fail-closed, promotes nothing, and names each marker line. Runs before the approval
# check (below) and after the no-open-children branch (tested further down, alongside the
# self-close/debt-hold fixtures) — a finished epic's decision is unaffected by any marker.
# ============================================================================

def _run_open_question_body(body, comments=None):
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=comments if comments is not None else [VALID_RECORD],
        body=body,
        children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    return fake


def test_marker_at_column_zero_blocks_promotion_and_raises_needs_info():
    body = "Some epic prose.\n\nYR-OPEN-QUESTION: does the retry budget need a cap?\n\nMore prose."
    fake = _run_open_question_body(body)

    # nothing promoted, no child touched at all
    assert _status_ready_edits(fake) == []
    assert not any(e[0] == "PI-101" for e in fake.edits)
    assert not any(c[1] == "101" for c in fake.comments)
    # Reason=Needs-info; Status never touched
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert not any(e[0] == "EI-100" and e[1] == STATUS_FIELD for e in fake.edits)

    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    text = epic_comments[0][2]
    assert epic_gate.OPEN_QUESTIONS_MARKER in text
    assert "line 3" in text
    assert "`YR-OPEN-QUESTION: does the retry budget need a cap?`" in text
    # the refusal never reproduces a found marker at column 0 (would satisfy its own detector)
    assert not any(line.startswith(epic_gate.OPEN_QUESTION_PREFIX) for line in text.splitlines())


def test_two_open_question_markers_both_named():
    body = (
        "Intro line.\n"
        "YR-OPEN-QUESTION: first question here?\n"
        "middle prose\n"
        "YR-OPEN-QUESTION: second question here?\n"
    )
    fake = _run_open_question_body(body)
    assert _status_ready_edits(fake) == []
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    text = epic_comments[0][2]
    assert "line 2" in text and "`YR-OPEN-QUESTION: first question here?`" in text
    assert "line 4" in text and "`YR-OPEN-QUESTION: second question here?`" in text


def test_open_questions_gate_precedes_approval_check_single_refusal():
    """An epic with BOTH an open-question marker and no valid approval record raises exactly once —
    the open-questions refusal — never falling through to also post the missing-approval refusal."""
    body = "YR-OPEN-QUESTION: still open?\n"
    fake = _run_open_question_body(body, comments=[])   # no valid approval either
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_gate.OPEN_QUESTIONS_MARKER in epic_comments[0][2]
    assert epic_gate.NO_APPROVAL_MARKER not in epic_comments[0][2]


def test_open_questions_raise_is_idempotent_across_ticks():
    body = "YR-OPEN-QUESTION: still open?\n"
    fake = _run_open_question_body(body)
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in edits_after_1

    _sweep(fake)                                            # identical second tick
    assert fake.edits == edits_after_1
    assert fake.comments == comments_after_1


def test_removing_last_marker_resumes_promotion_next_tick_no_attended_reset():
    """Tick 1 refuses on the marker. The disposition is rewriting the line off the grammar — nothing
    else. Tick 2 (no attended step beyond that rewrite) resumes promotion; the stale Needs-info Reason
    from tick 1 is never cleared."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD], body="YR-OPEN-QUESTION: still open?\n",
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []
    reason_edits_after_1 = _reason_edits(fake)

    # the disposition: rewrite the marker line off the grammar (an attended body edit) -- nothing else
    epics[100]["body"] = "RESOLVED: no cap needed, default is fine.\n"
    _sweep(fake)                                            # next tick, no other reset

    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits  # promotion resumed
    assert _reason_edits(fake) == reason_edits_after_1       # the stale Reason is never cleared


def test_dispositioned_marker_no_longer_blocks():
    body = "RESOLVED: does the retry budget need a cap? -- no, using the default.\n"
    fake = _run_open_question_body(body)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_ruling_appended_same_line_still_blocks_not_a_disposition():
    """Appending a ruling after the marker on the SAME line still matches -- that is a tempting
    non-disposition, not a second way to disposition. Only rewriting the line off the grammar counts."""
    body = "YR-OPEN-QUESTION: does the retry budget need a cap? RESOLVED: no, default is fine.\n"
    fake = _run_open_question_body(body)
    assert _status_ready_edits(fake) == []
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits


def test_similarly_prefixed_marker_does_not_match():
    """The colon is part of the prefix constant specifically so a plural/longer marker can't match."""
    body = "YR-OPEN-QUESTIONS: a plural form must not match the singular grammar\n"
    fake = _run_open_question_body(body)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_fenced_marker_line_still_fires_indentation_is_the_guarantee_not_fencing():
    """A line-anchored matcher still accepts a FENCED example: a fenced block's content lines sit at
    column 0 same as a real marker. This documents the accepted gap -- it does NOT claim a fenced
    mention is inert (indentation is the guarantee here, fencing is not)."""
    body = "```\nYR-OPEN-QUESTION: still fires even fenced?\n```\n"
    fake = _run_open_question_body(body)
    assert _status_ready_edits(fake) == []
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits


# ---- false positives: prose / inline-backtick / indentation / trail comment never fire ----

def test_prose_mention_is_not_an_open_question():
    body = "We discussed the marker YR-OPEN-QUESTION: should this block? and decided it should not."
    fake = _run_open_question_body(body)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_inline_backticked_mention_is_not_an_open_question():
    body = "See the `YR-OPEN-QUESTION:` grammar in authoring.md for how this gate reads the epic body."
    fake = _run_open_question_body(body)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_one_space_indented_mention_is_not_an_open_question():
    body = " YR-OPEN-QUESTION: does one leading space still count?\n"
    fake = _run_open_question_body(body)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_marker_only_in_a_trail_comment_is_not_an_open_question():
    """The gate scans the epic BODY only -- the trail is deliberately not scanned (the comment read
    is capped at first:100 and unpaginated). A marker sitting only in a comment must never block."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD, "YR-OPEN-QUESTION: does this comment count?"],
        body="Clean epic body, no markers here.",
        children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_technical_rfc_teaching_line_is_not_an_open_question_end_to_end():
    """The technical-rfc template's own worked example -- read from the file, not retyped -- must not
    fire the open-question grammar. It is inert by indentation + inline-backticking, not by content."""
    text = (ROOT / "skills" / "factory" / "templates" / "technical-rfc.md").read_text(encoding="utf-8")
    marker = "END ISSUE BODY"
    idx = text.find(marker)
    assert idx != -1, "templates/technical-rfc.md is missing the 'END ISSUE BODY' marker"
    scaffold = text[idx:]
    teaching_lines = [ln for ln in scaffold.splitlines() if "YR-OPEN-QUESTION:" in ln]
    assert teaching_lines, (
        "templates/technical-rfc.md's scaffold no longer mentions YR-OPEN-QUESTION: -- "
        "update this test's target"
    )
    for line in teaching_lines:
        assert not line.startswith(epic_gate.OPEN_QUESTION_PREFIX), (
            f"templates/technical-rfc.md teaching line fires the open-question grammar: {line!r}"
        )

    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD], body=scaffold,
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]   # promotes normally, no false positive
    assert _reason_edits(fake) == []


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
    """The one-line `YR-EPIC-APPROVAL design=… review=… who=…` form is accepted -> promotes (no
    raise)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=["YR-EPIC-APPROVAL design=[[spec]] review=2026-07-03 APPROVE who=a human reviewer"],
        children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []                       # not raised


# ============================================================================
# Issue #344 — the approval record: line-anchored, and authored.
#
# `_has_valid_approval` must match `YR-EPIC-APPROVAL` only on a line that STARTS the line at column 0
# (a prefix match, no leading-whitespace tolerance) rather than as a substring anywhere in the comment
# body, and must additionally require a non-empty `who` field alongside `design` and `review`. A refusal
# must name which requirement failed, and the gate's own refusal comment must never itself satisfy the
# check it describes.
# ============================================================================

def _epic_comment_text(fake, number=100):
    """The single comment body posted to epic `number` by this sweep -- fails loudly if the sweep
    posted zero or more than one, since every test using this helper expects exactly one refusal."""
    texts = [c[2] for c in fake.comments if c[1] == str(number)]
    assert len(texts) == 1, f"expected exactly one comment on #{number}, got {texts!r}"
    return texts[0]


# ---- the match is line-anchored: a substring anywhere in the comment must not satisfy it ----------------

def test_prose_mention_of_marker_with_bare_field_values_does_not_validate():
    """A prose sentence quoting the marker mid-line, with bare `design:`/`review:`/`who:` values
    elsewhere in the same sentence, must not satisfy the approval check -- a substring match anywhere in
    the comment body is exactly the exploit this issue closes."""
    body = (
        "Note: our YR-EPIC-APPROVAL process requires design: sign-off, review: approval, and "
        "who: attestation before any promotion happens."
    )
    fake = _run_missing_record([body])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_indented_approval_record_does_not_validate():
    """A marker line carrying leading whitespace (e.g. quoted in a reply) must not satisfy the check --
    prefix matching tolerates no leading whitespace, matching the open-question grammar's own rule."""
    record = " YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: 2026-07-03 APPROVE\nwho: a human"
    fake = _run_missing_record([record])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_blockquoted_approval_record_does_not_validate():
    """A blockquoted echo of the marker (e.g. a GitHub '> ' quote-reply) must not satisfy the check --
    every line carries the quote prefix, so none of them starts with the marker at column 0."""
    record = "> YR-EPIC-APPROVAL\n> design: [[spec]]\n> review: 2026-07-03 APPROVE\n> who: a human"
    fake = _run_missing_record([record])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_inline_backticked_marker_mention_does_not_validate():
    """An inline-backticked mention of the marker in prose must not satisfy the check."""
    body = "See the `YR-EPIC-APPROVAL` grammar in authoring.md for the required design/review/who fields."
    fake = _run_missing_record([body])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_marker_prefixed_line_with_only_backticked_field_names_still_refuses():
    """A line that legitimately STARTS with the marker (passing the line-anchor check) but only
    mentions the field names inside backticks, never as real `key: value` / `key=value` assignments,
    must still refuse. `_extract_field`'s word-boundary guard is what keeps a backticked field name
    inert -- this exercises that guard directly rather than assuming it holds, per the issue's own
    residual note."""
    body = "YR-EPIC-APPROVAL requires `design:`, `review:`, and `who:` before it is considered valid."
    fake = _run_missing_record([body])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_fenced_marker_line_still_validates_indentation_is_the_guarantee_not_fencing():
    """Documents the accepted residual named in the issue: a line-anchored matcher is exactly as strong
    as the rest of the file, not unforgeable -- a FENCED example still fires, because a fenced block's
    content lines sit at column 0 same as a real marker."""
    record = "```\nYR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: 2026-07-03 APPROVE\nwho: a human\n```"
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[record],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


# ---- the third field: `who` is required, non-empty, alongside `design` and `review` ---------------------

def test_record_missing_who_is_invalid():
    """A residual two-field record (design + review, no who) -- the pre-#344 shape -- must now refuse."""
    fake = _run_missing_record(["YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: 2026-07-03 APPROVE"])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_record_empty_who_field_is_invalid():
    fake = _run_missing_record(
        ["YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: 2026-07-03 APPROVE\nwho:"])
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert _status_ready_edits(fake) == []


def test_all_three_fields_present_promotes_block_form():
    record = "YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: 2026-07-03 APPROVE\nwho: a human reviewer"
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[record],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_oneline_form_review_value_does_not_absorb_who_key():
    """The one-line form's value cutter must stop `review`'s value at the next `who=` key. Without `who`
    in the cutter's key list, `review` would swallow `who=<value>` whole -- still non-empty, so it would
    wrongly pass -- instead of leaving a genuinely separate, non-empty `who` value."""
    record = "YR-EPIC-APPROVAL design=[[spec]] review=2026-07-03 APPROVE who=a human"
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[record],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []
    assert epic_gate._extract_field(record, "review") == "2026-07-03 APPROVE"
    assert epic_gate._extract_field(record, "who") == "a human"


# ---- the refusal names which requirement failed: absent marker, or which field, distinctly -------------

def test_refusal_names_missing_design_only():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\nreview: 2026-07-03 APPROVE\nwho: a human"])
    text = _epic_comment_text(fake)
    assert "`design`" in text
    assert "`review`" not in text
    assert "`who`" not in text


def test_refusal_names_missing_review_only():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\ndesign: [[spec]]\nwho: a human"])
    text = _epic_comment_text(fake)
    assert "`review`" in text
    assert "`design`" not in text
    assert "`who`" not in text


def test_refusal_names_missing_who_only():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: 2026-07-03 APPROVE"])
    text = _epic_comment_text(fake)
    assert "`who`" in text
    assert "`design`" not in text
    assert "`review`" not in text


def test_refusal_names_multiple_missing_fields():
    fake = _run_missing_record(["YR-EPIC-APPROVAL\ndesign: [[spec]]"])
    text = _epic_comment_text(fake)
    assert "`review`" in text
    assert "`who`" in text
    assert "`design`" not in text


def test_refusal_when_no_marker_found_does_not_falsely_name_a_specific_field():
    """When no comment carries the marker line at all, the refusal must still name the requirement that
    failed -- but it must not falsely claim a specific field is empty/absent, since there is no
    candidate record to inspect fields on in the first place."""
    fake = _run_missing_record(["just a normal comment, no sentinel"])
    text = _epic_comment_text(fake)
    assert "YR-EPIC-APPROVAL" in text
    assert "`design`" not in text
    assert "`review`" not in text
    assert "`who`" not in text


# ---- the gate's own refusal comment must never satisfy the check it describes ----------------------------

def test_refusal_comment_fed_back_as_epic_comment_does_not_satisfy_approval():
    """The gate's own refusal comment -- fed back onto the epic's trail as though a human had quoted it
    in a reply -- must not itself satisfy the approval check it describes. `FakeGh` feeds every posted
    comment back onto the epic's own canned detail, so the second tick genuinely sees the refusal sitting
    on the epic's trail, exactly as a real second sweep would."""
    fake = _run_missing_record(["just a normal comment, no sentinel"])
    assert _status_ready_edits(fake) == []
    refusal_text = _epic_comment_text(fake)
    assert "YR-EPIC-APPROVAL" in refusal_text     # sanity: not a vacuous test

    _sweep(fake)                                  # second tick: the refusal now sits on the epic's trail
    assert _status_ready_edits(fake) == []         # still refuses -- nothing was ever promoted


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
# Issue #345 — the gate-touching declaration: a first-open child whose OWN body carries a line
# beginning `YR-GATE-TOUCHING:` at column 0 with a non-empty reason refuses fail-closed
# (Reason=Blocked on the epic), promoting nothing and touching no child's state. Runs immediately
# after the Type gate (above) and BEFORE the `_pi_node` lookup — a child not yet on the board must
# still refuse. The declaration is read from the CHILD's own body only, never the epic's (whose
# per-task context slices legitimately carry the same prefix describing that very child).
# ============================================================================

GATE_TOUCHING_MARKER = "YR-EPIC-GATE: gate-touching"


def _run_gate_touching(first_child_body, *, second_child_pi="PI-102", epic_body="",
                        comments=None, epic_reason=None):
    """`comments`, when given, are EXTRA comments alongside a valid approval record (never a
    replacement for it) -- this section is about the gate-touching site specifically, so every
    fixture here already clears the approval-record check upstream of it."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", reason=epic_reason)]
    children = [_child(101, pi_id="PI-101", status="Backlog", body=first_child_body)]
    if second_child_pi is not None:
        children.append(_child(102, pi_id=second_child_pi, status="Backlog"))
    epics = {100: _epic_detail(
        comments=[VALID_RECORD] + list(comments if comments is not None else []),
        body=epic_body,
        children=children)}
    fake = FakeGh(board, epics)
    _sweep(fake)
    return fake


def test_gate_touching_declaration_blocks_promotion_and_raises_blocked():
    fake = _run_gate_touching("YR-GATE-TOUCHING: raises check_timeout's default\n")

    # nothing promoted at all -- not #101, not a skip-ahead to #102
    assert _status_ready_edits(fake) == []
    assert not any(e[0] == "PI-101" for e in fake.edits)
    assert not any(e[0] == "PI-102" for e in fake.edits)
    assert not any(c[1] == "101" for c in fake.comments)
    assert not any(c[1] == "102" for c in fake.comments)

    # epic raised to Blocked, exactly one comment on the epic
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    text = epic_comments[0][2]
    assert text.splitlines()[0] == GATE_TOUCHING_MARKER
    assert "#101" in text
    assert "`raises check_timeout's default`" in text          # the reason, backticked
    assert "attended" in text.lower()                            # the rule: gate evolution is attended work
    # the refusal never reproduces the marker at column 0 (would satisfy its own detector)
    assert not any(line.startswith("YR-GATE-TOUCHING:") for line in text.splitlines())


def test_gate_touching_read_only_from_childs_own_body_not_the_epics():
    """The epic BODY legitimately carries `YR-GATE-TOUCHING:` lines inside its per-task context
    slices describing children -- reading declarations from there would false-positive on every
    epic whose slice text names a later child's gate-touching status. The first open child's own
    body carries no declaration here, so promotion proceeds normally."""
    epic_body = (
        "### Slice A -- some task\n"
        "YR-GATE-TOUCHING: this describes a DIFFERENT slice, not child #101\n"
    )
    fake = _run_gate_touching("Ordinary task body, no declaration here.", epic_body=epic_body,
                               second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_fires_even_when_child_not_yet_on_the_board():
    """The check runs BEFORE the `_pi_node` lookup, which early-returns (no writes, no comment) for
    a child not yet on the board. A gate-touching child in exactly that state must still refuse --
    proving the check does not sit downstream of a project item it never reads."""
    fake = _run_gate_touching("YR-GATE-TOUCHING: adds a new lint gate\n", second_child_pi=None)
    # no board item to have edited for #101 (it carries no pi_id) -- but the epic itself still raises
    assert not any(e[0] == "PI-101" for e in fake.edits)
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == GATE_TOUCHING_MARKER


def test_gate_touching_runs_after_the_type_gate_not_a_task_wins():
    """When the first open child is BOTH not-a-Task and carries a gate-touching declaration, the
    Type gate (which runs first) refuses with its own marker -- the gate-touching check never even
    reads that child's body."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, itype="Feature", pi_id="PI-101", status="Backlog",
                          body="YR-GATE-TOUCHING: irrelevant, this child is not even a Task\n"),
                  _child(102, itype="Task", pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == "YR-EPIC-GATE: not-a-task"


# ---- false positives: indentation / inline-backticking / empty reason never fire -------------------

def test_gate_touching_indented_declaration_does_not_fire():
    fake = _run_gate_touching(" YR-GATE-TOUCHING: does one leading space still count?\n",
                               second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_inline_backticked_mention_does_not_fire():
    body = "See the `YR-GATE-TOUCHING:` grammar in authoring.md for how this gate reads a child body."
    fake = _run_gate_touching(body, second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_prose_mention_does_not_fire():
    body = "We discussed a YR-GATE-TOUCHING: line here and decided this slice doesn't need one."
    fake = _run_gate_touching(body, second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_empty_reason_does_not_fire():
    fake = _run_gate_touching("YR-GATE-TOUCHING:\n", second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_whitespace_only_reason_does_not_fire():
    fake = _run_gate_touching("YR-GATE-TOUCHING:    \n", second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_similarly_prefixed_marker_does_not_match():
    body = "YR-GATE-TOUCHING-ISH: a longer prefix must not match the exact grammar\n"
    fake = _run_gate_touching(body, second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert _reason_edits(fake) == []


def test_gate_touching_fenced_declaration_still_fires_indentation_is_the_guarantee_not_fencing():
    """A line-anchored matcher still accepts a FENCED example -- a fenced block's content lines sit
    at column 0 same as a real marker. This documents the accepted gap, same discipline as the
    open-question grammar's own precedent."""
    body = "```\nYR-GATE-TOUCHING: still fires even fenced\n```\n"
    fake = _run_gate_touching(body, second_child_pi=None)
    assert _status_ready_edits(fake) == []
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits


def test_technical_rfc_shipped_slot_fires_nothing_end_to_end():
    """The technical-rfc template's shipped per-task-context slot (read from the file, not
    retyped) must not itself fire the gate-touching grammar when pasted verbatim into a child's
    body -- the mirror of the open-question teaching-line pin."""
    text = (ROOT / "skills" / "factory" / "templates" / "technical-rfc.md").read_text(encoding="utf-8")
    start = text.find("### Slice A")
    end = text.find("### Slice B")
    assert start != -1 and end != -1 and start < end, (
        "templates/technical-rfc.md is missing its 'Slice A' / 'Slice B' per-task context markers"
    )
    slot = text[start:end]
    assert "YR-GATE-TOUCHING" in slot, (
        "templates/technical-rfc.md's Slice A scaffold no longer mentions YR-GATE-TOUCHING -- "
        "update this test's target"
    )
    assert not any(line.startswith("YR-GATE-TOUCHING:") for line in slot.splitlines()), (
        f"templates/technical-rfc.md's shipped per-task-context slot fires the gate-touching "
        f"grammar at column 0: {slot!r}"
    )

    fake = _run_gate_touching(slot, second_child_pi=None)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]   # promotes normally, no false positive
    assert _reason_edits(fake) == []


# ---- idempotency + independent comment/field keying, same discipline as the sibling refusal sites --

def test_gate_touching_raise_is_idempotent_across_ticks():
    fake = _run_gate_touching("YR-GATE-TOUCHING: raises check_timeout's default\n")
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)
    assert ("EI-100", REASON_FIELD, "Blocked") in edits_after_1

    _sweep(fake)                                             # identical second tick
    assert fake.edits == edits_after_1
    assert fake.comments == comments_after_1


def test_gate_touching_posts_its_own_comment_under_a_stale_different_reason():
    fake = _run_gate_touching("YR-GATE-TOUCHING: raises check_timeout's default\n",
                               comments=[], epic_reason="Needs-info")   # stale, not this site's target
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == GATE_TOUCHING_MARKER
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits   # corrected to this site's own target


def test_gate_touching_makes_no_field_write_when_reason_already_blocked():
    fake = _run_gate_touching("YR-GATE-TOUCHING: raises check_timeout's default\n",
                               comments=[], epic_reason="Blocked")
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == GATE_TOUCHING_MARKER
    assert not any(e[0] == "EI-100" for e in fake.edits)


def test_gate_touching_posts_no_duplicate_once_its_marker_is_on_record_but_still_corrects_a_stale_field():
    fake = _run_gate_touching("YR-GATE-TOUCHING: raises check_timeout's default\n",
                               comments=[GATE_TOUCHING_MARKER], epic_reason="Needs-info")
    assert fake.comments == []
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits


def test_gate_touching_indented_marker_in_a_comment_does_not_satisfy_the_key():
    fake = _run_gate_touching("YR-GATE-TOUCHING: raises check_timeout's default\n",
                               comments=[" " + GATE_TOUCHING_MARKER])
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1                             # the indent did not suppress the post
    assert epic_comments[0][2].splitlines()[0] == GATE_TOUCHING_MARKER


def test_gate_touching_query_requests_child_body():
    """`EPIC_QUERY`'s `subIssues` selection must request `body` -- the field the check reads --
    inside that selection specifically, not merely somewhere else in the query."""
    query = epic_gate.EPIC_QUERY
    sub_start = query.index("subIssues")
    sub_end = query.index("projectItems", sub_start)
    sub_issues_selection = query[sub_start:sub_end]
    assert re.search(r"^\s*body\s*$", sub_issues_selection, re.MULTILINE), (
        "EPIC_QUERY's subIssues selection does not request the child's own `body`"
    )


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
# issue #407 — the routing selector matches issueType in {Feature, Epic}, case-insensitively: an
# Epic-typed Ready parent is routed through the per-epic algorithm exactly as a Feature-typed one.
# ============================================================================

@pytest.mark.parametrize("itype", ["Epic", "EPIC", "epic", "EpIc"])
def test_epic_typed_ready_parent_promotes_first_open_child_same_as_feature(itype):
    """Mirrors test_happy_path_promotes_first_open_task_child byte-for-byte, except the parent's own
    Type is Epic (in various casings) rather than Feature — the routing selector must not care."""
    board = [_item(100, item_id="EI-100", itype=itype, status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD],
        children=[_child(101, pi_id="PI-101", status="Backlog"),
                  _child(102, pi_id="PI-102", status="Backlog")],
    )}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert fake.comments[0][1] == "101"


def test_epic_typed_finished_epic_self_closes_same_as_feature():
    """Mirrors test_finished_epic_with_completed_child_closes_completed with an Epic-typed parent: the
    self-close leg of the per-epic algorithm is reached identically for either arm of the vocabulary."""
    board = [_item(100, item_id="EI-100", itype="Epic", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD, CLOSE_RECORDS],
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]


def test_epic_typed_childless_epic_untouched_same_as_feature():
    board = [_item(100, item_id="EI-100", itype="Epic", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD], children=[])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.edits == [] and fake.comments == []


def test_epic_and_feature_typed_ready_epics_both_promote_in_one_sweep():
    """Two epics on the same board, one of each arm of the vocabulary — both are routed through the
    per-epic algorithm in the same sweep; neither shadows the other."""
    board = [
        _item(100, item_id="EI-100", itype="Feature", status="Ready"),
        _item(200, item_id="EI-200", itype="Epic", status="Ready"),
    ]
    epics = {
        100: _epic_detail(comments=[VALID_RECORD], children=[_child(101, pi_id="PI-101", status="Backlog")]),
        200: _epic_detail(comments=[VALID_RECORD], children=[_child(201, pi_id="PI-201", status="Backlog")]),
    }
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits
    assert ("PI-201", STATUS_FIELD, "Ready") in fake.edits
    assert len(_status_ready_edits(fake)) == 2


# ============================================================================
# AC9 — reuse of the runner's Projects field/option ids (env-overridable, same defaults) & mechanisms
# ============================================================================

def test_defaults_reuse_runner_ids():
    """MIGRATED (issue #388, a declared change to an existing test). These assertions used to restate the
    field-id and option-map literals inline — a second home for them in the suite. The literals now live
    in exactly one home (tools/board_plumbing.py) and are asserted against that home once, in
    tests/test_board_plumbing_home.py; the wall-11 guard (tests/test_board_home_wall.py) forbids a second
    copy. What this test proves is unchanged in spirit: the epic gate OBTAINS every board identifier from
    that one home — no literal restated here. The env-override-on-reload behaviour is still proven end to
    end by test_field_ids_env_overridable below (and, for all eleven identifiers, by the pin suite's
    test_epic_gate_every_board_identifier_is_environment_overridable)."""
    assert epic_gate.PROJECT_ID == board_plumbing.project_id()
    assert epic_gate.STATUS_FIELD_ID == board_plumbing.status_field_id()
    assert epic_gate.REASON_FIELD_ID == board_plumbing.reason_field_id()
    assert epic_gate.STATUS_OPT == board_plumbing.status_opt()
    assert epic_gate.REASON_OPT == board_plumbing.reason_opt()


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
        comments=[VALID_RECORD, CLOSE_RECORDS],
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
        comments=[VALID_RECORD, CLOSE_RECORDS],
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


def test_finished_epic_with_open_question_marker_still_self_closes():
    """Issue #343: the open-questions gate runs AFTER the no-open-children branch -- a finished epic's
    self-close decision is unchanged regardless of any marker in its body."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD, CLOSE_RECORDS],
        body="YR-OPEN-QUESTION: does this even matter now?\n",
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    fake = FakeGh(board, epics)
    _sweep(fake)

    assert fake.closes == [(REPO, "100", "completed")]
    # the open-questions refusal never fires for a finished epic -- no raise, no comment at all
    assert fake.comments == []
    assert not any(e[1] == REASON_FIELD for e in fake.edits)


def test_self_close_is_idempotent_across_ticks():
    """Tick 1 closes the finished epic (the fake flips its board content.state to CLOSED). Tick 2's board
    read no longer sees it OPEN, so it is not a candidate -> no second close call."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD, CLOSE_RECORDS],
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
        comments=[VALID_RECORD, CLOSE_RECORDS], body="",
        children=[_child(101, state="CLOSED", pi_id="PI-101"),
                  _child(102, state="CLOSED", pi_id="PI-102")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    epics[100]["subIssues"]["nodes"][1]["stateReason"] = "NOT_PLANNED"
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]
    assert fake.comments == []
    # the debt counter rides along on every sweep too -- REPO has 0 closed feature epics in this fake's
    # canned data, so it only observes (nothing written), same as every other plain-FakeGh test below
    assert actions == [{"epic": 100, "action": "close", "reason": "completed"},
                        {"action": "debt-count", "repo": REPO, "count": 0, "threshold": 10}]


def test_body_mentioning_kind_sentinel_inline_is_not_a_debt_epic():
    """A backticked/prose mention inside a longer line never matches the exact-line test -> closes as
    a normal (non-debt) epic, not held."""
    body = "See the `YR-ITERATION-KIND: tech-debt` sentinel grammar for details on debt epics."
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD, CLOSE_RECORDS], body=body,
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
    # the debt counter's own observability action (0 closed feature epics for REPO) rides along too
    assert actions == [{"epic": 100, "action": "hold"},
                        {"action": "debt-count", "repo": REPO, "count": 0, "threshold": 10}]
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
    assert actions == [{"epic": 100, "action": "hold"},
                        {"action": "debt-count", "repo": REPO, "count": 0, "threshold": 10}]
    hold_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(hold_comments) == 1
    assert "YR-DEBT-HOLD" in hold_comments[0][2]
    assert fake.closes == []
    # Reason was already Needs-info -> no edit needed/made
    assert _reason_edits(fake) == []


def test_finished_debt_epic_with_open_question_marker_still_holds():
    """Issue #343: a finished DEBT epic's hold decision (waiting on a ledger verdict) is also
    unaffected by an open-question marker -- the no-open-children branch runs first for a debt epic
    too, exactly as it does for the plain self-close path above."""
    board, epics = _debt_epic_detail(comments=[])
    epics[100]["body"] = DEBT_BODY + "\n\nYR-OPEN-QUESTION: does this block the hold too?\n"
    fake = FakeGh(board, epics)
    actions = _sweep(fake)

    assert fake.closes == []
    assert actions == [{"epic": 100, "action": "hold"},
                        {"action": "debt-count", "repo": REPO, "count": 0, "threshold": 10}]
    hold_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(hold_comments) == 1
    assert "YR-DEBT-HOLD" in hold_comments[0][2]
    # the open-questions refusal text never appears -- the debt-hold decision alone governs here
    assert not any(epic_gate.OPEN_QUESTIONS_MARKER in c[2] for c in fake.comments)


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
    assert actions == [{"epic": 100, "action": "hold"},
                        {"action": "debt-count", "repo": REPO, "count": 0, "threshold": 10}]


def test_debt_epic_with_valid_verdict_closes_exactly_as_today():
    board, epics = _debt_epic_detail(comments=[VALID_LEDGER])
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]
    assert actions == [{"epic": 100, "action": "close", "reason": "completed"},
                        {"action": "debt-count", "repo": REPO, "count": 0, "threshold": 10}]
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


def _lock_free(repo=None):
    return False


def _lock_held(repo=None):
    return True


def _lock_state(held_for):
    """A `build_lock_held` probe (`(repo) -> bool`, epic #126 — per-repo, never a host-global lock) that
    reports busy only for repos in `held_for` (a set of `owner/name` strings)."""
    def probe(repo):
        return repo in held_for
    return probe


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


def test_stranded_probe_is_called_with_the_claimed_childs_own_repo():
    """epic #126: the liveness probe is per-repo — it must be invoked with the STRANDED CHILD's own
    repo (never a host-global lock), so a false-positive/negative can't hide behind a stub that ignores
    the argument."""
    seen = []

    def probe(repo):
        seen.append(repo)
        return False

    _run_stranded_candidate(age_min=60, build_lock_held=probe)
    assert seen == [REPO]


def test_no_raise_while_the_claimed_repos_own_lock_is_held():
    """The claimed child's OWN repo has a live build (per-repo lock held) -> defer, don't raise."""
    fake = _run_stranded_candidate(age_min=60, build_lock_held=_lock_state({REPO}))
    assert fake.edits == [] and fake.comments == []


def test_another_repos_held_lock_does_not_defer_the_raise():
    """A DIFFERENT repo's build lock being held must never defer a raise against this claim — the
    retired host-global lock would have (wrongly) deferred every raise org-wide while any one repo had a
    healthy long build in flight; the per-repo probe must not reintroduce that false-stranded suppression
    (or its mirror: a healthy long build on another repo silently masking a genuinely stranded claim)."""
    fake = _run_stranded_candidate(age_min=60, build_lock_held=_lock_state({"other-org/other-repo"}))
    assert ("PI-101", REASON_FIELD, "Blocked") in fake.edits


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


# ============================================================================
# #316 — stranded claims: standalone coverage beside the epic pass. An In-Progress `Task` item with NO
# parent epic (GitHub's own sub-issues `parent` field absent) gets the exact same stranded raise as an
# epic child: past the staleness bound, no open PR, no live build holding its OWN repo's lock ->
# Reason=Blocked + the fact-stating comment. The per-epic pass (tested above) stays untouched.
# ============================================================================

def _run_standalone_stranded_candidate(*, age_min, reason=None, open_prs=None,
                                        build_lock_held=_lock_free, stranded_after_min=None,
                                        parent=None, itype="Task", status="In Progress"):
    """A single standalone board item (default: no parent, Type=Task, In Progress) with the given
    age/Reason/PR/lock state, run through one sweep. No epic detail is registered at all, so ANY write
    the sweep makes here can only have come from the new standalone pass."""
    board = [_item(101, item_id="PI-101", itype=itype, status=status, reason=reason,
                    updated_at=_iso(age_min), parent=parent)]
    fake = FakeGh(board, {}, open_prs=open_prs)
    _sweep(fake, now=_now, build_lock_held=build_lock_held, stranded_after_min=stranded_after_min)
    return fake


def test_standalone_stranded_claim_raised_past_bound_no_pr_lock_free():
    """A standalone (no-parent) Task, In Progress, no Reason, no PR, age > 45min (default bound), lock
    free -> Reason=Blocked + the same fact-stating comment the per-epic pass posts."""
    fake = _run_standalone_stranded_candidate(age_min=60)

    assert ("PI-101", REASON_FIELD, "Blocked") in fake.edits
    comments = [c for c in fake.comments if c[1] == "101"]
    assert len(comments) == 1
    body = comments[0][2].lower()
    assert "stranded" in body
    assert "60" in comments[0][2]                  # the age is reported in the comment
    assert "no live build" in body
    assert "dispatch.md" in body


def test_standalone_raise_uses_the_identical_comment_body_as_the_epic_child_raise():
    """"The same stranded raise" is not just similar wording — it is the SAME shared body function, so a
    standalone claim's comment is byte-identical to what the per-epic pass would post for the same age."""
    fake = _run_standalone_stranded_candidate(age_min=60)
    comments = [c for c in fake.comments if c[1] == "101"]
    assert comments[0][2] == epic_gate._stranded_body(60.0)


def test_standalone_raise_sets_reason_only_no_status_flip():
    """The raise is the termination surface: Reason -> Blocked, but Status is never touched (no flip)."""
    fake = _run_standalone_stranded_candidate(age_min=60)
    assert _status_ready_edits(fake) == []
    assert _reason_edits(fake) == [("PI-101", REASON_FIELD, "Blocked")]


def test_standalone_no_raise_under_staleness_bound():
    """Age under the (default 45 min) bound -> not yet suspect, no raise."""
    fake = _run_standalone_stranded_candidate(age_min=20)
    assert fake.edits == [] and fake.comments == []


def test_standalone_no_raise_while_build_lock_held():
    """A build is live for this claim's own repo (lock held) -> the sweep defers."""
    fake = _run_standalone_stranded_candidate(age_min=60, build_lock_held=_lock_held)
    assert fake.edits == [] and fake.comments == []


def test_standalone_no_raise_when_open_pr_exists():
    """An open `task/101-…` PR exists -> a completed build that only missed the In Review status write;
    do not false-raise it."""
    fake = _run_standalone_stranded_candidate(age_min=60, open_prs=["task/101-fix-thing"])
    assert fake.edits == [] and fake.comments == []


def test_standalone_pass_never_touches_an_epic_child():
    """An In-Progress, stale, PR-less, lock-free Task WITH a parent (an epic child in shape) is skipped
    by the standalone pass — `parent` is exactly the marker that tells the two apart. No epic is
    registered to engage this item either, so any write here would prove the standalone pass wrongly
    reached across the boundary into the per-epic pass's own turf."""
    fake = _run_standalone_stranded_candidate(age_min=60, parent=100)
    assert fake.edits == [] and fake.comments == []


def test_standalone_raise_is_idempotent_across_ticks():
    """Tick 1 raises #101 (Reason -> Blocked, applied back by the fake). Tick 2 sees #101 already
    carrying Blocked -> no double-raise, no duplicate comment."""
    board = [_item(101, item_id="PI-101", itype="Task", status="In Progress", updated_at=_iso(60))]
    fake = FakeGh(board, {}, open_prs=[])
    _sweep(fake, now=_now, build_lock_held=_lock_free)
    edits_after_1, comments_after_1 = list(fake.edits), list(fake.comments)
    assert ("PI-101", REASON_FIELD, "Blocked") in edits_after_1

    _sweep(fake, now=_now, build_lock_held=_lock_free)                 # identical second tick
    assert fake.edits == edits_after_1                                 # no re-raise edit
    assert fake.comments == comments_after_1                           # no duplicate comment


def test_board_query_status_projection_gains_updated_at():
    """BOARD_QUERY's Status field-value projection must request `updatedAt` — the standalone stranded
    pass has no per-issue projectItems fallback the way the per-epic pass does; it reads the staleness
    clock straight off the board item's own Status field value."""
    m = re.search(r'status:\s*fieldValueByName\(name:\s*"Status"\)\s*\{[^}]*\}', epic_gate.BOARD_QUERY)
    assert m, "BOARD_QUERY has no Status fieldValueByName selection"
    assert "updatedAt" in m.group(0)


# ============================================================================
# #90 — the per-repo debt counter and the once-only raise
#
# Extends the stubbed-`gh` harness with the debt-counter's own reads/writes: a paginated closed-Feature-
# epic search per repo, the open-due-raise search, the manifest contents read, `issue create`, and
# `project item-add`. `FakeDebtGh` subclasses `FakeGh` so a test can freely mix ordinary epic-processing
# fixtures with debt-counter fixtures in the same fake (used by the isolation test below).
# ============================================================================

DEBT_REPO_A = "yellow-robots/repo-a"
DEBT_REPO_B = "yellow-robots/repo-b"


def _closed_epic(number, *, closed_at, state_reason="COMPLETED", body="", itype="Feature"):
    """A closed-issue search-result node, as DEBT_CLOSED_SEARCH_QUERY returns it."""
    return {"number": number, "closedAt": closed_at, "stateReason": state_reason, "body": body,
            "issueType": {"name": itype}}


def _hand_written_due_body(repo, anchor, count=10, counted=(101,)):
    """A due-raise body authored straight from the AC's grammar (marker line, then repo/anchor/count/
    counted, then prose) -- independent of the implementation's own `_due_body` wording, so the match
    logic is proven against the spec's letter rather than against itself."""
    counted_str = ", ".join(f"#{n}" for n in counted)
    return (
        f"{epic_gate.DUE_MARKER}\n"
        f"repo: {repo}\n"
        f"anchor: {anchor}\n"
        f"count: {count}\n"
        f"counted: {counted_str}\n\n"
        "Prose pointing at the round protocol."
    )


def _due_raise_node(number, *, repo, anchor, count=10, counted=(101,), on_board=True,
                     project_number=1, item_id="PI-EXISTING", wrong_project=False):
    """An open due-raise search-result node, as DEBT_RAISE_SEARCH_QUERY returns it. `on_board=False` (or
    `wrong_project=True`) models the half-done raise -- created, but never added to our board."""
    nodes = []
    if on_board:
        nodes.append({"id": item_id, "project": {"number": 999 if wrong_project else project_number}})
    return {"number": number, "body": _hand_written_due_body(repo, anchor, count, counted),
            "url": f"https://github.com/{repo}/issues/{number}", "projectItems": {"nodes": nodes}}


class FakeDebtGh(FakeGh):
    """Extends `FakeGh` with the debt counter's reads/writes.

    `closed_epic_pages`: repo -> list of *pages* (each page a list of `_closed_epic` nodes) -- a
    single-page repo can just pass `[page]`. `manifest_repos`: repo -> raw `.yr/factory.toml` text (a
    repo absent from this dict makes the contents read raise, modelling a missing/unreadable manifest).
    `due_raise_nodes`: repo -> list of existing open-raise nodes. `search_raises`: repos whose closed-
    epic search raises, to prove per-repo failure isolation.

    A created issue is fed back into its own `due_raise_nodes` bucket, and a later `item-add` for that
    issue's URL attaches a project item onto it -- so calling `_sweep_debt_counters` twice on the SAME
    fake is a genuine two-tick idempotency proof, not just two independently-seeded calls."""

    def __init__(self, board_nodes, epic_details, open_prs=None, *,
                 closed_epic_pages=None, manifest_repos=None, due_raise_nodes=None, search_raises=None):
        super().__init__(board_nodes, epic_details, open_prs)
        self.closed_epic_pages = {r: [list(p) for p in pages] for r, pages in (closed_epic_pages or {}).items()}
        self.manifest_repos = dict(manifest_repos or {})
        self.due_raise_nodes = {r: list(ns) for r, ns in (due_raise_nodes or {}).items()}
        self.search_raises = set(search_raises or [])
        self.search_argv = []
        self.manifest_argv = []
        self.issue_create_argv = []
        self.item_add_argv = []
        self._next_id = 9000

    def __call__(self, argv):
        argv = list(argv)
        if argv[:2] == ["api", "graphql"]:
            q = cursor = None
            for a in argv:
                if a.startswith("q="):
                    q = a[len("q="):]
                elif a.startswith("cursor="):
                    cursor = a[len("cursor="):]
            if q is not None:
                self.search_argv.append(argv)
                return self._search(q, cursor)
        elif argv[0] == "api" and len(argv) > 1 and "contents/.yr/factory.toml" in argv[1]:
            self.manifest_argv.append(argv)
            m = re.match(r"repos/([^/]+)/([^/]+)/contents/", argv[1])
            repo = f"{m.group(1)}/{m.group(2)}"
            if repo not in self.manifest_repos:
                raise RuntimeError(f"gh api {argv[1]} failed (404): Not Found")
            return self.manifest_repos[repo]
        elif argv[:2] == ["issue", "create"]:
            f = _flags(argv)
            self.issue_create_argv.append(argv)
            self._next_id += 1
            number = self._next_id
            url = f"https://github.com/{f['--repo']}/issues/{number}"
            node = {"number": number, "body": f["--body"], "url": url, "projectItems": {"nodes": []}}
            self.due_raise_nodes.setdefault(f["--repo"], []).append(node)
            return url + "\n"
        elif argv[:2] == ["project", "item-add"]:
            f = _flags(argv)
            self.item_add_argv.append(argv)
            self._next_id += 1
            item_id = f"PI-DUE-{self._next_id}"
            pn = int(argv[2])
            for nodes in self.due_raise_nodes.values():
                for n in nodes:
                    if n.get("url") == f["--url"]:
                        n["projectItems"]["nodes"] = [{"id": item_id, "project": {"number": pn}}]
            return {"id": item_id}
        return super().__call__(argv)

    def _search(self, q, cursor):
        m = re.search(r"repo:(\S+)", q)
        repo = m.group(1) if m else None
        if "state:closed" in q:
            if repo in self.search_raises:
                raise RuntimeError(f"gh api graphql failed: search unavailable for {repo}")
            pages = self.closed_epic_pages.get(repo, [[]])
            idx = int(cursor) if cursor else 0
            nodes = pages[idx] if idx < len(pages) else []
            has_next = idx + 1 < len(pages)
            return {"data": {"search": {"nodes": nodes,
                                         "pageInfo": {"hasNextPage": has_next,
                                                      "endCursor": str(idx + 1) if has_next else None}}}}
        if epic_gate.DUE_MARKER in q:
            return {"data": {"search": {"nodes": self.due_raise_nodes.get(repo, [])}}}
        raise AssertionError(f"unexpected search query: {q!r}")


def _run_debt_sweep(fake, repos, *, project_number=1):
    return epic_gate._sweep_debt_counters(
        fake, repos, project_number=project_number,
        status_field_id=STATUS_FIELD, status_opt=STATUS_OPT, org="yellow-robots",
    )


# ---- repo-set derivation: distinct repos over Feature-type board items, any state, any Status --------

def test_debt_repo_set_any_state_any_status_feature_only():
    nodes = [
        _item(1, item_id="A", itype="Feature", status="Ready", state="OPEN", repo="org/r1"),
        _item(2, item_id="B", itype="Feature", status=None, state="CLOSED", repo="org/r2"),
        _item(3, item_id="C", itype="Feature", status="Backlog", state="OPEN", repo="org/r1"),  # dup
        _item(4, item_id="D", itype="Task", status="Backlog", state="OPEN", repo="org/r3"),     # not Feature
        {"id": "E", "content": None},                                                           # draft item
    ]
    assert epic_gate._debt_repo_set(nodes) == {"org/r1", "org/r2"}


def test_debt_repo_set_excludes_epic_typed_items():
    """issue #407: the routing widening (issueType in {Feature, Epic}) is the sweep's own routing
    selector's concern, not the debt counter's — `_debt_repo_set` keeps its Feature-only match, so a
    repo whose only board item is Epic-typed is never counted."""
    nodes = [
        _item(1, item_id="A", itype="Feature", status="Ready", state="OPEN", repo="org/r1"),
        _item(2, item_id="B", itype="Epic", status="Ready", state="OPEN", repo="org/r2"),
    ]
    assert epic_gate._debt_repo_set(nodes) == {"org/r1"}


# ---- anchor selection + countable classification (`_debt_anchor_and_countable`) -----------------------

def test_no_anchor_all_countable_epics_count():
    closed = [_closed_epic(1, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(2, closed_at="2026-02-01T00:00:00Z"),
              _closed_epic(3, closed_at="2026-03-01T00:00:00Z")]
    anchor, countable = epic_gate._debt_anchor_and_countable(closed)
    assert anchor is None
    assert sorted(n["number"] for n in countable) == [1, 2, 3]


def test_anchor_is_the_latest_closed_debt_epic():
    closed = [
        _closed_epic(1, closed_at="2026-01-01T00:00:00Z", body=DEBT_BODY),
        _closed_epic(2, closed_at="2026-03-01T00:00:00Z", body=DEBT_BODY),   # the latest debt epic
        _closed_epic(3, closed_at="2026-02-01T00:00:00Z"),                  # before the anchor -> excluded
        _closed_epic(4, closed_at="2026-04-01T00:00:00Z"),                  # after the anchor -> counted
    ]
    anchor, countable = epic_gate._debt_anchor_and_countable(closed)
    assert anchor["number"] == 2
    assert [n["number"] for n in countable] == [4]


def test_not_planned_closed_debt_epic_still_anchors():
    """The spec's letter: any closed debt epic anchors, regardless of close reason."""
    closed = [_closed_epic(1, closed_at="2026-01-01T00:00:00Z", state_reason="NOT_PLANNED", body=DEBT_BODY),
              _closed_epic(2, closed_at="2026-02-01T00:00:00Z")]
    anchor, countable = epic_gate._debt_anchor_and_countable(closed)
    assert anchor["number"] == 1
    assert [n["number"] for n in countable] == [2]


def test_not_planned_feature_epic_never_counts():
    """Pins the coupling with `_epic_close_reason`'s 'completed' write: an epic only closes with reason
    `completed` when >=1 child completed, and the counter's own filter requires `stateReason ==
    COMPLETED` -- a not-planned closed epic must never be countable."""
    closed = [_closed_epic(1, closed_at="2026-01-01T00:00:00Z", state_reason="NOT_PLANNED")]
    _, countable = epic_gate._debt_anchor_and_countable(closed)
    assert countable == []
    assert epic_gate._epic_close_reason([{"stateReason": "NOT_PLANNED"}]) == "not planned"


def test_debt_epic_itself_never_countable_even_if_completed():
    closed = [_closed_epic(1, closed_at="2026-01-01T00:00:00Z", state_reason="COMPLETED", body=DEBT_BODY)]
    anchor, countable = epic_gate._debt_anchor_and_countable(closed)
    assert countable == []
    assert anchor["number"] == 1


def test_node_missing_closed_at_is_skipped_defensively():
    closed = [
        {"number": 1, "closedAt": None, "stateReason": "COMPLETED", "body": DEBT_BODY,
         "issueType": {"name": "Feature"}},
        _closed_epic(2, closed_at="2026-01-01T00:00:00Z"),
    ]
    anchor, countable = epic_gate._debt_anchor_and_countable(closed)
    assert anchor is None                              # the debt epic with no closedAt never anchors
    assert [n["number"] for n in countable] == [2]


# ---- threshold resolution: env beats manifest beats default; any failure falls back to the default ----

def test_debt_round_every_default_is_10():
    assert epic_gate.DEBT_ROUND_EVERY == 10


def test_manifest_threshold_used_when_env_unset(monkeypatch):
    monkeypatch.delenv("DEBT_ROUND_EVERY", raising=False)
    assert epic_gate._resolve_debt_threshold(lambda argv: "debt_round_every = 7\n", "org/repo") == 7


def test_env_threshold_beats_manifest_and_short_circuits_the_read(monkeypatch):
    monkeypatch.setenv("DEBT_ROUND_EVERY", "4")
    try:
        importlib.reload(epic_gate)

        def gh(argv):
            raise AssertionError("the manifest must not be read when the env override is set")

        assert epic_gate._resolve_debt_threshold(gh, "org/repo") == 4
    finally:
        monkeypatch.undo()
        importlib.reload(epic_gate)


def test_unreadable_manifest_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DEBT_ROUND_EVERY", raising=False)

    def gh(argv):
        raise RuntimeError("gh api ... failed (404): Not Found")

    assert epic_gate._resolve_debt_threshold(gh, "org/repo") == epic_gate.DEBT_ROUND_EVERY


def test_manifest_invalid_values_fall_back_to_default(monkeypatch):
    monkeypatch.delenv("DEBT_ROUND_EVERY", raising=False)
    bad_manifests = [
        "other_key = 1\n",              # missing debt_round_every
        "debt_round_every = 0\n",       # below 1
        "debt_round_every = -3\n",      # below 1
        "debt_round_every = true\n",    # a TOML boolean, not an integer
        'debt_round_every = "5"\n',     # a TOML string, not an integer
        "not [ valid toml",             # unparseable
    ]
    for raw in bad_manifests:
        def gh(argv, raw=raw):
            return raw
        assert epic_gate._resolve_debt_threshold(gh, "org/repo") == epic_gate.DEBT_ROUND_EVERY, raw


def test_env_threshold_overrides_manifest_end_to_end(monkeypatch):
    """The precedence proven through the real counting path, not just the resolver in isolation."""
    monkeypatch.setenv("DEBT_ROUND_EVERY", "1")
    try:
        importlib.reload(epic_gate)
        closed = [_closed_epic(1, closed_at="2026-01-01T00:00:00Z")]
        fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                           manifest_repos={DEBT_REPO_A: "debt_round_every = 100\n"})
        actions = epic_gate._sweep_debt_counters(
            fake, {DEBT_REPO_A}, project_number=1,
            status_field_id=STATUS_FIELD, status_opt=STATUS_OPT, org="yellow-robots")
        assert actions and actions[0]["action"] == "debt-raise"   # env(1) reached, not manifest(100)
    finally:
        monkeypatch.undo()
        importlib.reload(epic_gate)


# ---- the search itself: query shape, pagination, defensive client-side type re-filter ------------------

def test_closed_epic_search_query_shape():
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [[]]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 5\n"})
    _run_debt_sweep(fake, {DEBT_REPO_A})
    assert len(fake.search_argv) == 1
    q = next(a for a in fake.search_argv[0] if a.startswith("q="))
    assert f"repo:{DEBT_REPO_A}" in q and "state:closed" in q and "type:Feature" in q


def test_closed_epic_search_paginates_across_two_pages():
    page1 = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z")]
    page2 = [_closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [page1, page2]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 5\n"})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert actions == [{"action": "debt-count", "repo": DEBT_REPO_A, "count": 2, "threshold": 5}]
    assert len(fake.search_argv) == 2                  # both pages were actually fetched


def test_closed_epic_search_filters_non_feature_nodes_defensively():
    contaminated = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
                    _closed_epic(999, closed_at="2026-01-01T00:00:00Z", itype="Task")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [contaminated]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 5\n"})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert actions == [{"action": "debt-count", "repo": DEBT_REPO_A, "count": 1, "threshold": 5}]


def test_closed_epic_search_filters_epic_typed_nodes_defensively():
    """issue #407: the debt counter's Feature-scoped semantics are unchanged by the routing widening —
    an Epic-typed node surfacing from the search re-filters out exactly like a Task-typed one."""
    contaminated = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
                    _closed_epic(999, closed_at="2026-01-01T00:00:00Z", itype="Epic")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [contaminated]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 5\n"})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert actions == [{"action": "debt-count", "repo": DEBT_REPO_A, "count": 1, "threshold": 5}]


# ---- below / at threshold ------------------------------------------------------------------------------

def test_below_threshold_writes_nothing():
    closed = [_closed_epic(1, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(2, closed_at="2026-02-01T00:00:00Z")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 5\n"})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert actions == [{"action": "debt-count", "repo": DEBT_REPO_A, "count": 2, "threshold": 5}]
    assert fake.issue_create_argv == [] and fake.item_add_argv == [] and fake.edit_argv == []


def test_at_threshold_creates_issue_item_add_and_backlog_edit_with_due_record():
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n"})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})

    assert len(fake.issue_create_argv) == 1
    f = _flags(fake.issue_create_argv[0])
    assert f["--repo"] == DEBT_REPO_A and f["--type"] == "Task"
    assert "2" in f["--title"]                              # names the count

    body = f["--body"]
    assert body.splitlines()[0] == epic_gate.DUE_MARKER      # the marker on its own whole line
    assert epic_gate._extract_field(body, "repo") == DEBT_REPO_A
    assert epic_gate._extract_field(body, "anchor") == "none"
    assert epic_gate._extract_field(body, "count") == "2"
    counted_field = epic_gate._extract_field(body, "counted")
    assert "101" in counted_field and "102" in counted_field
    assert "debt-rounds.md" in body

    assert len(fake.item_add_argv) == 1
    add_f = _flags(fake.item_add_argv[0])
    assert fake.item_add_argv[0][2] == "1"                  # project_number positional
    assert add_f["--owner"] == "yellow-robots" and add_f["--format"] == "json"

    assert len(fake.edit_argv) == 1
    ef = _flags(fake.edit_argv[0])
    assert ef["--field-id"] == STATUS_FIELD
    assert ef["--single-select-option-id"] == "Backlog"
    assert ef["--project-id"] == epic_gate.PROJECT_ID

    assert actions == [{"action": "debt-raise", "repo": DEBT_REPO_A, "count": 2, "anchor": "none"}]


# ---- search-before-create: no duplicate raise, repair a half-done one, a differing anchor is a new key -

def test_existing_raise_fully_on_board_creates_nothing():
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    existing = _due_raise_node(900, repo=DEBT_REPO_A, anchor="none", count=2, counted=(101, 102),
                                on_board=True)
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n"},
                       due_raise_nodes={DEBT_REPO_A: [existing]})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert actions == []
    assert fake.issue_create_argv == [] and fake.item_add_argv == [] and fake.edit_argv == []


def test_debt_raise_is_idempotent_across_two_ticks():
    """A genuine two-tick proof: tick 1 creates the raise (through this same fake's create/item-add
    handlers, which feed the new issue back into the search state); tick 2 sees it already fully on the
    board and creates nothing more."""
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n"})

    actions_1 = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert actions_1 and actions_1[0]["action"] == "debt-raise"
    assert len(fake.issue_create_argv) == 1 and len(fake.item_add_argv) == 1

    actions_2 = _run_debt_sweep(fake, {DEBT_REPO_A})               # identical second tick
    assert actions_2 == []                                         # no re-raise
    assert len(fake.issue_create_argv) == 1                        # no duplicate create
    assert len(fake.item_add_argv) == 1                             # no duplicate item-add


def test_existing_raise_with_different_anchor_does_not_suppress_a_new_raise():
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    stale = _due_raise_node(800, repo=DEBT_REPO_A, anchor="#5", count=2, counted=(50, 51), on_board=True)
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n"},
                       due_raise_nodes={DEBT_REPO_A: [stale]})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert len(fake.issue_create_argv) == 1
    assert actions and actions[0]["action"] == "debt-raise"


def test_existing_raise_missing_from_board_gets_repaired():
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
              _closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    existing = _due_raise_node(900, repo=DEBT_REPO_A, anchor="none", count=2, counted=(101, 102),
                                on_board=False)
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n"},
                       due_raise_nodes={DEBT_REPO_A: [existing]})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})

    assert fake.issue_create_argv == []                             # never re-created
    assert len(fake.item_add_argv) == 1
    assert _flags(fake.item_add_argv[0])["--url"] == existing["url"]
    assert len(fake.edit_argv) == 1
    assert _flags(fake.edit_argv[0])["--single-select-option-id"] == "Backlog"
    assert actions == [{"action": "debt-repair", "repo": DEBT_REPO_A, "issue": 900}]


def test_existing_raise_on_a_different_project_gets_repaired_too():
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z")]
    existing = _due_raise_node(900, repo=DEBT_REPO_A, anchor="none", count=1, counted=(101,),
                                on_board=True, wrong_project=True)
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 1\n"},
                       due_raise_nodes={DEBT_REPO_A: [existing]})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A})
    assert fake.issue_create_argv == []
    assert len(fake.item_add_argv) == 1
    assert actions == [{"action": "debt-repair", "repo": DEBT_REPO_A, "issue": 900}]


# ---- a counter failure on one repo is isolated ---------------------------------------------------------

def test_debt_error_on_one_repo_does_not_affect_another_repos_counting():
    closed_b = [_closed_epic(201, closed_at="2026-01-01T00:00:00Z")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_B: [closed_b]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n",
                                       DEBT_REPO_B: "debt_round_every = 5\n"},
                       search_raises={DEBT_REPO_A})
    actions = _run_debt_sweep(fake, {DEBT_REPO_A, DEBT_REPO_B})
    by_repo = {a["repo"]: a for a in actions}
    assert by_repo[DEBT_REPO_A]["action"] == "debt-error"
    assert by_repo[DEBT_REPO_B] == {"action": "debt-count", "repo": DEBT_REPO_B, "count": 1, "threshold": 5}


def test_debt_error_does_not_affect_epic_processing():
    """The failure is scoped to the counter's own repo loop -- a Ready epic elsewhere on the board still
    promotes normally in the very same sweep."""
    board = [
        _item(100, item_id="EI-100", itype="Feature", status="Ready", repo=DEBT_REPO_A),
        _item(200, item_id="EI-200", itype="Feature", status=None, state="CLOSED", repo=DEBT_REPO_B),
    ]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                                children=[_child(101, pi_id="PI-101", status="Backlog", repo=DEBT_REPO_A)])}
    fake = FakeDebtGh(board, epics,
                       closed_epic_pages={DEBT_REPO_B: [[_closed_epic(201, closed_at="2026-01-01T00:00:00Z")]]},
                       manifest_repos={DEBT_REPO_A: "# onboarded\n", DEBT_REPO_B: "debt_round_every = 5\n"},
                       search_raises={DEBT_REPO_A})
    actions = epic_gate.sweep_epics(
        gh=fake, org="yellow-robots", project_number=1,
        status_field_id=STATUS_FIELD, reason_field_id=REASON_FIELD,
        status_opt=STATUS_OPT, reason_opt=REASON_OPT,
    )
    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits              # the epic's own promotion succeeded
    kinds = {a["action"] for a in actions}
    assert "promote" in kinds and "debt-error" in kinds
    assert any(a.get("action") == "debt-error" and a.get("repo") == DEBT_REPO_A for a in actions)
    assert any(a.get("action") == "debt-count" and a.get("repo") == DEBT_REPO_B for a in actions)


# ---- write mechanics + the invariant: never Ready, never close, never touches Reason -------------------

def test_writes_use_the_runner_gh_mechanisms_for_a_raise():
    closed = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z")]
    fake = FakeDebtGh([], {}, closed_epic_pages={DEBT_REPO_A: [closed]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 1\n"})
    _run_debt_sweep(fake, {DEBT_REPO_A})

    create = fake.issue_create_argv[0]
    assert create[:2] == ["issue", "create"]
    add = fake.item_add_argv[0]
    assert add[:2] == ["project", "item-add"]
    edit = fake.edit_argv[0]
    assert edit[:2] == ["project", "item-edit"]


def test_debt_counter_never_sets_ready_closes_or_touches_reason():
    closed_a = [_closed_epic(101, closed_at="2026-01-01T00:00:00Z"),
                _closed_epic(102, closed_at="2026-02-01T00:00:00Z")]
    existing_half = _due_raise_node(900, repo=DEBT_REPO_B, anchor="none", count=1, counted=(201,),
                                     on_board=False)
    fake = FakeDebtGh(
        [], {},
        closed_epic_pages={DEBT_REPO_A: [closed_a],
                            DEBT_REPO_B: [[_closed_epic(201, closed_at="2026-01-01T00:00:00Z")]]},
        manifest_repos={DEBT_REPO_A: "debt_round_every = 2\n", DEBT_REPO_B: "debt_round_every = 1\n"},
        due_raise_nodes={DEBT_REPO_B: [existing_half]},
    )
    _run_debt_sweep(fake, {DEBT_REPO_A, DEBT_REPO_B})

    assert fake.closes == []                                # never closes anything
    for _id, field, opt in fake.edits:
        assert field == STATUS_FIELD                        # never touches the Reason field
        assert opt == "Backlog"                              # never sets Ready


def test_sweep_debt_counters_signature_has_no_reason_param():
    """Structural guarantee behind the "never touches Reason" invariant: the function isn't even handed
    a Reason field id or option map to write with."""
    params = inspect.signature(epic_gate._sweep_debt_counters).parameters
    assert "reason_field_id" not in params and "reason_opt" not in params


# ---- `main()`'s print lines for every debt action kind --------------------------------------------------

def test_main_prints_debt_count_line(capsys, monkeypatch):
    board = [_item(200, item_id="EI-200", itype="Feature", status=None, state="CLOSED", repo=DEBT_REPO_A)]
    fake = FakeDebtGh(board, {},
                       closed_epic_pages={DEBT_REPO_A: [[_closed_epic(1, closed_at="2026-01-01T00:00:00Z")]]},
                       manifest_repos={DEBT_REPO_A: "debt_round_every = 5\n"})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert f"debt-count {DEBT_REPO_A}" in out and "1/5" in out


def test_main_prints_every_debt_action_kind(capsys, monkeypatch):
    repo_count, repo_raise = "yellow-robots/repo-count", "yellow-robots/repo-raise"
    repo_repair, repo_error = "yellow-robots/repo-repair", "yellow-robots/repo-error"
    board = [_item(n, item_id=f"I{n}", itype="Feature", status=None, state="CLOSED", repo=r)
             for n, r in enumerate((repo_count, repo_raise, repo_repair, repo_error), start=1)]
    existing_half = _due_raise_node(900, repo=repo_repair, anchor="none", count=1, counted=(31,),
                                     on_board=False)
    fake = FakeDebtGh(
        board, {},
        closed_epic_pages={
            repo_count: [[_closed_epic(11, closed_at="2026-01-01T00:00:00Z")]],
            repo_raise: [[_closed_epic(21, closed_at="2026-01-01T00:00:00Z")]],
            repo_repair: [[_closed_epic(31, closed_at="2026-01-01T00:00:00Z")]],
        },
        manifest_repos={repo_count: "debt_round_every = 5\n", repo_raise: "debt_round_every = 1\n",
                         repo_repair: "debt_round_every = 1\n"},
        due_raise_nodes={repo_repair: [existing_half]},
        search_raises={repo_error},
    )
    monkeypatch.setattr(epic_gate, "_gh", fake)
    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "debt-count" in out and repo_count in out
    assert "raised a tech-debt round" in out and repo_raise in out
    assert "repaired tech-debt raise #900" in out and repo_repair in out
    assert "debt-error" in out and repo_error in out


# ============================================================================
# #108 — org-wide board intake for registered repos
#
# Extends the stubbed-`gh` harness with intake's own reads/writes: `gh issue list --repo ... --state
# open ...` per registered repo, and `project item-add` for each issue found missing from the board.
# `FakeIntakeGh` subclasses `FakeGh` for the same reason `FakeDebtGh` does: an `item-add` is fed back
# onto the SAME live `board_nodes` list the board query re-serializes on every call, so running intake
# twice against one fake is a genuine two-tick idempotency proof, not two independently-seeded calls.
# ============================================================================

INTAKE_REPO_A = "yellow-robots/intake-a"
INTAKE_REPO_B = "yellow-robots/intake-b"


def _open_issue(number, repo=INTAKE_REPO_A):
    """An open-issue node exactly as `gh issue list --json number,url` returns it."""
    return {"number": number, "url": f"https://github.com/{repo}/issues/{number}"}


class FakeIntakeGh(FakeGh):
    """`open_issues`: repo -> list of `_open_issue` dicts (a repo absent from this dict makes its
    `issue list` read raise, modelling an inaccessible repo — never asserted on here, since intake's
    per-repo error isolation isn't part of the acceptance criteria)."""

    def __init__(self, board_nodes, epic_details, open_prs=None, *, open_issues=None):
        super().__init__(board_nodes, epic_details, open_prs)
        self.open_issues = {r: list(v) for r, v in (open_issues or {}).items()}
        self.issue_list_argv = []
        self.item_add_argv = []
        self._next_id = 7000

    def __call__(self, argv):
        argv = list(argv)
        if argv[:2] == ["issue", "list"]:
            self.issue_list_argv.append(argv)
            f = _flags(argv)
            repo = f["--repo"]
            if repo not in self.open_issues:
                raise RuntimeError(f"gh issue list --repo {repo} failed")
            return json.dumps(self.open_issues[repo])
        if argv[:2] == ["project", "item-add"]:
            f = _flags(argv)
            self.item_add_argv.append(argv)
            self._next_id += 1
            item_id = f"PI-INTAKE-{self._next_id}"
            m = re.match(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)", f["--url"])
            repo, number = m.group(1), int(m.group(2))
            node = _item(number, item_id=item_id, itype="Task", repo=repo)
            self.board_nodes.append(node)               # feeds a later board read / re-run
            self._index[item_id] = node
            self._by_number[number] = node
            return {"id": item_id}
        return super().__call__(argv)


def _run_intake(fake, repos, *, project_number=1, org="yellow-robots"):
    return epic_gate._sweep_intake(fake, repos, fake.board_nodes,
                                    project_number=project_number, org=org)


# ---- AC1 — a missing open issue gets exactly one native item-add ----------------------------------

def test_intake_adds_every_missing_open_issue():
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(10), _open_issue(11)]})
    actions = _run_intake(fake, [INTAKE_REPO_A])

    assert len(fake.item_add_argv) == 2
    assert fake.item_add_argv[0] == ["project", "item-add", "1", "--owner", "yellow-robots",
                                      "--url", f"https://github.com/{INTAKE_REPO_A}/issues/10"]
    assert fake.item_add_argv[1] == ["project", "item-add", "1", "--owner", "yellow-robots",
                                      "--url", f"https://github.com/{INTAKE_REPO_A}/issues/11"]
    assert {(a["repo"], a["issue"]) for a in actions} == {(INTAKE_REPO_A, 10), (INTAKE_REPO_A, 11)}
    assert all(a["action"] == "intake" for a in actions)


def test_intake_sweeps_every_registered_repo():
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(1, INTAKE_REPO_A)],
                                              INTAKE_REPO_B: [_open_issue(2, INTAKE_REPO_B)]})
    actions = _run_intake(fake, [INTAKE_REPO_A, INTAKE_REPO_B])
    assert {(a["repo"], a["issue"]) for a in actions} == {(INTAKE_REPO_A, 1), (INTAKE_REPO_B, 2)}


# ---- AC2 — idempotent: an issue already on the board is never re-added --------------------------------

def test_intake_skips_an_issue_already_on_the_board():
    board = [_item(10, item_id="PI-10", itype="Task", status="Backlog", repo=INTAKE_REPO_A)]
    fake = FakeIntakeGh(board, {}, open_issues={INTAKE_REPO_A: [_open_issue(10), _open_issue(11)]})
    actions = _run_intake(fake, [INTAKE_REPO_A])

    assert len(fake.item_add_argv) == 1
    assert fake.item_add_argv[0][-1] == f"https://github.com/{INTAKE_REPO_A}/issues/11"
    assert actions == [{"action": "intake", "repo": INTAKE_REPO_A, "issue": 11}]


def test_intake_already_on_board_issue_ignores_its_status():
    """An issue on the board with ANY Status (or no Status at all) is still never re-added — the
    idempotency check is presence-on-the-board, not any particular Status."""
    board = [_item(10, item_id="PI-10", itype="Task", status=None, repo=INTAKE_REPO_A)]
    fake = FakeIntakeGh(board, {}, open_issues={INTAKE_REPO_A: [_open_issue(10)]})
    actions = _run_intake(fake, [INTAKE_REPO_A])
    assert actions == []
    assert fake.item_add_argv == []


def test_intake_is_idempotent_across_two_ticks():
    """A genuine two-tick proof: tick 1 adds the issue (through this same fake's item-add handler,
    which feeds the new item straight back onto `board_nodes`); tick 2, run against the SAME fake,
    sees it already on the board and adds nothing."""
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(10)]})

    first = _run_intake(fake, [INTAKE_REPO_A])
    assert len(first) == 1
    assert len(fake.item_add_argv) == 1

    second = _run_intake(fake, [INTAKE_REPO_A])
    assert second == []
    assert len(fake.item_add_argv) == 1                 # no duplicate item-add on the re-run


# ---- AC2 — closed issues and pull requests are never added --------------------------------------------

def test_intake_reads_open_issues_only_never_prs():
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(10)]})
    _run_intake(fake, [INTAKE_REPO_A])

    assert len(fake.issue_list_argv) == 1
    f = _flags(fake.issue_list_argv[0])
    assert f["--state"] == "open"                        # closed issues are never even read
    assert fake.issue_list_argv[0][:2] == ["issue", "list"]   # never `gh pr list` -- PRs never surface
    assert fake.pr_list_argv == []


def test_intake_never_touches_status_or_reason():
    """Intake adds exactly one write kind, `item-add` -- it never sets Status/Reason itself (the
    board's own item-added workflow does that, out of the sweep's hands)."""
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(10), _open_issue(11)]})
    _run_intake(fake, [INTAKE_REPO_A])
    assert fake.edits == []
    assert fake.comments == []
    assert fake.closes == []


# ---- AC1/AC2 — wired into the org sweep itself, gated on the explicit `repos` seam ---------------------

def test_sweep_epics_runs_intake_before_epic_processing():
    board = []
    fake = FakeIntakeGh(board, {}, open_issues={INTAKE_REPO_A: [_open_issue(50)]})
    actions = epic_gate.sweep_epics(
        gh=fake, org="yellow-robots", project_number=1,
        status_field_id=STATUS_FIELD, reason_field_id=REASON_FIELD,
        status_opt=STATUS_OPT, reason_opt=REASON_OPT, repos=[INTAKE_REPO_A],
    )
    assert {"action": "intake", "repo": INTAKE_REPO_A, "issue": 50} in actions


def test_sweep_epics_default_repos_runs_no_intake():
    """`repos` left unset (the promotion sweep's own tests never pass it) means no intake at all --
    `sweep_epics` never touches `gh issue list` when no repo list is supplied."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics)                          # the plain fake -- no `issue list` handler at all
    actions = _sweep(fake)
    assert not any(a["action"] == "intake" for a in actions)


# ---- AC3 — each add prints one report line (repo, issue number) in the sweep's CLI output -------------

def test_main_prints_one_report_line_per_intake_add(capsys, monkeypatch):
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(10), _open_issue(11)],
                                              INTAKE_REPO_B: [_open_issue(20)]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [INTAKE_REPO_A, INTAKE_REPO_B])

    rc = epic_gate.main()
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "added" in ln]
    assert len(lines) == 3                                # exactly one line per add, no more
    assert any(INTAKE_REPO_A in ln and "10" in ln for ln in lines)
    assert any(INTAKE_REPO_A in ln and "11" in ln for ln in lines)
    assert any(INTAKE_REPO_B in ln and "20" in ln for ln in lines)


def test_main_prints_nothing_to_do_when_intake_finds_nothing_missing(capsys, monkeypatch):
    board = [_item(10, item_id="PI-10", itype="Task", status="Backlog", repo=INTAKE_REPO_A)]
    fake = FakeIntakeGh(board, {}, open_issues={INTAKE_REPO_A: [_open_issue(10)]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [INTAKE_REPO_A])

    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "nothing to do" in out
    assert "added" not in out


# ============================================================================
# it-33 slice 2 (issue #457) — every runtime surface states the commit it runs from: the sweep's
# CLI entrypoint prints one statement line naming the whole tree's commit before it acts.
# ============================================================================

def test_main_prints_the_commit_statement_before_any_sweep_action_line(capsys, monkeypatch):
    board = [_item(10, item_id="PI-10", itype="Task", status="Backlog", repo=INTAKE_REPO_A)]
    fake = FakeIntakeGh(board, {}, open_issues={INTAKE_REPO_A: [_open_issue(10)]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [INTAKE_REPO_A])
    # this test pins the STATEMENT line's position, not the drift alarm's (see the it-33 slice 4
    # tests below) — a clean drift moment keeps the pre-existing adjacency intact. Both drift
    # findings sources are stubbed clean (slice 6 adds deploy_record_findings alongside
    # build_findings — an unstubbed one would otherwise reach a real `gh` for #464).
    monkeypatch.setattr(epic_gate.drift, "build_findings", lambda repo_root, home: [])
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", lambda repo_root, home: [])

    rc = epic_gate.main()
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines, "main() printed nothing at all"
    real = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert lines[0].startswith("epic-gate: "), "the statement is not the FIRST line main() prints"
    assert f"commit: {real}" in lines[0]
    assert "nothing to do" in lines[1]


# ============================================================================
# it-33 slice 4 (issue #458) — the sweep folds in the build-host drift alarm's findings: printed,
# advisory only — never altering the sweep's actions or its exit code (never a merge gate).
# ============================================================================

def test_main_prints_build_drift_findings_between_statement_and_action_lines(capsys, monkeypatch):
    board = [_item(10, item_id="PI-10", itype="Task", status="Backlog", repo=INTAKE_REPO_A)]
    fake = FakeIntakeGh(board, {}, open_issues={INTAKE_REPO_A: [_open_issue(10)]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [INTAKE_REPO_A])
    monkeypatch.setattr(epic_gate.drift, "build_findings",
                        lambda repo_root, home: ["epic-gate: TRAILS origin/main (at aaa, origin/main at bbb)",
                                                  "attended-session: not readable from this host — "
                                                  "no cross-host read"])
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", lambda repo_root, home: [])

    rc = epic_gate.main()
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("epic-gate: "), "the statement is still the first line"
    assert lines[1] == ("epic-gate: drift — epic-gate: TRAILS origin/main "
                        "(at aaa, origin/main at bbb)")
    assert lines[2] == ("epic-gate: drift — attended-session: not readable from this host — "
                        "no cross-host read")
    assert "nothing to do" in lines[3]


def test_main_prints_nothing_extra_when_the_build_drift_moment_is_clean(capsys, monkeypatch):
    # every reach for `gh` is injected — the suite never touches the live board (CI has no token; the
    # build host's credentials must not be what makes a test pass)
    monkeypatch.setattr(epic_gate, "_gh", FakeIntakeGh([], {}, open_issues={}))
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])
    monkeypatch.setattr(epic_gate.drift, "build_findings", lambda repo_root, home: [])
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", lambda repo_root, home: [])
    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "drift" not in out.lower()


def test_main_exit_code_is_unaffected_by_drift_findings_never_a_gate(capsys, monkeypatch):
    """Advisory: drift findings are printed, but the sweep's own exit code and actions never change
    because of them — the alarm is never part of check_cmd, CI, or any merge condition."""
    monkeypatch.setattr(epic_gate, "_gh", FakeIntakeGh([], {}, open_issues={}))
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])
    monkeypatch.setattr(epic_gate.drift, "build_findings",
                        lambda repo_root, home: ["surface: TRAILS origin/main (at a, origin/main at b)"])
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", lambda repo_root, home: [])
    rc = epic_gate.main()
    assert rc == 0


def test_main_passes_dispatch_dev_runner_home_and_the_factorys_own_root_to_build_findings(monkeypatch):
    seen = {}

    def fake(repo_root, home):
        seen["repo_root"], seen["home"] = repo_root, home
        return []

    monkeypatch.setattr(epic_gate, "_gh", FakeIntakeGh([], {}, open_issues={}))
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])
    monkeypatch.setattr(epic_gate.drift, "build_findings", fake)
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", lambda repo_root, home: [])
    epic_gate.main()
    assert seen["repo_root"] == ROOT
    assert seen["home"] == epic_gate.dispatch.DEV_RUNNER_HOME


# ============================================================================
# it-33 slice 6 (issue #462) — the sweep ALSO folds in the deploy-record comparison, readable only
# here: printed the same way as build_findings' own lines, advisory only.
# ============================================================================

def test_main_prints_deploy_record_findings_after_build_findings(capsys, monkeypatch):
    monkeypatch.setattr(epic_gate, "_gh", FakeIntakeGh([], {}, open_issues={}))
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])
    monkeypatch.setattr(epic_gate.drift, "build_findings",
                        lambda repo_root, home: ["epic-gate: TRAILS origin/main (at a, origin/main at b)"])
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings",
                        lambda repo_root, home: ["deploy-record: dispatch: DISAGREES (record says c, live states d)"])
    rc = epic_gate.main()
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "epic-gate: drift — epic-gate: TRAILS origin/main (at a, origin/main at b)"
    assert lines[2] == ("epic-gate: drift — deploy-record: dispatch: DISAGREES "
                        "(record says c, live states d)")
    assert "nothing to do" in lines[3]


def test_main_passes_dispatch_dev_runner_home_and_the_factorys_own_root_to_deploy_record_findings(monkeypatch):
    seen = {}

    def fake(repo_root, home):
        seen["repo_root"], seen["home"] = repo_root, home
        return []

    monkeypatch.setattr(epic_gate, "_gh", FakeIntakeGh([], {}, open_issues={}))
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])
    monkeypatch.setattr(epic_gate.drift, "build_findings", lambda repo_root, home: [])
    monkeypatch.setattr(epic_gate.drift, "deploy_record_findings", fake)
    epic_gate.main()
    assert seen["repo_root"] == ROOT
    assert seen["home"] == epic_gate.dispatch.DEV_RUNNER_HOME


def test_main_never_reaches_gh_for_464_by_default(monkeypatch):
    """Structural pin for the module's `_no_deploy_record_gh_reach` autouse fixture: with NO
    per-test override, `main()`'s call into `deploy_record_findings` must never fall through to
    `tools/sources.py`'s real `gh` subprocess seam. `sources.issue_trail` is patched to explode if
    reached at all; the autouse fixture's stub (returning `[]` without calling `issue_trail`)
    must make this a no-op. If the autouse fixture is ever removed or narrowed, this test is the
    one that catches it — not a live `gh` reach discovered later on the build host."""
    def _boom(repo, issue):
        raise AssertionError(f"main() reached gh for {repo}#{issue} without a test-injected trail")

    monkeypatch.setattr(epic_gate.drift.sources, "issue_trail", _boom)
    monkeypatch.setattr(epic_gate, "_gh", FakeIntakeGh([], {}, open_issues={}))
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])
    monkeypatch.setattr(epic_gate.drift, "build_findings", lambda repo_root, home: [])
    # deploy_record_findings deliberately left to the autouse fixture's default stub above.
    rc = epic_gate.main()
    assert rc == 0


# ============================================================================
# Issue #125 — the admission wall: a Ready item headed for a repo with no `.yr/factory.toml` at the
# base ref is refused fail-closed (Needs-info naming onboarding) instead of promoted/left dispatchable.
# ============================================================================

NOT_ONBOARDED_REPO = "yellow-robots/not-onboarded"


def _onboarding_body_asserts(body):
    """The comment must state the repo isn't onboarded, name the non-delegable acts, and state the
    resume — the acceptance criteria's letter, not any particular wording."""
    low = body.lower()
    assert "onboard" in low
    assert "auth" in low and "arming" in low
    assert "factory.toml" in low


# ---- the manifest probe itself: contents-API read, any failure = missing, cached per sweep -------------

def test_repo_has_manifest_true_on_a_successful_contents_read():
    seen = []

    def gh(argv):
        seen.append(argv)
        return 'check_cmd = "pytest"\n'

    assert epic_gate._repo_has_manifest(gh, "yellow-robots", "widget") is True
    assert seen[0][:2] == ["api", "repos/yellow-robots/widget/contents/.yr/factory.toml"]


def test_repo_has_manifest_false_on_any_read_failure():
    def gh(argv):
        raise RuntimeError("gh api ... failed (404): Not Found")

    assert epic_gate._repo_has_manifest(gh, "yellow-robots", "widget") is False


def test_repo_onboarded_caches_per_repo_within_one_sweep():
    calls = []

    def gh(argv):
        calls.append(argv)
        return "onboarded\n"

    cache = {}
    assert epic_gate._repo_onboarded(gh, "yellow-robots/widget", cache) is True
    assert epic_gate._repo_onboarded(gh, "yellow-robots/widget", cache) is True
    assert len(calls) == 1                                 # one contents read for the repo, not two


# ---- probe hit: no bounce, promotion proceeds exactly as today -----------------------------------------

def test_admission_wall_probe_hit_promotes_as_today():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    fake = FakeGh(board, epics, manifest_repos={REPO: 'check_cmd = "pytest"\n'})
    _sweep(fake)
    assert fake.edits == [("PI-101", STATUS_FIELD, "Ready")]
    assert len(fake.comments) == 1 and "YR-AUTO-PROMOTED" in fake.comments[0][2]


def test_admission_wall_leaves_an_onboarded_standalone_ready_item_untouched():
    """A standalone Ready item on an ONBOARDED repo is inspected by the wall (probe hit) and then simply
    left alone — cord-pull for standalone work stays intact; the wall adds a refusal, never a new touch."""
    board = [_item(300, item_id="EI-300", itype="Task", status="Ready", repo=REPO)]
    fake = FakeGh(board, {}, manifest_repos={REPO: 'check_cmd = "pytest"\n'})
    actions = _sweep(fake)
    assert fake.edits == [] and fake.comments == []
    assert not any(a.get("item") == 300 for a in actions)


# ---- probe miss on an epic child about to be promoted: the EPIC bounces, the child never promotes ------

def test_admission_wall_probe_miss_bounces_epic_not_child():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", repo=NOT_ONBOARDED_REPO)]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog",
                                                 repo=NOT_ONBOARDED_REPO)])}
    fake = FakeGh(board, epics, manifest_repos={})          # NOT_ONBOARDED_REPO carries no manifest
    actions = _sweep(fake)

    assert _status_ready_edits(fake) == []                  # the child is never promoted
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    _onboarding_body_asserts(epic_comments[0][2])
    assert {"epic": 100, "action": "raise", "reason": "Needs-info"} in actions


def test_admission_wall_epic_bounce_is_idempotent_across_ticks():
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", repo=NOT_ONBOARDED_REPO)]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog",
                                                 repo=NOT_ONBOARDED_REPO)])}
    fake = FakeGh(board, epics, manifest_repos={})
    _sweep(fake)
    assert len(fake.comments) == 1
    second_actions = _sweep(fake)                           # a genuine second tick on the same fake
    assert len(fake.comments) == 1                          # no duplicate comment
    # the epic itself is never re-raised (a "debt-count" action for the repo's Feature item still runs
    # every tick — an unrelated, pre-existing mechanism this task leaves untouched).
    assert not any(a.get("action") == "raise" for a in second_actions)


# ---- probe miss on an already-Ready standalone item: it bounces itself, off the Ready poll --------------

def test_admission_wall_standalone_probe_miss_bounces_both_fields():
    board = [_item(300, item_id="EI-300", itype="Task", status="Ready", repo=NOT_ONBOARDED_REPO)]
    fake = FakeGh(board, {}, manifest_repos={})
    actions = _sweep(fake)

    assert ("EI-300", STATUS_FIELD, "Backlog") in fake.edits
    assert ("EI-300", REASON_FIELD, "NeedsInfo") in fake.edits
    comments = [c for c in fake.comments if c[1] == "300"]
    assert len(comments) == 1
    _onboarding_body_asserts(comments[0][2])
    assert {"item": 300, "action": "bounce-standalone", "reason": "Needs-info"} in actions
    # it leaves the Ready poll: the board item's own Status field is no longer Ready
    assert fake.board_nodes[0]["status"] == {"name": "Backlog"}


def test_admission_wall_standalone_bounce_is_idempotent_across_ticks():
    board = [_item(300, item_id="EI-300", itype="Task", status="Ready", repo=NOT_ONBOARDED_REPO)]
    fake = FakeGh(board, {}, manifest_repos={})
    _sweep(fake)
    assert len(fake.comments) == 1
    second_actions = _sweep(fake)                           # Status is now Backlog -- no longer a candidate
    assert len(fake.comments) == 1                          # no duplicate comment
    assert second_actions == []


def test_admission_wall_never_silently_skips_a_ready_standalone_item():
    """A Ready item whose repo fails the probe always leaves a board write behind — silent skip (a Ready
    item left untouched, un-bounced) is the starvation shape the acceptance criteria forbids."""
    board = [_item(300, item_id="EI-300", itype="Task", status="Ready", repo=NOT_ONBOARDED_REPO)]
    fake = FakeGh(board, {}, manifest_repos={})
    actions = _sweep(fake)
    assert fake.edits or fake.comments                      # some write happened
    assert any(a.get("action") == "bounce-standalone" for a in actions)


# ---- other Ready work on other (onboarded) repos is unaffected in the very same sweep -------------------

def test_admission_wall_bounce_on_one_repo_does_not_affect_another_repos_promotion():
    board = [
        _item(100, item_id="EI-100", itype="Feature", status="Ready", repo=REPO),
        _item(400, item_id="EI-400", itype="Feature", status="Ready", repo=NOT_ONBOARDED_REPO),
    ]
    epics = {
        100: _epic_detail(comments=[VALID_RECORD],
                          children=[_child(101, pi_id="PI-101", status="Backlog", repo=REPO)]),
        400: _epic_detail(comments=[VALID_RECORD],
                          children=[_child(401, pi_id="PI-401", status="Backlog", repo=NOT_ONBOARDED_REPO)]),
    }
    fake = FakeGh(board, epics, manifest_repos={REPO: 'check_cmd = "pytest"\n'})
    actions = _sweep(fake)
    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits          # #100's child still promotes
    assert not any(e[0] == "PI-401" for e in fake.edits)            # #400's child never promotes
    assert ("EI-400", REASON_FIELD, "NeedsInfo") in fake.edits
    kinds = {a["action"] for a in actions}
    assert "promote" in kinds and "raise" in kinds


# ---- the probe is cached per repo within one sweep: two Ready candidates, one contents read ------------

def test_admission_wall_probe_cached_across_two_candidates_on_the_same_repo():
    """Two standalone (non-Feature) Ready candidates on the same repo — kept off the debt counter's own,
    unrelated per-repo contents read (issue #47, Feature-only) so this pins ONLY the admission wall's
    own cache."""
    board = [
        _item(300, item_id="EI-300", itype="Task", status="Ready", repo=NOT_ONBOARDED_REPO),
        _item(301, item_id="EI-301", itype="Task", status="Ready", repo=NOT_ONBOARDED_REPO),
    ]
    fake = FakeGh(board, {}, manifest_repos={})
    _sweep(fake)
    manifest_calls = [a for a in fake.manifest_argv if NOT_ONBOARDED_REPO in a[1]]
    assert len(manifest_calls) == 1                         # one contents read for the repo, not two


# ============================================================================
# Issue #140 — the probe distinguishes a confirmed 404 (definitively absent) from a transient failure
# (network error, 5xx, rate limit, timeout): only the confirmed case reads as not-onboarded. A transient
# failure retries with a short bounded backoff; if it still fails, the caller must not treat the repo as
# not-onboarded — no bounce, no comment, no board write, and no caching of the failure as "absent".
# ============================================================================

def test_repo_has_manifest_retries_a_transient_failure_then_succeeds(monkeypatch):
    """A non-404 failure (network/5xx/timeout) on the first attempt is retried; success on retry reads
    exactly like a first-try hit -- True, no different treatment."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    calls = []

    def gh(argv):
        calls.append(argv)
        if len(calls) == 1:
            raise RuntimeError("gh: connection reset by peer")
        return 'check_cmd = "pytest"\n'

    assert epic_gate._repo_has_manifest(gh, "yellow-robots", "widget") is True
    assert len(calls) == 2


def test_repo_has_manifest_confirmed_404_returns_false_without_retrying(monkeypatch):
    """A confirmed 404 is definitive -- no retry/backoff is burned on it, unlike a transient failure."""
    sleeps = []
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: sleeps.append(s))
    calls = []

    def gh(argv):
        calls.append(argv)
        raise RuntimeError("gh api ... failed (HTTP 404): Not Found")

    assert epic_gate._repo_has_manifest(gh, "yellow-robots", "widget") is False
    assert len(calls) == 1
    assert sleeps == []


def test_repo_has_manifest_persistent_non_404_failure_raises_probe_error(monkeypatch):
    """A non-404 failure that survives every attempt raises `ManifestProbeError` -- never `False`: the
    caller must not be able to read this as a confirmed absence."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)

    def gh(argv):
        raise RuntimeError("gh: 503 Service Unavailable")

    with pytest.raises(epic_gate.ManifestProbeError):
        epic_gate._repo_has_manifest(gh, "yellow-robots", "widget")


def test_repo_onboarded_does_not_cache_a_probe_failure(monkeypatch):
    """A `ManifestProbeError` propagates through `_repo_onboarded` uncached -- unlike a confirmed
    True/False it is never stored in the sweep-local cache, so the next read for the same repo probes
    again instead of the failure freezing in as 'absent' for the rest of the sweep."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    calls = []

    def gh(argv):
        calls.append(argv)
        raise RuntimeError("gh: 500 Internal Server Error")

    cache = {}
    with pytest.raises(epic_gate.ManifestProbeError):
        epic_gate._repo_onboarded(gh, "yellow-robots/widget", cache)
    assert cache == {}
    first_call_count = len(calls)

    with pytest.raises(epic_gate.ManifestProbeError):
        epic_gate._repo_onboarded(gh, "yellow-robots/widget", cache)
    assert len(calls) > first_call_count            # re-probed, not short-circuited by a cached failure


TRANSIENT_REPO = "yellow-robots/transient"


def test_admission_wall_epic_child_probe_retries_transient_then_promotes(monkeypatch):
    """The onboarded-but-flaky case: the probe fails once (transient) then succeeds on retry -- the repo
    reads as onboarded, exactly like a first-try hit; no bounce, no probe-error action."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", repo=TRANSIENT_REPO)]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog",
                                                 repo=TRANSIENT_REPO)])}
    fake = FakeGh(board, epics,
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: timeout"), 'check_cmd = "pytest"\n']})
    actions = _sweep(fake)

    assert ("PI-101", STATUS_FIELD, "Ready") in fake.edits
    assert not any(a.get("action") in ("raise", "probe-error") for a in actions)
    assert not any(e[1] == REASON_FIELD for e in fake.edits)          # epic never bounced


def test_admission_wall_epic_child_probe_persistent_failure_skips_without_bounce(monkeypatch):
    """A probe failure that survives every retry is NOT read as not-onboarded: the epic is left exactly
    where it is -- no Reason edit, no comment, no promotion -- and the skip surfaces as its own
    'probe-error' action naming the epic and the child."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", repo=TRANSIENT_REPO)]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog",
                                                 repo=TRANSIENT_REPO)])}
    fake = FakeGh(board, epics,
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: 503 Service Unavailable")]})
    actions = _sweep(fake)

    assert fake.edits == []                          # nothing promoted, epic never bounced
    assert fake.comments == []                        # no onboarding comment, no promotion comment
    probe_actions = [a for a in actions if a.get("action") == "probe-error"]
    assert len(probe_actions) == 1
    assert probe_actions[0]["epic"] == 100 and probe_actions[0]["child"] == 101
    assert "error" in probe_actions[0]


def test_admission_wall_never_posts_the_onboarding_comment_on_a_probe_error_path(monkeypatch):
    """`_not_onboarded_body()`'s onboarding message stays exclusive to the confirmed-404 case -- neither
    a probe-error on an epic child nor on a standalone item posts any comment."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [
        _item(100, item_id="EI-100", itype="Feature", status="Ready", repo=TRANSIENT_REPO),
        _item(300, item_id="EI-300", itype="Task", status="Ready", repo=TRANSIENT_REPO),
    ]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog",
                                                 repo=TRANSIENT_REPO)])}
    fake = FakeGh(board, epics,
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: 503 Service Unavailable")]})
    _sweep(fake)
    assert fake.comments == []


def test_admission_wall_standalone_probe_persistent_failure_skips_writing_nothing(monkeypatch):
    """A standalone Ready item on a repo whose probe persistently fails (non-404) is left exactly where
    it is -- no Status/Reason edit, no comment -- and the skip surfaces as a 'probe-error' action naming
    the item, distinct from a 'bounce-standalone'."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [_item(300, item_id="EI-300", itype="Task", status="Ready", repo=TRANSIENT_REPO)]
    fake = FakeGh(board, {},
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: 500 Internal Server Error")]})
    actions = _sweep(fake)

    assert fake.edits == [] and fake.comments == []
    assert fake.board_nodes[0]["status"] == {"name": "Ready"}   # untouched -- stays put for the next sweep
    probe_actions = [a for a in actions if a.get("action") == "probe-error"]
    assert len(probe_actions) == 1
    assert probe_actions[0]["item"] == 300
    assert "child" not in probe_actions[0]
    assert not any(a.get("action") == "bounce-standalone" for a in actions)


def test_admission_wall_probe_failure_on_one_candidate_does_not_poison_a_later_read_same_sweep(monkeypatch):
    """Two standalone Ready candidates share a repo whose probe fails on the first candidate's own two
    attempts then recovers: the second candidate's read is NOT short-circuited by a cached 'absent' from
    the first's failure -- it re-probes and (network recovered) reads onboarded, left untouched."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [
        _item(300, item_id="EI-300", itype="Task", status="Ready", repo=TRANSIENT_REPO),
        _item(301, item_id="EI-301", itype="Task", status="Ready", repo=TRANSIENT_REPO),
    ]
    fake = FakeGh(board, {}, manifest_errors={
        TRANSIENT_REPO: [RuntimeError("gh: timeout"), RuntimeError("gh: timeout"),
                         'check_cmd = "pytest"\n'],
    })
    actions = _sweep(fake)

    probe_actions = [a for a in actions if a.get("action") == "probe-error"]
    assert len(probe_actions) == 1 and probe_actions[0]["item"] == 300
    # #301 was never bounced NOR probe-errored -- its own (later, uncached) read simply succeeded
    assert not any(a.get("item") == 301 for a in actions)
    assert not any(c[1] == "301" for c in fake.comments)
    assert not any(e[0] == "EI-301" for e in fake.edits)


def test_admission_wall_probe_failure_for_persistent_repo_reprobes_across_two_candidates(monkeypatch):
    """When the repo's probe fails persistently (never recovers within the sweep), EVERY candidate on it
    gets its own fresh probe attempts and its own 'probe-error' action -- proving the earlier failure was
    never cached as a confirmed absence for the repo."""
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [
        _item(300, item_id="EI-300", itype="Task", status="Ready", repo=TRANSIENT_REPO),
        _item(301, item_id="EI-301", itype="Task", status="Ready", repo=TRANSIENT_REPO),
    ]
    fake = FakeGh(board, {},
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: 500 Internal Server Error")]})
    actions = _sweep(fake)

    probe_items = {a["item"] for a in actions if a.get("action") == "probe-error"}
    assert probe_items == {300, 301}
    assert fake.edits == [] and fake.comments == []
    manifest_calls = [a for a in fake.manifest_argv if TRANSIENT_REPO in a[1]]
    assert len(manifest_calls) == 4                  # 2 candidates x 2 attempts each -- no cached failure


def test_main_prints_probe_failure_for_a_standalone_item(monkeypatch, capsys):
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [_item(300, item_id="EI-300", itype="Task", status="Ready", repo=TRANSIENT_REPO)]
    fake = FakeGh(board, {},
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: 500 Internal Server Error")]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])

    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "probe" in out.lower() and "300" in out
    assert "not onboarded" not in out.lower()


def test_main_prints_probe_failure_for_an_epic_child(monkeypatch, capsys):
    monkeypatch.setattr(epic_gate.time, "sleep", lambda s: None)
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", repo=TRANSIENT_REPO)]
    epics = {100: _epic_detail(comments=[VALID_RECORD],
                               children=[_child(101, pi_id="PI-101", status="Backlog",
                                                 repo=TRANSIENT_REPO)])}
    fake = FakeGh(board, epics,
                  manifest_errors={TRANSIENT_REPO: [RuntimeError("gh: 503 Service Unavailable")]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [])

    rc = epic_gate.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "probe" in out.lower() and "100" in out and "101" in out


def test_main_uses_registered_repos_for_intake(capsys, monkeypatch):
    """`main()` sweeps exactly the repos `_registered_repos()` names -- never a repo outside that
    list, and never skips one inside it."""
    fake = FakeIntakeGh([], {}, open_issues={INTAKE_REPO_A: [_open_issue(1)]})
    monkeypatch.setattr(epic_gate, "_gh", fake)
    monkeypatch.setattr(epic_gate, "_registered_repos", lambda: [INTAKE_REPO_A])

    rc = epic_gate.main()
    assert rc == 0
    assert [_flags(a)["--repo"] for a in fake.issue_list_argv] == [INTAKE_REPO_A]


# ============================================================================
# Issue #342 — every epic-gate refusal records itself, even under a Reason a different refusal set.
#
# Each of the three per-epic refusal sites (missing approval, first-open-child-not-a-Task, the
# admission-wall epic-child bounce) must post its OWN comment keyed on the presence of its OWN marker
# line among the epic's already-fetched comments, and make its field write keyed independently on the
# epic's CURRENT Reason value -- so a stale Reason left behind by a *different* refusal never suppresses
# this refusal's own comment, and a marker already on record never suppresses a still-needed field
# correction. No test here asserts a Reason was ever cleared -- the sweep never clears one.
# ============================================================================

NO_APPROVAL_MARKER = "YR-EPIC-GATE: no-approval"
NOT_A_TASK_MARKER = "YR-EPIC-GATE: not-a-task"
NOT_ONBOARDED_MARKER = "YR-EPIC-GATE: not-onboarded"


def _no_approval_setup(*, comments, epic_reason=None):
    """An epic with an invalid/missing approval record -- site (1)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", reason=epic_reason)]
    epics = {100: _epic_detail(comments=comments,
                               children=[_child(101, pi_id="PI-101", status="Backlog")])}
    return board, epics


def _not_a_task_setup(*, comments, epic_reason=None):
    """A validly-approved epic whose first open child is not a Task -- site (3)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", reason=epic_reason)]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD] + list(comments),
        children=[_child(101, itype="Feature", pi_id="PI-101", status="Backlog"),
                  _child(102, itype="Task", pi_id="PI-102", status="Backlog")])}
    return board, epics


def _not_onboarded_setup(*, comments, epic_reason=None):
    """A validly-approved epic whose first open (Task) child sits on a repo with no manifest -- the
    admission wall's epic-child bounce, site (5)."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready", repo=NOT_ONBOARDED_REPO,
                   reason=epic_reason)]
    epics = {100: _epic_detail(
        comments=[VALID_RECORD] + list(comments),
        children=[_child(101, pi_id="PI-101", status="Backlog", repo=NOT_ONBOARDED_REPO)])}
    return board, epics


# ---- each site posts its own record even though the epic already carries a Reason a DIFFERENT ----------
# ---- refusal would have set (a stale value distinct from this site's own target) ------------------------

def test_no_approval_posts_its_own_comment_under_a_stale_different_reason():
    board, epics = _no_approval_setup(comments=["just a normal comment, no sentinel"],
                                       epic_reason="Blocked")   # stale, not this site's own target
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NO_APPROVAL_MARKER
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits   # corrected to this site's own target


def test_not_a_task_posts_its_own_comment_under_a_stale_different_reason():
    board, epics = _not_a_task_setup(comments=[], epic_reason="Needs-info")   # stale, not "Blocked"
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NOT_A_TASK_MARKER
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits


def test_not_onboarded_posts_its_own_comment_under_a_stale_different_reason():
    board, epics = _not_onboarded_setup(comments=[], epic_reason="Blocked")   # stale, not "Needs-info"
    fake = FakeGh(board, epics, manifest_repos={})
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NOT_ONBOARDED_MARKER
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits


# ---- each site makes NO field write once the Reason already holds the value it would set (the ----------
# ---- comment still posts if its own marker is not yet on record -- the debt-hold shape, applied here) --

def test_no_approval_makes_no_field_write_when_reason_already_needs_info():
    board, epics = _no_approval_setup(comments=["just a normal comment, no sentinel"],
                                       epic_reason="Needs-info")
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NO_APPROVAL_MARKER
    assert not any(e[0] == "EI-100" for e in fake.edits)


def test_not_a_task_makes_no_field_write_when_reason_already_blocked():
    board, epics = _not_a_task_setup(comments=[], epic_reason="Blocked")
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NOT_A_TASK_MARKER
    assert not any(e[0] == "EI-100" for e in fake.edits)


def test_not_onboarded_makes_no_field_write_when_reason_already_needs_info():
    board, epics = _not_onboarded_setup(comments=[], epic_reason="Needs-info")
    fake = FakeGh(board, epics, manifest_repos={})
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NOT_ONBOARDED_MARKER
    assert not any(e[0] == "EI-100" for e in fake.edits)


# ---- once a site's own marker is already on record, it posts no duplicate -- but its field write --------
# ---- still runs independently, keyed on the current Reason value alone (proves the two keys are ---------
# ---- genuinely independent, not just both happening to agree) --------------------------------------------

def test_no_approval_posts_no_duplicate_once_its_marker_is_on_record_but_still_corrects_a_stale_field():
    board, epics = _no_approval_setup(comments=[NO_APPROVAL_MARKER], epic_reason="Blocked")
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.comments == []                                 # marker already present -> no re-post
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits  # field still corrected


def test_not_a_task_posts_no_duplicate_once_its_marker_is_on_record_but_still_corrects_a_stale_field():
    board, epics = _not_a_task_setup(comments=[NOT_A_TASK_MARKER], epic_reason="Needs-info")
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.comments == []
    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits


def test_not_onboarded_posts_no_duplicate_once_its_marker_is_on_record_but_still_corrects_a_stale_field():
    board, epics = _not_onboarded_setup(comments=[NOT_ONBOARDED_MARKER], epic_reason="Blocked")
    fake = FakeGh(board, epics, manifest_repos={})
    _sweep(fake)
    assert fake.comments == []
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits


# ---- marker matching tolerates NO leading whitespace -- an indented echo of the marker (e.g. quoted ------
# ---- in a reply) must not satisfy the key, so the site's own comment still posts --------------------------

def test_no_approval_indented_marker_does_not_satisfy_the_key():
    board, epics = _no_approval_setup(comments=[" " + NO_APPROVAL_MARKER])
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1                              # the indent did not suppress the post
    assert epic_comments[0][2].splitlines()[0] == NO_APPROVAL_MARKER


def test_not_a_task_indented_marker_does_not_satisfy_the_key():
    board, epics = _not_a_task_setup(comments=[" " + NOT_A_TASK_MARKER])
    fake = FakeGh(board, epics)
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NOT_A_TASK_MARKER


def test_not_onboarded_indented_marker_does_not_satisfy_the_key():
    board, epics = _not_onboarded_setup(comments=[" " + NOT_ONBOARDED_MARKER])
    fake = FakeGh(board, epics, manifest_repos={})
    _sweep(fake)
    epic_comments = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments) == 1
    assert epic_comments[0][2].splitlines()[0] == NOT_ONBOARDED_MARKER


# ---- the three markers are pairwise distinct and match the exact literal text specified -----------------

def test_the_three_refusal_markers_are_pairwise_distinct_and_match_the_spec_literal():
    board1, epics1 = _no_approval_setup(comments=["no sentinel here"])
    fake1 = FakeGh(board1, epics1)
    _sweep(fake1)
    line1 = fake1.comments[0][2].splitlines()[0]

    board2, epics2 = _not_a_task_setup(comments=[])
    fake2 = FakeGh(board2, epics2)
    _sweep(fake2)
    line2 = fake2.comments[0][2].splitlines()[0]

    board3, epics3 = _not_onboarded_setup(comments=[])
    fake3 = FakeGh(board3, epics3, manifest_repos={})
    _sweep(fake3)
    line3 = fake3.comments[0][2].splitlines()[0]

    assert (line1, line2, line3) == (NO_APPROVAL_MARKER, NOT_A_TASK_MARKER, NOT_ONBOARDED_MARKER)
    assert len({line1, line2, line3}) == 3


# ---- the headline scenario: a first refusal raises the epic, then a genuinely DIFFERENT refusal fires ---
# ---- on a later tick and is not silently swallowed by the epic already carrying a Reason -----------------

def test_a_different_refusal_on_a_later_tick_still_posts_its_own_comment():
    """Tick 1: no valid approval record -> raises Needs-info, posts the no-approval marker. Tick 2: a
    human adds a valid approval record, but the next open child turns out not to be a Task -> a
    DIFFERENT refusal fires. It must still post its own comment and correct the Reason to its own
    target, not be silently suppressed by the epic already carrying Needs-info from tick 1."""
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=["no sentinel here"],
        children=[_child(101, itype="Feature", pi_id="PI-101", status="Backlog"),
                  _child(102, itype="Task", pi_id="PI-102", status="Backlog")])}
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    epic_comments_after_1 = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments_after_1) == 1
    assert epic_comments_after_1[0][2].splitlines()[0] == NO_APPROVAL_MARKER

    # a human adds a valid approval record between ticks; the epic still carries stale Needs-info
    epics[100]["comments"]["nodes"].append({"body": VALID_RECORD})
    second_actions = _sweep(fake)

    assert ("EI-100", REASON_FIELD, "Blocked") in fake.edits    # corrected to the SECOND site's target
    epic_comments_after_2 = [c for c in fake.comments if c[1] == "100"]
    assert len(epic_comments_after_2) == 2                      # the first comment is untouched, +1 new
    assert epic_comments_after_2[0] == epic_comments_after_1[0]
    assert epic_comments_after_2[1][2].splitlines()[0] == NOT_A_TASK_MARKER
    assert {"epic": 100, "action": "raise", "reason": "Blocked"} in second_actions


# ============================================================================
# it-31 slice 9 (#441) — the close arm: a finished non-debt epic holds until its close records exist
# (the model's compiled close-lane mandates, judged by the detector's own core; the debt hold at the
# branch above is the exemplar and stays byte-identical)

def _finished_feature_epic(comments):
    board = [_item(100, item_id="EI-100", itype="Feature", status="Ready")]
    epics = {100: _epic_detail(
        comments=comments,
        children=[_child(101, state="CLOSED", pi_id="PI-101")])}
    epics[100]["subIssues"]["nodes"][0]["stateReason"] = "COMPLETED"
    return board, epics


def test_finished_epic_without_close_records_holds_naming_each():
    board, epics = _finished_feature_epic([VALID_RECORD])
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == []                                 # never closed without the records
    body = _epic_comment_text(fake)
    assert body.splitlines()[0] == "YR-CLOSE-HOLD"
    assert "YR-ROUND-RECORD" in body and "YR-SHIP-WALK" in body
    assert ("EI-100", REASON_FIELD, "NeedsInfo") in fake.edits
    assert {"epic": 100, "action": "hold-close", "missing": 2} in actions


def test_close_hold_body_carries_the_sweep_own_commit_statement():
    """it-33 slice 3 (epic #455): YR-CLOSE-HOLD gained `commit` in records.toml's `fields` — line 0
    stays exactly the sentinel marker (mode=sentinel is whole-line equality), the `commit:` field
    rides line 1, indented so it never reads as one more '- '-prefixed finding bullet."""
    import check_trail
    import records as records_mod
    body = epic_gate._close_hold_body(["close: YR-ROUND-RECORD: mandated record absent (marker "
                                       "'YR-ROUND-RECORD:', mode prefix)"])
    lines = body.splitlines()
    assert lines[0] == "YR-CLOSE-HOLD"
    assert lines[1] == f"  {epic_gate.COMMIT_STATEMENT}"
    reg = records_mod.load()
    row = records_mod.get(reg, "YR-CLOSE-HOLD")
    assert check_trail._missing_fields(row, [body]) == []


# it-33 slice 3 (epic #455): every YR-EPIC-GATE raise-family row gained `commit` in records.toml's
# `fields` — one pin per emitter, each checked against the LIVE registry's own field grammar.
def test_every_epic_gate_raise_body_carries_the_commit_field():
    import check_trail
    import records as records_mod
    reg = records_mod.load()
    cases = {
        "YR-EPIC-GATE: no-approval": epic_gate._needs_info_body("no comment carries the record"),
        "YR-EPIC-GATE: not-a-task": epic_gate._not_a_task_body(101),
        "YR-EPIC-GATE: not-onboarded": epic_gate._not_onboarded_body(),
        "YR-EPIC-GATE: open-questions": epic_gate._open_questions_body([(3, "YR-OPEN-QUESTION: x")]),
        "YR-EPIC-GATE: gate-touching": epic_gate._gate_touching_body(101, "touches check_cmd"),
        "YR-EPIC-GATE: stranded claim": epic_gate._stranded_body(60.0),
    }
    for name, body in cases.items():
        row = records_mod.get(reg, name)
        assert check_trail._marker_present(row, [body]), name
        assert check_trail._missing_fields(row, [body]) == [], name


def test_close_hold_comment_and_reason_set_exactly_once_across_ticks():
    board, epics = _finished_feature_epic([VALID_RECORD])
    fake = FakeGh(board, epics)
    _sweep(fake)
    after_1 = [c for c in fake.comments if c[1] == "100"]
    assert len(after_1) == 1
    _sweep(fake)
    assert [c for c in fake.comments if c[1] == "100"] == after_1     # no duplicate
    assert fake.closes == []


def test_finished_epic_with_close_records_closes_as_before():
    board, epics = _finished_feature_epic([VALID_RECORD, CLOSE_RECORDS])
    fake = FakeGh(board, epics)
    actions = _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]
    assert fake.comments == []
    assert {"epic": 100, "action": "close", "reason": "completed"} in actions


def test_close_records_split_across_two_comments_also_satisfy():
    """Each record complete within ONE text (the field-pooling rule) — but the two records may ride
    separate comments."""
    round_rec = ("YR-ROUND-RECORD: counts\nrefusals: 1\nrecords-demanded: 2\n"
                 "detector-findings: 0\nescalations: 0\ndeployed: none\n")
    walk_rec = "YR-SHIP-WALK: walked\nwho: @human\nscope: epic\n"
    board, epics = _finished_feature_epic([VALID_RECORD, round_rec, walk_rec])
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]


def test_incomplete_round_record_still_holds():
    """Grammar, not just presence: a marker with missing fields is a finding, and the hold names it."""
    partial = "YR-ROUND-RECORD: counts\nrefusals: 1\n" + CLOSE_RECORDS.split("\n\n")[1]
    board, epics = _finished_feature_epic([VALID_RECORD, partial])
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == []
    assert "records-demanded" in _epic_comment_text(fake)


def test_close_hold_body_never_satisfies_the_mandates_it_names():
    """The debt lesson, re-applied: the hold comment naming the missing records must not itself
    read as those records on the next tick."""
    import check_trail
    import records as records_mod
    board, epics = _finished_feature_epic([VALID_RECORD])
    fake = FakeGh(board, epics)
    _sweep(fake)
    hold_body = _epic_comment_text(fake)
    reg = records_mod.load()
    findings = check_trail.check_texts(reg, "close", {"issue-trail": [hold_body]},
                                       lanes_map=records_mod.lanes(reg),
                                       forbids_map=records_mod.lane_forbids(reg))
    assert findings, "the hold comment satisfied the very mandates it names"


def test_debt_epic_close_duties_are_unchanged():
    """The debt sibling's behavior is unchanged (the acceptance's own words): a debt epic with a
    valid verdict closes WITHOUT close records — its hold is the ledger verdict's, exactly as
    today."""
    board, epics = _debt_epic_detail(comments=[VALID_LEDGER])
    fake = FakeGh(board, epics)
    _sweep(fake)
    assert fake.closes == [(REPO, "100", "completed")]


def test_unloadable_mandates_hold_fail_closed(monkeypatch):
    """A sweep that cannot read its mandates must not self-close — Needs-info over guessing."""
    board, epics = _finished_feature_epic([VALID_RECORD, CLOSE_RECORDS])
    fake = FakeGh(board, epics)
    import epic_gate as eg
    monkeypatch.setattr(eg.records, "load",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("registry down")))
    actions = _sweep(fake)
    assert fake.closes == []
    assert any(a.get("action") == "hold-close" for a in actions)
    assert "registry down" in _epic_comment_text(fake)


# ============================================================================
# it-33 slice 7 (#459) — the close arm's pin: a call-site census. Every epic-closing call site in
# tools/ (the argv form of an issue close, `gh issue close`, a `closeIssue` GraphQL mutation, or a
# `_close_issue(` invocation) must sit inside a function on the close-lane allow-list —
# `_close_issue` itself, and `_process_epic`, the close arm's caller. The allow-list is keyed by
# enclosing FUNCTION NAME, never by line number, so it survives reflow. This is a plain text
# census (the shape of test_architect_reconciliation_and_gate_locations.py:32): it reads file
# text via pathlib/re only and imports no module — it does not exercise epic_gate.py's behavior,
# only where its close calls are allowed to live. No change to tools/epic_gate.py itself; no
# cardinality rule — only that every match sits inside the allow-list.

_CLOSE_CALL_PATTERNS = [
    re.compile(r'\[\s*[\'"]issue[\'"]\s*,\s*[\'"]close[\'"]'),   # argv form: ["issue", "close", ...]
    re.compile(r'gh issue close\b'),
    re.compile(r'\bcloseIssue\b'),
    re.compile(r'_close_issue\('),
]

_CLOSE_ARM_ALLOW_LIST = {"_close_issue", "_process_epic"}

_DEF_LINE_RE = re.compile(r'^([ \t]*)def ([A-Za-z_][A-Za-z0-9_]*)\(', re.MULTILINE)


def _enclosing_function_name(text, line_no):
    """The name of the function enclosing 1-indexed `line_no` in `text` — the nearest `def` line,
    scanning backward from (and including) the target line, whose indentation is no deeper than
    the target line's own. No AST, no imports: a plain indentation scan, matched to this repo's
    flat, unindented top-level function style."""
    lines = text.splitlines()
    target_indent = len(lines[line_no - 1]) - len(lines[line_no - 1].lstrip(" \t"))
    for i in range(line_no - 1, -1, -1):
        m = _DEF_LINE_RE.match(lines[i])
        if m and len(m.group(1)) <= target_indent:
            return m.group(2)
    return None


def _close_call_sites(root_dir):
    """Every match of the close-call forms under `root_dir`, each tagged with its enclosing
    function name: a list of (path, line_no, matched_text, enclosing_function_name)."""
    sites = []
    for path in sorted(p for p in root_dir.rglob("*") if p.is_file()):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in _CLOSE_CALL_PATTERNS:
            for m in pattern.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                sites.append((path, line_no, m.group(0), _enclosing_function_name(text, line_no)))
    return sites


def test_census_finds_every_epic_closing_call_site_in_tools_inside_the_close_lane_allow_list():
    sites = _close_call_sites(ROOT / "tools")
    assert sites, "the census matched no close-call sites — the patterns have drifted from the real ones"
    violations = [s for s in sites if s[3] not in _CLOSE_ARM_ALLOW_LIST]
    assert violations == [], "\n".join(
        f"{p.relative_to(ROOT)}:{ln}: {matched!r} is not inside an allow-listed function "
        f"(found enclosing function {fn!r})"
        for p, ln, matched, fn in violations
    )


def test_census_names_the_path_and_line_of_a_new_unguarded_close_call_site(tmp_path):
    """A new call site OUTSIDE the allow-listed functions must fail the census, naming exactly
    where — proving the allow-list is genuinely keyed by function name, not merely by file."""
    rogue = tmp_path / "rogue.py"
    rogue.write_text(
        'def _some_other_function(gh, repo, number):\n'
        '    gh(["issue", "close", str(number), "--repo", repo])\n',
        encoding="utf-8",
    )
    sites = _close_call_sites(tmp_path)
    violations = [s for s in sites if s[3] not in _CLOSE_ARM_ALLOW_LIST]
    assert len(violations) == 1
    path, line_no, matched, fn = violations[0]
    assert path == rogue
    assert line_no == 2
    assert fn == "_some_other_function"
