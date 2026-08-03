"""Acceptance tests for issue #382 — one shared matcher helper for the `YR-*` record markers.

This is the *prune* half of a pin-then-prune pair (tech-debt round 2). The pin slice (issue #381,
tests/test_marker_grammar_pins.py) locked the behaviour that MUST survive; this file verifies the new
shared helper and the declared behaviour change on the merge-record reader.

Derived from the acceptance CRITERIA (the spec), never from the implementation's internals: each test
drives a named reader through its own entry point with crafted comment/body text and asserts only the
observable behaviour. No test re-implements a `startswith` / `.strip()` matcher.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import textutil        # noqa: E402
import merge_shadow    # noqa: E402
import bench_report    # noqa: E402
import verdict_diff    # noqa: E402

MERGE_TOOL = ROOT / "tools" / "merge_shadow.py"


# ============================================================================
# Criterion 1 & 2 — textutil gains a marker matcher with two NAMED anchoring modes; each call site
# names its mode; the helper never guesses and never collapses the two.
# ============================================================================

def test_helper_and_two_named_modes_are_public():
    """`textutil` exposes the matcher plus two distinct, named anchoring-mode constants."""
    assert callable(textutil.marker_line_matches)
    assert textutil.MARKER_SENTINEL != textutil.MARKER_PREFIX, (
        "the two anchoring modes must be distinct, never collapsed into one"
    )


# -- sentinel mode: a line EQUAL to the marker after stripping (leading whitespace tolerated) ----------
@pytest.mark.parametrize("line,matches", [
    ("YR-DEBT-LEDGER", True),                 # bare marker at column 0
    ("    YR-DEBT-LEDGER", True),             # indented — leading whitespace tolerated BY DESIGN
    ("\tYR-DEBT-LEDGER", True),               # a tab is whitespace too
    ("YR-DEBT-LEDGER   ", True),              # trailing whitespace tolerated
    ("Per YR-DEBT-LEDGER the round is due", False),   # a longer line (prose) is not the sentinel
    ("`YR-DEBT-LEDGER`", False),             # an inline-backticked example is not the sentinel
    ("YR-DEBT-LEDGER: value", False),        # a longer marker name / payload is not equality
], ids=lambda v: str(v))
def test_sentinel_mode_is_stripped_line_equality(line, matches):
    assert textutil.marker_line_matches(line, "YR-DEBT-LEDGER", mode=textutil.MARKER_SENTINEL) is matches


# -- prefix mode: the RAW, unstripped line begins with the marker at column 0, NO whitespace tolerance --
@pytest.mark.parametrize("line,matches", [
    ("YR-NIT: tag=nit path=x.py — msg", True),   # column 0
    (" YR-NIT: tag=nit path=x.py", False),       # one-space indent never matches (raw, unstripped)
    ("\tYR-NIT: tag=nit path=x.py", False),      # a tab indent never matches
    ("> YR-NIT: tag=nit path=x.py", False),      # a `> `-blockquoted line never matches
    ("see the `YR-NIT:` grammar", False),        # an inline mention never matches
], ids=lambda v: str(v))
def test_prefix_mode_is_raw_column0_startswith(line, matches):
    assert textutil.marker_line_matches(line, "YR-NIT:", mode=textutil.MARKER_PREFIX) is matches


def test_the_two_modes_do_not_collapse_on_an_indented_line():
    """The observable difference the two modes encode: an INDENTED marker line matches the sentinel rule
    but NOT the prefix rule. A helper that collapsed them could not tell these apart."""
    indented = "    YR-DEBT-LEDGER"
    assert textutil.marker_line_matches(indented, "YR-DEBT-LEDGER", mode=textutil.MARKER_SENTINEL) is True
    assert textutil.marker_line_matches(indented, "YR-DEBT-LEDGER", mode=textutil.MARKER_PREFIX) is False


def test_mode_is_mandatory_and_named_the_helper_never_guesses():
    """The caller must NAME its mode — there is no default, so the helper cannot silently guess one."""
    with pytest.raises(TypeError):
        textutil.marker_line_matches("YR-NIT:", "YR-NIT:")  # no mode= given


def test_unknown_mode_is_a_raised_error_not_a_guess():
    with pytest.raises(ValueError):
        textutil.marker_line_matches("YR-NIT:", "YR-NIT:", mode="whole-body")


# ============================================================================
# Criterion — tools/bench_report.py's verdict-diff reader migrates from a whole-BODY prefix onto the
# helper's column-0 prefix mode. Every comment the composer emits still parses.
# ============================================================================

def _verdict_diff_comment(*, agree=True, round=4, gating="APPROVE", shadow="APPROVE", **kw):
    rec = {"schema": "yr-verdict-diff/1", "round": round, "gating": gating, "shadow": shadow,
           "agree": agree}
    if not agree:
        rec.setdefault("gating_transcript", "VERDICT: APPROVE\n")
        rec.setdefault("shadow_transcript", "VERDICT: REJECT\n")
    rec.update(kw)
    return verdict_diff.render_comment(rec)


def test_verdict_diff_composer_output_still_parses():
    """The composer is the fixed point: the agreement AND disagreement shapes both still parse."""
    agree = bench_report.parse_verdict_diff_comment(11, _verdict_diff_comment(agree=True))
    assert agree is not None and agree["pr"] == 11 and agree["agree"] is True
    disagree = bench_report.parse_verdict_diff_comment(
        12, _verdict_diff_comment(agree=False, gating="APPROVE", shadow="REJECT"))
    assert disagree is not None and disagree["agree"] is False and disagree["shadow"] == "REJECT"


def test_verdict_diff_marker_on_a_column0_line_not_the_body_start_now_parses():
    """The migration's observable gain over the old whole-BODY `body.startswith` rule: a comment whose
    marker leads a column-0 LINE (here after a preamble line) is now recognized, where the old
    whole-body-prefix rule required the marker to be the body's very first bytes."""
    body = "Automated verdict-diff for this round:\n\n" + _verdict_diff_comment(round=5)
    assert not body.startswith(bench_report.DIFF_MARKER)   # not the body's first bytes
    record = bench_report.parse_verdict_diff_comment(13, body)
    assert record is not None and record["round"] == 5


