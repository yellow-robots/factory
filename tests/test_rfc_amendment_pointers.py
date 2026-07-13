"""
Tests for Issue #153 — docs/rfcs: amendment pointers on 0002/0003/0004.

Derived from the Issue #153 acceptance criteria (the spec), not from the
implementation. Three drifted, frozen RFCs (0002, 0003, 0004) each gain a
house-style `**Amended <date>:**` clause on their status line (:3) pointing
at the shipped reality that superseded a named design/decision statement —
the ship-freeze holds, so the body itself must stay byte-identical apart
from that one line. 0004 already carries the 2026-07-10 #126 amendment
(pinned by tests/test_dispatch.py::test_rfc_0004_header_carries_the_per_repo_amendment_pointer,
which reads the file's first five lines for "amended" / "#126" / "per-repo"
/ "single.flight") — this issue appends a *second* clause alongside it
without disturbing those tokens or their position in the first five lines.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
RFC_0002 = ROOT / "docs" / "rfcs" / "0002-dev-ai-runner.md"
RFC_0003 = ROOT / "docs" / "rfcs" / "0003-task-state-model.md"
RFC_0004 = ROOT / "docs" / "rfcs" / "0004-dispatch.md"
AGENTS = ROOT / "AGENTS.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _status_line(path):
    lines = _text(path).splitlines()
    for line in lines:
        if line.startswith("**Status:**"):
            return line
    raise AssertionError(f"{path} has no '**Status:**' line")


def _first_five_lines(path):
    return "\n".join(_text(path).splitlines()[:5])


# ---------------------------------------------------------------------------
# 0002-dev-ai-runner.md — the single-`claude -p`-orchestrates-subagents
# design (:29) is superseded by the shipped per-stage cold-process runner
# ---------------------------------------------------------------------------

def test_rfc_0002_status_line_carries_an_amendment_clause():
    status = _status_line(RFC_0002)
    assert re.search(r"\*\*Amended \d{4}-\d{2}-\d{2}:\*\*", status), (
        "0002's status line is missing a '**Amended <date>:**' clause"
    )


def test_rfc_0002_amendment_names_the_superseded_orchestration_design():
    status = _status_line(RFC_0002)
    match = re.search(r"\*\*Amended[^·]*", status)
    assert match, "0002's status line has no amendment clause to inspect"
    clause = match.group(0)
    assert re.search(r"claude -p", clause), (
        "0002's amendment doesn't name the superseded 'claude -p' design"
    )
    assert re.search(r"subagent", clause, re.IGNORECASE), (
        "0002's amendment doesn't name the superseded internally-orchestrated-"
        "subagents design"
    )


def test_rfc_0002_amendment_points_at_the_shipped_per_stage_runner():
    status = _status_line(RFC_0002)
    match = re.search(r"\*\*Amended[^·]*", status)
    clause = match.group(0)
    assert "tools/dev-runner.sh" in clause, (
        "0002's amendment doesn't point at tools/dev-runner.sh as the shipped reality"
    )
    assert re.search(r"builder.+verifier|verifier.+builder", clause, re.IGNORECASE), (
        "0002's amendment doesn't record builder ≠ verifier as separate processes"
    )
    assert re.search(r"separate process|cold.process", clause, re.IGNORECASE), (
        "0002's amendment doesn't record the cold/separate-process shipped reality"
    )


def test_rfc_0002_original_status_prefix_is_undisturbed():
    status = _status_line(RFC_0002)
    assert status.startswith("**Status:** Accepted (2026-06-17)"), (
        "0002's original status prefix was rewritten instead of amended"
    )


def test_rfc_0002_decision_makers_and_builds_on_survive():
    status = _status_line(RFC_0002)
    assert "**Decision-makers:** Jose + Claude" in status
    assert "[0001-ticket-driven-dev-workflow](0001-ticket-driven-dev-workflow.md)" in status


def test_rfc_0002_body_frozen_statement_is_untouched():
    # The very design statement the amendment says is superseded (:29) must
    # still read verbatim in the body -- the ship-freeze holds, nothing is
    # rewritten out from under the pointer.
    text = _text(RFC_0002)
    assert (
        "A single `claude -p` run **internally orchestrates distinct roles "
        "as subagents**" in text
    ), "0002's frozen body statement at :29 was rewritten, not just pointed at"


def test_rfc_0002_context_paragraph_is_untouched():
    text = _text(RFC_0002)
    assert (
        "RFC 0001 defined the workflow: a *Ready* GitHub Issue is dispatched "
        "to a **dev-AI** that produces a PR." in text
    ), "0002's Context paragraph was edited"


def test_rfc_0002_amended_appears_only_on_the_status_line():
    lines = _text(RFC_0002).splitlines()
    amended_lines = [i for i, l in enumerate(lines) if "Amended" in l]
    assert amended_lines == [2], (
        f"'Amended' appears outside the status line (0-indexed line 2) in 0002: "
        f"found on lines {amended_lines}"
    )


# ---------------------------------------------------------------------------
# 0003-task-state-model.md — "Promotion to Ready is always a human/Joam
# decision" (:43) is superseded by the epic-gate's standing-approval
# promotion; standalone tasks keep human promotion
# ---------------------------------------------------------------------------

def test_rfc_0003_status_line_carries_an_amendment_clause():
    status = _status_line(RFC_0003)
    assert re.search(r"\*\*Amended \d{4}-\d{2}-\d{2}:\*\*", status), (
        "0003's status line is missing a '**Amended <date>:**' clause"
    )


def test_rfc_0003_amendment_names_the_superseded_promotion_statement():
    status = _status_line(RFC_0003)
    match = re.search(r"\*\*Amended[^·]*", status)
    assert match, "0003's status line has no amendment clause to inspect"
    clause = match.group(0)
    assert re.search(r"human", clause, re.IGNORECASE) and re.search(
        r"promot", clause, re.IGNORECASE
    ), "0003's amendment doesn't name the superseded human-promotion statement"


def test_rfc_0003_amendment_points_at_epic_gate_standing_approval():
    status = _status_line(RFC_0003)
    match = re.search(r"\*\*Amended[^·]*", status)
    clause = match.group(0)
    assert re.search(r"epic.gate", clause, re.IGNORECASE), (
        "0003's amendment doesn't name the epic-gate as the shipped reality"
    )
    assert re.search(r"standing.approval", clause, re.IGNORECASE), (
        "0003's amendment doesn't name standing-approval promotion"
    )
    assert re.search(r"standalone", clause, re.IGNORECASE), (
        "0003's amendment doesn't carve out that standalone tasks keep human promotion"
    )
    assert "AGENTS.md" in clause, (
        "0003's amendment doesn't point at AGENTS.md as the living rule"
    )


def test_rfc_0003_original_status_prefix_and_earlier_annotations_survive():
    status = _status_line(RFC_0003)
    assert status.startswith(
        "**Status:** Accepted — implemented (native Status/Reason fields "
        "live on Project #1) · **rev 2** (2026-06-18, native primitives) "
        "· **Amends** [0001-ticket-driven-dev-workflow]"
    ), "0003's original status prefix (including 'rev 2' and 'Amends') was disturbed"
    assert "**Informs** 2026-06-17-dev-runner-v1" in status


def test_rfc_0003_body_frozen_statement_is_untouched():
    text = _text(RFC_0003)
    assert (
        "**Promotion to `Ready` is always a human/Joam decision.** The "
        "runner *consumes* Ready; it never sets it." in text
    ), "0003's frozen body statement at :43 was rewritten, not just pointed at"


def test_rfc_0003_principle_paragraph_is_untouched():
    text = _text(RFC_0003)
    assert (
        "Status belongs to the task — and we represent every facet "
        "with GitHub's **native** mechanism, not labels." in text
    ), "0003's Principle paragraph was edited"


def test_rfc_0003_amended_appears_only_on_the_status_line():
    lines = _text(RFC_0003).splitlines()
    amended_lines = [i for i, l in enumerate(lines) if "Amended" in l]
    assert amended_lines == [2], (
        f"'Amended' appears outside the status line (0-indexed line 2) in 0003: "
        f"found on lines {amended_lines}"
    )


# ---------------------------------------------------------------------------
# 0004-dispatch.md — a *second* amendment clause is appended alongside the
# existing 2026-07-10 #126 one, for the same promotion statement (:43);
# tests/test_dispatch.py:256 pins the first five lines for the #126 tokens
# ---------------------------------------------------------------------------

def test_rfc_0004_existing_126_amendment_is_undisturbed():
    header = _first_five_lines(RFC_0004)
    assert re.search(r"amended", header, re.I)
    assert "#126" in header
    assert re.search(r"per-repo", header, re.I)
    assert re.search(r"single.flight", header, re.I)
    assert (
        "**Amended 2026-07-10:** single-flight is superseded by per-repo "
        "locks + an operator-adjustable global concurrency cap (epic #126) "
        "— see `deploy/DISPATCH.md`" in header
    ), "0004's existing 2026-07-10 #126 amendment clause was altered"


def test_rfc_0004_carries_a_second_amendment_clause():
    status = _status_line(RFC_0004)
    amendments = re.findall(r"\*\*Amended \d{4}-\d{2}-\d{2}:\*\*", status)
    assert len(amendments) == 2, (
        f"0004's status line should carry exactly two amendment clauses "
        f"(the existing #126 one plus a new one), found {len(amendments)}"
    )


def test_rfc_0004_second_amendment_names_the_superseded_grooming_statement():
    status = _status_line(RFC_0004)
    # split off everything after the first amendment clause to inspect the second
    parts = status.split("**Amended 2026-07-10:**", 1)
    assert len(parts) == 2, "0004 lost its 2026-07-10 amendment marker"
    remainder = parts[1]
    second_match = re.search(r"\*\*Amended \d{4}-\d{2}-\d{2}:\*\*.*", remainder)
    assert second_match, "0004's status line has no second amendment clause"
    clause = second_match.group(0)
    assert re.search(r"grooming|promot", clause, re.IGNORECASE), (
        "0004's second amendment doesn't name the superseded promotion/grooming statement"
    )
    assert re.search(r"human", clause, re.IGNORECASE), (
        "0004's second amendment doesn't reference the human/Joam decision it supersedes"
    )
    assert re.search(r"epic.gate", clause, re.IGNORECASE), (
        "0004's second amendment doesn't name the epic-gate as the shipped reality"
    )
    assert re.search(r"standing.approval", clause, re.IGNORECASE), (
        "0004's second amendment doesn't name standing-approval promotion"
    )
    assert re.search(r"standalone", clause, re.IGNORECASE), (
        "0004's second amendment doesn't carve out that standalone tasks keep human promotion"
    )
    assert "AGENTS.md" in clause, (
        "0004's second amendment doesn't point at AGENTS.md as the living rule"
    )


def test_rfc_0004_second_amendment_is_appended_after_the_first():
    status = _status_line(RFC_0004)
    first_idx = status.find("**Amended 2026-07-10:**")
    second_idx = status.find(
        "**Amended", first_idx + len("**Amended 2026-07-10:**")
    )
    assert first_idx != -1 and second_idx != -1 and second_idx > first_idx, (
        "0004's second amendment clause isn't positioned after the existing "
        "2026-07-10 clause on the status line"
    )


def test_rfc_0004_builds_on_trailer_survives():
    status = _status_line(RFC_0004)
    assert status.rstrip().endswith(
        "**Builds on** [0001-ticket-driven-dev-workflow](0001-ticket-driven-dev-workflow.md), "
        "[0002-dev-ai-runner](0002-dev-ai-runner.md), "
        "[0003-task-state-model](0003-task-state-model.md)"
    ), "0004's trailing 'Builds on' citation list was disturbed"


def test_rfc_0004_body_frozen_statement_is_untouched():
    text = _text(RFC_0004)
    assert (
        "**Grooming** (Backlog → Ready, #20) stays a human/Joam judgment "
        "— dispatch only *pulls* Ready, never *promotes*." in text
    ), "0004's frozen body statement at :43 was rewritten, not just pointed at"


def test_rfc_0004_context_paragraph_is_untouched():
    text = _text(RFC_0004)
    assert (
        "The dev-runner takes a Ready task to a reviewed, tested PR "
        "end-to-end (implement → tester → review; v0.1–v0.3, "
        "proven live on #26)." in text
    ), "0004's Context paragraph was edited"


def test_rfc_0004_amended_appears_only_on_the_status_line():
    lines = _text(RFC_0004).splitlines()
    amended_lines = [i for i, l in enumerate(lines) if "Amended" in l]
    assert amended_lines == [2], (
        f"'Amended' appears outside the status line (0-indexed line 2) in 0004: "
        f"found on lines {amended_lines}"
    )


# ---------------------------------------------------------------------------
# The living rule cited by the new pointers actually exists in AGENTS.md
# ---------------------------------------------------------------------------

def test_agents_md_has_the_input_gate_paragraph_the_pointers_cite():
    text = _text(AGENTS)
    assert re.search(r"standing approval", text, re.IGNORECASE), (
        "AGENTS.md is missing the standing-approval input-gate language the "
        "new RFC amendment pointers cite"
    )
    assert re.search(r"epic.gate|epic_gate", text, re.IGNORECASE), (
        "AGENTS.md is missing an epic-gate reference for the amendment pointers to cite"
    )


# ---------------------------------------------------------------------------
# Net-lines declaration: pointers land, nothing removed -- across all three
# files combined, more characters exist after the change than a bare status
# prefix would, i.e. status lines only grew (additive amendment clauses).
# ---------------------------------------------------------------------------

def test_status_lines_are_longer_than_their_pre_amendment_prefixes():
    # A cheap, implementation-independent proxy for "net-positive, additive
    # only": each amended status line must be strictly longer than its
    # known original (pre-#153) prefix once the trailing citation is
    # accounted for, i.e. the amendment text was inserted, not swapped in
    # place of dropped content.
    assert len(_status_line(RFC_0002)) > len(
        "**Status:** Accepted (2026-06-17) · **Decision-makers:** Jose "
        "+ Claude · **Builds on:** [0001-ticket-driven-dev-workflow]"
        "(0001-ticket-driven-dev-workflow.md)"
    )
    assert len(_status_line(RFC_0003)) > len(
        "**Status:** Accepted — implemented (native Status/Reason "
        "fields live on Project #1) · **rev 2** (2026-06-18, native "
        "primitives) · **Amends** [0001-ticket-driven-dev-workflow]"
        "(0001-ticket-driven-dev-workflow.md) · **Informs** "
        "2026-06-17-dev-runner-v1"
    )
    assert len(_status_line(RFC_0004)) > len(
        "**Status:** Accepted — implemented & live (n8n workflow polls "
        "Ready → dev-runner) · **Amended 2026-07-10:** "
        "single-flight is superseded by per-repo locks + an "
        "operator-adjustable global concurrency cap (epic #126) — see "
        "`deploy/DISPATCH.md` · **Builds on** "
        "[0001-ticket-driven-dev-workflow](0001-ticket-driven-dev-workflow.md), "
        "[0002-dev-ai-runner](0002-dev-ai-runner.md), "
        "[0003-task-state-model](0003-task-state-model.md)"
    )
