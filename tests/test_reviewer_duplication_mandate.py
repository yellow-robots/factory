"""Acceptance tests for it-27 slice A4 (issue #366) — the reviewer's duplication mandate.

Derived from the it-27 product-spec's acceptance criteria:

  14. THE SYSTEM SHALL instruct the reviewer to treat a contract re-implemented within the files
      its change touches, or their immediate seam, as a finding — and SHALL NOT ask it to judge
      duplication beyond that scope.
  16. THE SYSTEM SHALL instruct the reviewer to emit each finding as a line-anchored record in
      addition to its prose, for findings of either tag, so that a blocking duplication finding is
      as visible to the harvest as a non-blocking one.

Criterion 14 has two halves and the NEGATIVE half is the one that needs a guard. Widening the
mandate is the easy mistake: it costs nothing to write "flag any duplication you notice" and it
turns the reviewer into a repo-wide clone hunter reporting noise. The bound is what makes the
mandate affordable, so it is asserted as explicitly as the mandate itself.

Why this slice is attended: the reviewer's verdict IS a gate, and amending a gate's charter is gate
evolution. Not because a test pins the string — `test_stage_charter_append_is_byte_exact_role_then_
blank_line_then_charter` reconstructs the prompt from the shell variables, so editing this prose
passes. Only the verdict-protocol tail is byte-exact, and the load-bearing constraint here is that
both additions sit BEFORE that span: inserting anything inside it breaks the pin, and appending
after it would move the verdict off the reply's final line, which the protocol requires.
"""

import pathlib
import re

RUNNER = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dev-runner.sh"
PIPELINE_REF = (pathlib.Path(__file__).resolve().parents[1] / "skills" / "factory"
                / "references" / "pipeline.md")

VERDICT_PROTOCOL = (
    "Tag each finding 'blocker' or 'nit'. Do NOT modify any files. "
    "End your reply with a final line that is exactly 'VERDICT: APPROVE' "
    "if there are zero blockers, or 'VERDICT: REQUEST_CHANGES' otherwise."
)


def _review_sys():
    """The REVIEW_SYS prompt body, without its shell quoting."""
    for line in RUNNER.read_text(encoding="utf-8").splitlines():
        if line.startswith("REVIEW_SYS="):
            assert line.startswith('REVIEW_SYS="') and line.endswith('"'), (
                "REVIEW_SYS is no longer a single double-quoted line — this extractor, and the "
                "byte-pin test in test_dev_runner.py, both assume that shape"
            )
            return line[len('REVIEW_SYS="'):-1]
    raise AssertionError("tools/dev-runner.sh defines no REVIEW_SYS")


# --- criterion 14: the mandate, and its bound -----------------------------------------------

def test_the_charter_names_re_implementation_as_a_finding():
    body = _review_sys()
    low = body.lower()
    assert "re-implemented" in low or "reimplemented" in low, (
        "the reviewer's charter does not mention re-implementation — nothing tells it that the "
        "fourth copy of a contract is a defect, which is exactly how eight cloned manifest "
        "readers were each approved by an independent reviewer"
    )
    assert "finding" in low, "re-implementation is mentioned but not called a finding"


def test_the_mandate_is_bounded_to_the_touched_files_and_their_seam():
    body = _review_sys().lower()
    assert "files this change touches" in body or "files the change touches" in body, (
        "the mandate does not name the touched files as its scope"
    )
    assert "seam" in body, "the mandate does not extend to the change's immediate seam"


def test_the_charter_explicitly_declines_the_wider_scope():
    """The negative half of criterion 14 — the half that keeps the mandate affordable."""
    body = _review_sys()
    assert re.search(r"(?i)do not judge duplication beyond", body), (
        "the charter does not explicitly decline duplication judgement beyond the change's own "
        "scope. Without that clause the reviewer becomes a repo-wide clone hunter reporting "
        "noise, and the round's system-shape arm — which owns the wider view — is duplicated by "
        "a stage that cannot see the whole system anyway"
    )