@pytest.mark.parametrize("prefixed", ["    ", "\t", "> "], ids=["indent-spaces", "indent-tab", "blockquote"])
def test_verdict_diff_indented_or_blockquoted_marker_does_not_parse(prefixed):
    """Column-0 prefix mode has no whitespace tolerance: an indented or `> `-blockquoted marker line is
    not a verdict-diff record."""
    body = "\n".join(prefixed + l for l in _verdict_diff_comment().splitlines()) + "\n"
    assert bench_report.parse_verdict_diff_comment(14, body) is None


# ============================================================================
# Criterion (declared behaviour change) — merge_shadow's merge-record identification moves onto the
# helper's prefix mode applied to WHOLE marker tokens. The four arms, each with its negative.
# ============================================================================

def _record_dict(*, mode, decision, run_id, **kw):
    """A minimally-complete yr-merge-record dict the real composer (render_comment, the fixed point)
    renders into a comment body — marker line, blank line, then the fenced JSON block."""
    rec = {"schema": "yr-merge-record/1", "mode": mode, "decision": decision, "machinery_ok": True,
           "run_id": run_id, "base_sha": "b" * 40, "head_sha": "h" * 40}
    rec.update(kw)
    return rec


def _armed_comment(run_id="run-armed", decision="MERGED", **kw):
    return {"body": merge_shadow.render_comment(
        _record_dict(mode="armed", decision=decision, run_id=run_id, merge_commit="c" * 40, **kw))}


def _shadow_comment(run_id="run-shadow", decision="WOULD-MERGE", **kw):
    return {"body": merge_shadow.render_comment(
        _record_dict(mode="shadow", decision=decision, run_id=run_id, **kw))}


def _seen(comments):
    """(record, malformed, seen) for a list of `{'body': ...}` comments."""
    return merge_shadow._last_merge_record(comments)


# -- Arm 1: prose quoting the marker (outside a record's own marker line) ------------------------------
def test_arm_prose_mention_of_the_marker_is_not_a_merge_record():
    prose = {"body": "The `YR-MERGE` record must carry its colon; I think we should document that."}
    rec, malformed, seen = _seen([prose])
    assert seen is False and rec is None and malformed is False


