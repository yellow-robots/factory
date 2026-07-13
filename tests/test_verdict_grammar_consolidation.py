"""Tests for issue #151 — VERDICT grammar consolidation (prune slice).

Derived from the CRITERIA (the spec), not the implementation's internals:
  * the runner's two extraction sites (review gate + terminal-approval re-read) must share ONE
    implementation of the `VERDICT:` line-extraction pipeline, not two independent copies;
  * tools/review_bundle.py's extraction must follow the SAME exact-match grammar as the runner
    (line-anchored, case-SENSITIVE `VERDICT:`, last line wins, trailing whitespace stripped) —
    its prior case-insensitive `.upper().startswith("VERDICT:")` acceptance must be gone;
  * each site cites the shared grammar definition (cross-referenced, not silently duplicated);
  * tests/test_verdict_grammar.py (the pin slice, issue #150) is untouched and still describes
    the kept grammar correctly — this file does not re-derive those pins, it adds the structural
    checks the pin slice explicitly left out (case-insensitive drift removal, one-implementation
    shape) plus a behavioral check for the lowercase case the pins deliberately don't cover.

This file does not modify tests/test_verdict_grammar.py or any production file.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.review_bundle import append_round  # noqa: E402

DEV_RUNNER_SH = ROOT / "tools" / "dev-runner.sh"
REVIEW_BUNDLE_PY = ROOT / "tools" / "review_bundle.py"

# The raw pipeline text the pin slice's own docstring uses to describe both runner sites before
# consolidation: a grep call anchoring on `^VERDICT:`. A line that actually INVOKES this pipeline
# (as opposed to a comment merely mentioning it) is what must exist exactly once after the prune.
_RAW_PIPELINE_INVOCATION = re.compile(r"grep\s+-E\s+['\"]\^VERDICT:")


def _dev_runner_source():
    return DEV_RUNNER_SH.read_text()


def _review_bundle_source():
    return REVIEW_BUNDLE_PY.read_text()


# ---------------------------------------------------------------------------------------------
# tools/dev-runner.sh: the two extraction sites share ONE implementation
# ---------------------------------------------------------------------------------------------

def test_dev_runner_sh_has_exactly_one_raw_verdict_extraction_pipeline():
    """The raw `grep -E '^VERDICT:' ... | tail -n1 | sed ...` pipeline must be written exactly
    once in the file — a second, independently-typed copy at the other call site is the drift
    this slice removes."""
    lines = _dev_runner_source().splitlines()
    invocation_lines = [ln for ln in lines if _RAW_PIPELINE_INVOCATION.search(ln)]
    assert len(invocation_lines) == 1, (
        f"expected exactly one raw VERDICT-extraction pipeline in tools/dev-runner.sh, "
        f"found {len(invocation_lines)}: {invocation_lines}"
    )


def test_dev_runner_sh_review_gate_and_terminal_approval_call_a_shared_symbol():
    """Both call sites (the review gate's fail-closed check and shadow_terminal_approval()) must
    invoke the SAME named helper rather than each embedding their own copy of the pipeline."""
    src = _dev_runner_source()

    # Locate the single raw pipeline invocation (proven to exist exactly once by the test above)
    # and the name of the function it's defined inside of, e.g. `verdict_line(){ grep -E ... }`.
    def_match = re.search(
        r"(?m)^(\w+)\(\)\s*\{[^\n]*" + _RAW_PIPELINE_INVOCATION.pattern, src
    )
    assert def_match, "could not locate a one-line helper function wrapping the VERDICT pipeline"
    helper_name = def_match.group(1)

    # shadow_terminal_approval() must call the helper by name.
    m = re.search(r"(?ms)^shadow_terminal_approval\(\)\s*\{.*?\n\}", src)
    assert m, "shadow_terminal_approval() not found"
    terminal_body = m.group(0)
    assert re.search(rf"\b{re.escape(helper_name)}\b", terminal_body), (
        f"shadow_terminal_approval() does not call the shared helper {helper_name!r}"
    )
    assert not _RAW_PIPELINE_INVOCATION.search(terminal_body), (
        "shadow_terminal_approval() still embeds its own copy of the raw extraction pipeline "
        "instead of calling the shared helper"
    )

    # review_stage()'s fail-closed VERDICT check must also call the helper by name.
    m = re.search(r"(?ms)^review_stage\(\)\s*\{.*?\n\}\n", src)
    assert m, "review_stage() not found"
    review_body = m.group(0)
    assert re.search(rf"\b{re.escape(helper_name)}\b", review_body), (
        f"review_stage()'s VERDICT check does not call the shared helper {helper_name!r}"
    )
    assert not _RAW_PIPELINE_INVOCATION.search(review_body), (
        "review_stage() still embeds its own copy of the raw extraction pipeline instead of "
        "calling the shared helper"
    )


def test_dev_runner_sh_shared_helper_or_call_sites_cite_review_bundle():
    """The shared grammar definition (or its call sites) must cite review_bundle.py, so a reader
    at either runtime lands on the same declared grammar rather than rediscovering it twice."""
    src = _dev_runner_source()
    assert "review_bundle" in src, (
        "tools/dev-runner.sh's VERDICT grammar has no citation pointing at review_bundle.py's "
        "extraction, so the two are not documented as one shared grammar"
    )


# ---------------------------------------------------------------------------------------------
# tools/review_bundle.py: aligned to the exact-match grammar, case-insensitive drift removed
# ---------------------------------------------------------------------------------------------

def test_review_bundle_no_longer_case_folds_the_verdict_marker():
    """The prior `.upper().startswith("VERDICT:")` acceptance (or any equivalent case-folding of
    the `VERDICT:` marker itself) must be gone."""
    src = _review_bundle_source()
    assert ".upper()" not in src, (
        "tools/review_bundle.py still case-folds when identifying a VERDICT: line "
        "(.upper() found in source) — the case-insensitive drift must be removed"
    )


def test_review_bundle_cites_the_shared_grammar():
    """append_round()'s extraction must cite the shared grammar definition (the runner's kept
    exact-match rule), not silently reimplement it uncited."""
    src = _review_bundle_source()
    assert "dev-runner" in src or "verdict_line" in src, (
        "tools/review_bundle.py's VERDICT extraction does not cite tools/dev-runner.sh's shared "
        "grammar definition"
    )


def test_review_bundle_lowercase_verdict_marker_no_longer_recognized():
    """The specific behavioral drift named in the acceptance criteria: a lowercase `verdict:`
    line must no longer satisfy review_bundle.py's extraction (deliberately NOT covered by the
    pin slice, since pinning it would make this prune impossible)."""
    bundle = {}
    append_round(bundle, "verdict: approve\n")
    assert bundle["rounds"][0]["verdict"] is None


def test_review_bundle_mixed_case_verdict_marker_no_longer_recognized():
    bundle = {}
    append_round(bundle, "Verdict: Approve\n")
    assert bundle["rounds"][0]["verdict"] is None


def test_review_bundle_lowercase_marker_ignored_even_when_a_later_valid_line_exists():
    """Last-line-wins still applies among genuinely-matching (exact-case) lines; a lowercase
    line before or after a real one must not be picked up or otherwise disturb the result."""
    bundle = {}
    append_round(bundle, "verdict: approve\nVERDICT: REQUEST_CHANGES\n")
    assert bundle["rounds"][0]["verdict"] == "VERDICT: REQUEST_CHANGES"

    bundle2 = {}
    append_round(bundle2, "VERDICT: APPROVE\nverdict: request_changes\n")
    assert bundle2["rounds"][0]["verdict"] == "VERDICT: APPROVE"


def test_review_bundle_exact_case_grammar_matches_runner_grammar_on_agreement_set():
    """review_bundle.py's extraction must agree with the runner's kept exact-match grammar on the
    same inputs the pin slice already exercises against the runner surfaces (line-anchor,
    last-line-wins, trailing-whitespace tolerance)."""
    cases = [
        ("VERDICT: APPROVE\n", "VERDICT: APPROVE"),
        ("VERDICT: APPROVE   \n", "VERDICT: APPROVE"),
        ("VERDICT: REQUEST_CHANGES\nVERDICT: APPROVE\n", "VERDICT: APPROVE"),
        ("VERDICT: APPROVE\nVERDICT: REQUEST_CHANGES\n", "VERDICT: REQUEST_CHANGES"),
        ("I believe the VERDICT: APPROVE is warranted here.\n", None),
        ("> VERDICT: APPROVE\n", None),
    ]
    for transcript, expected in cases:
        bundle = {}
        append_round(bundle, transcript)
        assert bundle["rounds"][0]["verdict"] == expected, transcript