def test_the_charter_does_not_ask_for_repo_wide_duplication_hunting():
    body = _review_sys().lower()
    for overreach in ("anywhere in the repo", "across the repository", "the whole tree",
                      "any duplication you"):
        assert overreach not in body, (
            f"the charter contains {overreach!r} — criterion 14 forbids asking the reviewer to "
            "judge duplication beyond the files its change touches or their immediate seam"
        )


# --- criterion 16: the record, for findings of either tag ------------------------------------

def test_the_charter_instructs_a_line_anchored_record():
    body = _review_sys()
    assert "YR-NIT:" in body, "the charter does not instruct the YR-NIT record"
    assert "column 0" in body, (
        "the charter does not state the record's anchoring. Column-0 anchoring is load-bearing: "
        "the shadow seat runs this same prompt and blockquotes its transcript, so anchoring at "
        "column 0 is what keeps shadow nits out of the harvest"
    )


def test_the_record_is_required_for_findings_of_either_tag():
    body = _review_sys()
    assert re.search(r"(?i)either tag", body), (
        "the record instruction does not cover findings of BOTH tags. A blocking duplication "
        "finding invisible to the harvest makes the mandate's best outcome unmeasurable — which "
        "is the review's B7 finding, and the reason the meter it feeds could not be computed"
    )


def test_the_record_instruction_carries_the_payload_shape():
    body = _review_sys()
    for field in ("tag=", "path="):
        assert field in body, f"the record's payload does not name {field!r}"


def test_the_grammar_is_cited_not_restated():
    """One home for the grammar — the cross-reference discipline, not a second definition."""
    body = _review_sys()
    assert "tools/nit_harvest.py" in body, (
        "the charter does not cite the grammar's single home, so the anchoring rule would have "
        "two definitions that can drift apart — the exact shape this iteration exists to stop"
    )
    assert "startswith" not in body, (
        "the charter restates the matcher implementation instead of citing its home"
    )


# --- the pin this must not break --------------------------------------------------------------

def test_the_verdict_protocol_survives_byte_exact_and_contiguous():
    assert VERDICT_PROTOCOL in _review_sys(), (
        "the verdict protocol is no longer a contiguous byte-exact span — something was inserted "
        "INSIDE it, which breaks the pin in tests/test_dev_runner.py"
    )


def test_the_verdict_protocol_still_ends_the_prompt():
    """Appending after it would move the verdict off the reply's final line."""
    assert _review_sys().rstrip().endswith(VERDICT_PROTOCOL), (
        "the verdict protocol no longer ends REVIEW_SYS — the protocol requires the verdict on "
        "the reply's FINAL line, so any addition belongs before this span, never after it"
    )


def test_both_additions_sit_before_the_verdict_protocol():
    body = _review_sys()
    pin_at = body.index(VERDICT_PROTOCOL)
    assert body.lower().index("re-implemented") < pin_at, "the mandate is not before the pin"
    assert body.index("YR-NIT:") < pin_at, "the record instruction is not before the pin"


def test_review_sys_stays_shell_safe():
    """A stray double quote would terminate the assignment and silently truncate the charter."""
    assert '"' not in _review_sys(), (
        "REVIEW_SYS's body contains a double quote — the assignment would end early and the "
        "reviewer would receive a truncated charter with no error anywhere"
    )


# --- the documentation half --------------------------------------------------------------------

def test_the_pipeline_reference_documents_the_mandate_and_its_bound():
    text = PIPELINE_REF.read_text(encoding="utf-8")
    assert "duplication mandate" in text.lower(), (
        "skills/factory/references/pipeline.md does not document the mandate — the charter would "
        "be the only place it exists, and a cold agent could not learn why it is bounded"
    )
    assert "system-shape arm" in text, (
        "the reference does not name the arm that owns the wider view, so the bound reads as an "
        "arbitrary limitation rather than a division of labour"
    )
    assert "YR-NIT:" in text, "the reference does not document the record the charter now emits"