def test_arm_prose_mention_does_not_override_a_genuine_record_in_the_same_trail():
    """The negative: a genuine armed record in the same trail is still found — the prose does not win."""
    rec, malformed, seen = _seen([_armed_comment(run_id="genuine-A"),
                                  {"body": "later review prose mentioning YR-MERGE inline"}])
    assert seen is True and malformed is False and rec["run_id"] == "genuine-A"


# -- Arm 2: the bare fence word `yr-merge-record` outside a merge record's own fence -------------------
def test_arm_bare_fence_word_in_prose_is_not_a_merge_record():
    body = "In `tools/merge_shadow.py` the fenced-block name is `yr-merge-record`; note the schema."
    rec, malformed, seen = _seen([{"body": body}])
    assert seen is False and rec is None and malformed is False


def test_arm_orphan_fenced_block_without_a_marker_line_is_not_a_merge_record():
    """A comment carrying a ```yr-merge-record fenced block but NO column-0 marker line is not the PR's
    merge record — identification anchors on the marker line, not the fence word."""
    body = "Here is the block shape:\n\n```yr-merge-record\n{\"decision\": \"MERGED\"}\n```\n"
    rec, malformed, seen = _seen([{"body": body}])
    assert seen is False and rec is None and malformed is False


def test_arm_bare_fence_word_does_not_override_a_genuine_record():
    rec, malformed, seen = _seen([_armed_comment(run_id="genuine-B"),
                                  {"body": "the fence word `yr-merge-record` appears here in prose"}])
    assert seen is True and malformed is False and rec["run_id"] == "genuine-B"


# -- Arm 3: a marker whose name merely BEGINS WITH `YR-MERGE` (not the armed whole token) --------------
def test_arm_longer_marker_name_beginning_with_yr_merge_is_not_matched_by_that_prefix():
    """A whole-token match: the armed token `YR-MERGE:` does NOT match a marker line whose name merely
    begins with `YR-MERGE` (here a hypothetical `YR-MERGE-PLAN:`), so the prefix alone cannot trip the
    reader."""
    assert textutil.marker_line_matches("YR-MERGE-PLAN: draft", merge_shadow.MARKER_ARMED + ":",
                                        mode=textutil.MARKER_PREFIX) is False
    body = "YR-MERGE-PLAN: draft\n\n```yr-merge-record\n{\"decision\": \"MERGED\"}\n```\n"
    rec, malformed, seen = _seen([{"body": body}])
    assert seen is False and rec is None and malformed is False


def test_arm_shadow_marker_prefix_does_not_make_it_an_armed_record():
    """The shipped case: the shadow marker's name begins with `YR-MERGE`. The armed token `YR-MERGE:`
    must NOT match a shadow marker line by virtue of that shared prefix (whole-token discipline)."""
    shadow_line = merge_shadow.MARKER_SHADOW + ": WOULD-MERGE"
    assert textutil.marker_line_matches(shadow_line, merge_shadow.MARKER_ARMED + ":",
                                        mode=textutil.MARKER_PREFIX) is False
    assert textutil.marker_line_matches(shadow_line, merge_shadow.MARKER_SHADOW + ":",
                                        mode=textutil.MARKER_PREFIX) is True


# -- Arm 4: a blockquoted merge record ----------------------------------------------------------------
def test_arm_blockquoted_record_is_neither_this_prs_record_nor_malformed():
    """A `> `-blockquoted record (the shape the shadow/bench seat produces) is NOT read as this PR's own
    record — and, crucially, is NOT reported as malformed. It simply leaves the PR out of the window."""
    genuine = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="quoted"))
    quoted = {"body": "\n".join("> " + l for l in genuine.splitlines())}
    rec, malformed, seen = _seen([quoted])
    assert seen is False and rec is None and malformed is False


def test_arm_blockquoted_record_does_not_override_a_genuine_record():
    genuine = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="older"))
    quoted = {"body": "\n".join("> " + l for l in genuine.splitlines())}
    rec, malformed, seen = _seen([_armed_comment(run_id="genuine-C"), quoted])
    assert seen is True and malformed is False and rec["run_id"] == "genuine-C"


def test_blockquoted_record_reports_not_found_via_the_cli_never_malformed():
    """Through the `last-record` CLI (the re-evaluate locator's own surface): a blockquoted record prints
    `found: false`, NOT `found: true, malformed: true` — so the caller never refuses over a quote."""
    genuine = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="q"))
    quoted = [{"body": "\n".join("> " + l for l in genuine.splitlines())}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(quoted, fh)
        path = fh.name
    out = subprocess.run([sys.executable, str(MERGE_TOOL), "last-record", "--comments-file", path],
                         capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    assert result == {"found": False}


# ============================================================================
# Criterion — the shadow window still sees genuine shadow records. Excluding them would empty the
# window; that is the regression this fix could most easily cause.
# ============================================================================

def test_genuine_shadow_record_is_still_a_merge_record():
    rec, malformed, seen = _seen([_shadow_comment(run_id="shadow-1", decision="WOULD-MERGE")])
    assert seen is True and malformed is False
    assert rec["decision"] == "WOULD-MERGE" and rec["run_id"] == "shadow-1"


def test_genuine_shadow_record_classifies_into_the_shadow_window():
    """A landed, unreverted shadow WOULD-MERGE is a `success` event — so it counts toward completion."""
    pr = {"number": 7, "state": "MERGED", "mergeCommit": {"oid": "d" * 40},
          "comments": [_shadow_comment(run_id="shadow-2", decision="WOULD-MERGE")]}
    assert merge_shadow.classify_event(pr, set(), set()) == "success"


def test_shadow_completion_window_is_not_emptied_by_the_fix():
    """End-to-end: three landed shadow records satisfy the pinned N=5/K=3 window. If the fix wrongly
    excluded shadow records, the window would be empty and completion false — the regression guard."""
    prs = [{"number": n, "state": "MERGED", "mergeCommit": {"oid": f"{n:040d}"},
            "comments": [_shadow_comment(run_id=f"s-{n}", decision="WOULD-MERGE")]}
           for n in (30, 31, 32)]
    complete, successes, size = merge_shadow.shadow_completion(prs, main_log="")
    assert size == 3 and successes == 3 and complete is True


# ============================================================================
# Criterion — the fenced-block parse reads the fence from the SAME anchored line that identified the
# comment, so a genuine record that also blockquotes an older one cannot parse the quoted block.
# ============================================================================

def _quote(body):
    return "\n".join("> " + l for l in body.splitlines())


def test_genuine_record_quoting_an_older_one_parses_its_own_block_quote_above():
    """The older record is blockquoted ABOVE the genuine one. Identification anchors on the genuine
    column-0 marker, and the fenced-block parse begins there — so the quoted block is never parsed."""
    older = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="OLDER"))
    own = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="OWN"))
    body = _quote(older) + "\n\n" + own
    rec, malformed, seen = _seen([{"body": body}])
    assert seen is True and malformed is False
    assert rec["run_id"] == "OWN", "the parse must read the genuine block, never the quoted one"


def test_genuine_record_quoting_an_older_one_parses_its_own_block_quote_below():
    older = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="OLDER"))
    own = merge_shadow.render_comment(_record_dict(mode="armed", decision="MERGED", run_id="OWN"))
    body = own + "\n\n" + _quote(older)
    rec, malformed, seen = _seen([{"body": body}])
    assert seen is True and malformed is False and rec["run_id"] == "OWN"


# ============================================================================
# The wall-11 guard — a test that FAILS when a second hand-rolled marker matcher appears. Its expected
# set is DERIVED FROM THE TREE (scan every module, route through the shared helper), never a fixed list
# of the readers known today.
# ============================================================================

# The one legitimate home of a raw `startswith` / `.strip() ==` against a marker: the shared helper.
HELPER_MODULE = "textutil.py"

# A YR-* marker literal used in a matching context — the literal drift shapes the slice removed.
_LITERAL_HAND_ROLLED = [
    re.compile(r"""\.startswith\(\s*['"]YR-"""),              # `x.startswith("YR-...")`
    re.compile(r"""['"]YR-[\w:.\- ]*['"]\s+in\b"""),          # `"YR-..." in body` bare substring
    re.compile(r"""\.strip\(\)\s*==\s*['"]YR-"""),            # `x.strip() == "YR-..."` sentinel
    re.compile(r"""==\s*['"]YR-[\w:.\- ]*['"]"""),            # `... == "YR-..."` equality
]


def _marker_constants(source):
    """Every module-level name assigned a `"YR-..."` string literal — the tree's own marker constants,
    derived from the source, so a NEW reader's NEW constant is picked up automatically."""
    return set(re.findall(r"""(?m)^([A-Za-z_]\w*)\s*=\s*['"]YR-""", source))


def _hand_rolled_hits(source):
    """The hand-rolled-matcher hits in one module's source: a raw `startswith` / bare-substring / stripped
    equality against a YR-* marker LITERAL, or against one of the module's own marker CONSTANTS. A call
    routed through `textutil.marker_line_matches(...)` is not a hit — the marker there is an argument, not
    the subject of a `.startswith`/`in`/`==`."""
    hits = []
    for rx in _LITERAL_HAND_ROLLED:
        hits += [m.group(0) for m in rx.finditer(source)]
    for const in _marker_constants(source):
        c = re.escape(const)
        for rx in (re.compile(rf"\.startswith\(\s*{c}\b"),
                   re.compile(rf"\b{c}\s+in\b"),
                   re.compile(rf"\.strip\(\)\s*==\s*{c}\b"),
                   re.compile(rf"==\s*{c}\b"),
                   re.compile(rf"\b{c}\s*==")):
            hits += [m.group(0) for m in rx.finditer(source)]
    return hits


def _source_modules():
    """Every Python module in the tree's tool/consumer surfaces except the helper's own home. Derived by
    walking the tree — never a fixed list of the readers known today."""
    mods = []
    for sub in ("tools", "qa"):
        for path in sorted((ROOT / sub).glob("*.py")):
            if path.name == HELPER_MODULE:
                continue
            mods.append(path)
    return mods


def test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree():
    """No module outside the shared helper hand-rolls a `YR-*` marker matcher. Derived over the tree:
    every module that reads a marker must route through `textutil.marker_line_matches`."""
    offenders = {}
    for path in _source_modules():
        hits = _hand_rolled_hits(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, (
        "a hand-rolled YR-* marker matcher reappeared outside tools/textutil.py — route it through "
        f"textutil.marker_line_matches(...): {offenders}"
    )


def test_wall11_guard_actually_bites_on_synthetic_offenders():
    """The guard is not vacuous: it flags each drift shape the slice removed, whether written with a
    literal or with a module-local marker constant."""
    offending = [
        'if body.startswith("YR-VERDICT-DIFF:"):',       # bench_report's old whole-body prefix
        'if "YR-MERGE" in body or "yr-merge-record" in body:',   # merge_shadow's old bare substring
        'if line.strip() == "YR-DEBT-LEDGER":',          # a stripped-equality sentinel via literal
        'NIT_PREFIX = "YR-NIT:"\nif line.startswith(NIT_PREFIX):',   # via a marker constant
        'MARK = "YR-DEBT-HOLD"\nif line.strip() == MARK:',          # stripped equality via constant
    ]
    for snippet in offending:
        assert _hand_rolled_hits(snippet), f"guard failed to flag a hand-rolled matcher: {snippet!r}"


def test_wall11_guard_does_not_flag_helper_routed_calls_or_unrelated_code():
    """It must NOT flag a helper-routed call, nor unrelated `startswith`/`.strip() ==` against non-marker
    text (e.g. a blockquote prefix or a markdown heading), or the guard would forbid legitimate code."""
    clean = [
        'textutil.marker_line_matches(line, NIT_PREFIX, mode="prefix")',
        'NIT_PREFIX = "YR-NIT:"\ntextutil.marker_line_matches(line, NIT_PREFIX, mode="prefix")',
        'if lead.startswith(">"):',                       # blockquote-prefix test, not a marker
        'if l.strip() == CAVEAT_HEADING:',                # "## Grading caveat", not a YR marker
        'prefix = MARKER_ARMED if record.get("mode") == "armed" else MARKER_SHADOW',
    ]
    for snippet in clean:
        assert not _hand_rolled_hits(snippet), f"guard wrongly flagged legitimate code: {snippet!r}"


def test_wall11_guard_confirms_the_migrated_readers_route_through_the_helper():
    """A positive read of the same fact: every migrated reader module references the shared helper, so
    the ban above is protecting a real routing, not an empty set."""
    for name in ("epic_gate.py", "nit_harvest.py", "merge_shadow.py", "bench_report.py"):
        src = (ROOT / "tools" / name).read_text(encoding="utf-8")
        assert "marker_line_matches" in src, (
            f"tools/{name} no longer routes marker matching through textutil.marker_line_matches"
        )
