"""
Tests for issue #361 — Debt round: performance and the test suite become standing arms, and the
round reports its meters (technical-RFC slice P4 of epic #357).

Derived from the issue #361 acceptance criteria (the spec), not from the doc-editor's own wording:

  1. The system reports, per round, the count of duplication findings raised at build time and the
     count of consolidation shapes found by the system-shape arm, as two separate counts — never as
     a ratio of one unit.
  2. The system records per-test runtime attribution at each census together with the protocol that
     produced it — host, load state, extraction method — and does not gate on it.
  3. Where two runtime readings were produced under different protocols, the system compares their
     shares rather than their absolute durations.

Plus the stated test expectations: both standing arms (tests, performance) are described as
measured-every-round and non-gating; the attribution protocol fields (host, load state, extraction
method) are required; shares-before-seconds is stated; Round-close duties names all six meters; the
detection-locus meter is explicitly two counts and explicitly never a ratio.

Plus the stated constraints: this slice ships protocol text only — it changes no command any gate
runs, adds no manifest key, and takes no measurement itself.

House doc-pin style, in the manner of tests/test_debt_census_four_arms_and_reachability_partition.py
and tests/test_debt_round_prune_guard_wall.py — read the shipped file, assert its load-bearing
content.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
DEBT_ROUNDS = REFS / "debt-rounds.md"
DEBT_CENSUS = ROOT / "templates" / "debt-census.md"
MANIFEST = ROOT / ".yr" / "factory.toml"


def _text(path):
    return path.read_text(encoding="utf-8")


def _rounds():
    return _text(DEBT_ROUNDS)


def _census():
    return _text(DEBT_CENSUS)


def _norm(text):
    """Collapse whitespace runs (incl. line-wrap newlines) to a single space, so a phrase check
    isn't brittle against where the markdown happens to wrap a line."""
    return re.sub(r"\s+", " ", text)


def _section(text, heading, next_headings):
    start = text.find(heading)
    assert start != -1, f"missing the {heading!r} section heading"
    end = len(text)
    for nxt in next_headings:
        idx = text.find(nxt, start + 1)
        if idx != -1:
            end = min(end, idx)
    return text[start:end]


def _census_arms_section():
    return _section(_rounds(), "## Census arms", ["## The counter"])


def _round_close_duties_section():
    text = _rounds()
    return _section(text, "## Round-close duties", [])


def _arms_by_number(section):
    """Split the numbered 'Census arms' list into {number: body} the same way
    tests/test_debt_round_prune_guard_wall.py's _wall_11_body isolates a single numbered wall."""
    parts = re.split(r"(?m)^(\d+)\. \*\*", section)
    arms = {}
    for i in range(1, len(parts), 2):
        arms[int(parts[i])] = parts[i + 1]
    return arms


def _arm_coverage_section():
    return _section(_census(), "## Arm coverage", ["## Baselines"])


def _performance_section():
    return _section(_census(), "## Performance", ["## Duplication"])


def _duplication_section():
    return _section(_census(), "## Duplication / consolidation sets", ["## Unknowns"])


# ---------------------------------------------------------------------------
# AC2/AC3 — both standing arms are measured-every-round and non-gating
# (debt-rounds.md 'Census arms')
# ---------------------------------------------------------------------------

def test_debt_rounds_tests_arm_is_a_standing_arm_measured_every_round_and_non_gating():
    arms = _arms_by_number(_census_arms_section())
    body = _norm(arms[3]).lower()
    assert body.startswith("tests.") or "tests." in body[:20], (
        "debt-rounds.md Census arms item 3 is not the Tests arm any more"
    )
    assert "standing arm" in body, (
        "debt-rounds.md Tests arm is not described as a standing arm"
    )
    assert "swept every round" in body, (
        "debt-rounds.md Tests arm does not state it is swept every round rather than once"
    )
    assert "gates nothing" in body, (
        "debt-rounds.md Tests arm does not state it gates nothing"
    )


def test_debt_rounds_performance_arm_is_a_standing_arm_measured_every_round_and_non_gating():
    arms = _arms_by_number(_census_arms_section())
    body = _norm(arms[4]).lower()
    assert body.startswith("performance.") or "performance." in body[:20], (
        "debt-rounds.md Census arms item 4 is not the Performance arm any more"
    )
    assert "standing arm" in body, (
        "debt-rounds.md Performance arm is not described as a standing arm"
    )
    assert "measured every round" in body, (
        "debt-rounds.md Performance arm does not state it is measured every round"
    )
    assert "gates nothing" in body, (
        "debt-rounds.md Performance arm does not state it gates nothing"
    )


def test_debt_census_arm_coverage_notes_tests_and_performance_as_standing_arms():
    section = _norm(_arm_coverage_section()).lower()
    assert "standing arm" in section, (
        "templates/debt-census.md Arm coverage section does not describe tests/performance as "
        "standing arms"
    )
    assert "measured every round" in section, (
        "templates/debt-census.md Arm coverage section does not state the standing arms are "
        "measured every round"
    )
    assert "gating nothing" in section or "gates nothing" in section, (
        "templates/debt-census.md Arm coverage section does not state the standing arms gate "
        "nothing"
    )


# ---------------------------------------------------------------------------
# AC2 — per-test runtime attribution recorded with its protocol (host, load
# state, extraction method); non-gating
# ---------------------------------------------------------------------------

def test_debt_rounds_performance_arm_requires_attribution_with_protocol_fields():
    arms = _arms_by_number(_census_arms_section())
    body = _norm(arms[4]).lower()
    assert "per-test runtime attribution" in body, (
        "debt-rounds.md Performance arm does not require per-test runtime attribution"
    )
    assert "protocol that produced it" in body, (
        "debt-rounds.md Performance arm does not tie the attribution to the protocol that "
        "produced it"
    )
    for field in ("host", "load state", "extraction method"):
        assert field in body, (
            f"debt-rounds.md Performance arm does not name {field!r} as a protocol field"
        )
    assert "does not enter the series" in body, (
        "debt-rounds.md Performance arm does not state a reading without a protocol does not "
        "enter the series"
    )


def test_debt_census_performance_section_has_protocol_line_with_all_three_fields():
    section = _performance_section()
    assert "**Protocol:**" in section, (
        "templates/debt-census.md 'Performance' section is missing a 'Protocol:' declaration line"
    )
    lower = section.lower()
    for field in ("host", "load state", "extraction method"):
        assert field in lower, (
            f"templates/debt-census.md 'Performance' section does not offer a {field!r} protocol "
            "field"
        )


def test_debt_census_performance_section_has_runtime_attribution_table():
    section = _performance_section()
    header = "| Test | Runtime | Share of suite duration | Prior share (same protocol only) |"
    assert header in section, (
        f"templates/debt-census.md 'Performance' section is missing the expected table header "
        f"{header!r}"
    )


def test_debt_census_performance_section_states_non_gating():
    section = _norm(_performance_section()).lower()
    assert "gates nothing" in section, (
        "templates/debt-census.md 'Performance' section does not state the arm gates nothing"
    )


def test_debt_census_performance_section_states_no_protocol_reading_excluded():
    section = _norm(_performance_section()).lower()
    assert "does not enter the series" in section, (
        "templates/debt-census.md 'Performance' section does not restate that a reading with no "
        "protocol does not enter the series"
    )


# ---------------------------------------------------------------------------
# AC3 — shares before seconds; different protocols compare shares only
# ---------------------------------------------------------------------------

def test_debt_rounds_performance_arm_states_shares_before_seconds():
    arms = _arms_by_number(_census_arms_section())
    body = _norm(arms[4]).lower()
    assert "shares before seconds" in body, (
        "debt-rounds.md Performance arm does not state successive readings compare shares "
        "before seconds"
    )
    assert "different protocols" in body, (
        "debt-rounds.md Performance arm does not address readings produced under different "
        "protocols"
    )
    assert "never of absolute durations" in body or "never absolute durations" in body, (
        "debt-rounds.md Performance arm does not state a cross-protocol comparison is of shares "
        "only, never absolute durations"
    )


def test_debt_census_performance_section_states_shares_before_seconds():
    section = _norm(_performance_section()).lower()
    assert "shares before seconds" in section, (
        "templates/debt-census.md 'Performance' section does not restate shares-before-seconds"
    )
    assert "different protocols" in section, (
        "templates/debt-census.md 'Performance' section does not address different-protocol "
        "readings"
    )
    assert "never absolute durations" in section or "never of absolute durations" in section, (
        "templates/debt-census.md 'Performance' section does not state a different-protocol "
        "comparison is of shares only, never absolute durations"
    )


def test_debt_census_performance_table_has_a_share_column_and_a_protocol_scoped_prior_column():
    section = _performance_section()
    assert "Share of suite duration" in section, (
        "templates/debt-census.md 'Performance' table is missing a share-of-duration column"
    )
    assert "Prior share (same protocol only)" in section, (
        "templates/debt-census.md 'Performance' table's prior-reading column is not scoped to "
        "'same protocol only' — a cross-protocol prior reading must not silently qualify as "
        "comparable"
    )


# ---------------------------------------------------------------------------
# AC1 — the detection locus: two counts, kept separate, never a ratio
# (debt-rounds.md 'Round-close duties')
# ---------------------------------------------------------------------------

def test_debt_rounds_round_close_duties_names_all_six_meters_in_order():
    section = _norm(_round_close_duties_section()).lower()
    assert "six close-time meters" in section, (
        "debt-rounds.md 'Round-close duties' does not announce the round's six close-time meters"
    )
    meters = [
        "recurrence",
        "coverage over the four declared axes",
        "guard yield",
        "per-test cost with its protocol",
        "cluster conversion",
        "detection locus",
    ]
    indices = []
    for meter in meters:
        idx = section.find(meter)
        assert idx != -1, (
            f"debt-rounds.md 'Round-close duties' does not name the {meter!r} meter"
        )
        indices.append(idx)
    assert indices == sorted(indices), (
        f"debt-rounds.md 'Round-close duties' does not name the six meters in order: {meters}"
    )


def test_debt_rounds_cluster_conversion_meter_scoped_within_the_finding_round():
    section = _norm(_round_close_duties_section()).lower()
    assert "within the round that found them" in section, (
        "debt-rounds.md 'Round-close duties' does not scope the cluster-conversion meter to "
        "conversions within the round that found them"
    )


def test_debt_rounds_detection_locus_is_two_counts_never_a_ratio():
    section = _norm(_round_close_duties_section()).lower()
    assert "detection locus" in section, (
        "debt-rounds.md 'Round-close duties' does not name the detection-locus meter"
    )
    assert "two counts kept separate" in section, (
        "debt-rounds.md detection-locus meter does not state the two counts are kept separate"
    )
    assert "duplication findings raised at build time" in section, (
        "debt-rounds.md detection-locus meter does not name duplication findings raised at "
        "build time as one of the two counts"
    )
    assert "iteration's reviewer" in section, (
        "debt-rounds.md detection-locus meter does not attribute the build-time count to the "
        "iteration's reviewer"
    )
    assert "consolidation shapes found by the system-shape arm" in section, (
        "debt-rounds.md detection-locus meter does not name consolidation shapes found by the "
        "system-shape arm as the other of the two counts"
    )
    assert "two counts and never as a ratio" in section, (
        "debt-rounds.md detection-locus meter does not state the two counts are reported as two "
        "counts and never as a ratio"
    )


def test_debt_rounds_detection_locus_states_why_never_a_ratio():
    section = _norm(_round_close_duties_section()).lower()
    assert "one pr wide" in section, (
        "debt-rounds.md detection-locus meter does not give the reason a build-time catch is "
        "one PR wide"
    )
    assert "a shape is many" in section, (
        "debt-rounds.md detection-locus meter does not give the reason a shape is many"
    )


def test_debt_census_duplication_section_ties_consolidation_rows_to_detection_locus():
    section = _norm(_duplication_section()).lower()
    assert "detection-locus meter" in section, (
        "templates/debt-census.md 'Duplication / consolidation sets' section does not tie its "
        "rows to the round-close detection-locus meter"
    )
    assert "never a ratio against" in section or "never as a ratio" in section, (
        "templates/debt-census.md 'Duplication / consolidation sets' section does not restate "
        "that the two counts are never combined into a ratio"
    )
    assert "duplication findings" in section and "build time" in section, (
        "templates/debt-census.md 'Duplication / consolidation sets' section does not name the "
        "build-time duplication-findings count it is kept separate from"
    )


# ---------------------------------------------------------------------------
# Structural — Round-close duties list stays a contiguous numbered list
# (mirrors the contiguous-numbering guards already applied to walls and arms
# elsewhere in this canon; a skipped number is a defect the same way a
# skipped wall number would be).
# ---------------------------------------------------------------------------

def test_debt_rounds_round_close_duties_numbered_contiguously():
    section = _round_close_duties_section()
    numbers = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+)\. \*\*", section)]
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"debt-rounds.md 'Round-close duties' list is not numbered contiguously: got {numbers}"
    )


# ---------------------------------------------------------------------------
# Constraint — protocol text only: no manifest key added, no command any
# gate runs is touched, no measurement tooling is introduced
# ---------------------------------------------------------------------------

def test_manifest_check_cmd_and_keys_unchanged_by_this_slice():
    assert MANIFEST.is_file(), f"expected manifest at {MANIFEST}"
    text = _text(MANIFEST)
    assert 'check_cmd = "pytest tests/ -q"' in text, (
        ".yr/factory.toml check_cmd was changed — issue #361 ships protocol text only and "
        "touches no command any gate runs"
    )
    for forbidden_key in (
        "performance_cmd",
        "perf_cmd",
        "test_sweep_cmd",
        "standing_arm",
        "runtime_attribution",
    ):
        assert forbidden_key not in text, (
            f".yr/factory.toml carries a new key ({forbidden_key!r}) — issue #361 adds no "
            "manifest key"
        )


def test_no_new_performance_or_test_sweep_measurement_tooling_is_introduced():
    suspicious_globs = (
        "*perf_meter*",
        "*perf_protocol*",
        "*runtime_attribution*",
        "*standing_arm*",
        "*test_sweep*",
    )
    for pattern in suspicious_globs:
        for candidate in ROOT.glob(f"tools/{pattern}"):
            raise AssertionError(
                f"a performance/test-sweep tool {candidate} exists — issue #361 ships protocol "
                "text only, no measurement tooling"
            )


# ---------------------------------------------------------------------------
# Constraint — only the two named docs carry this slice's content; the
# pre-existing arm names / order stay intact (axis set still closed at four)
# ---------------------------------------------------------------------------

def test_debt_rounds_census_arms_still_closed_at_four_numbered_arms():
    section = _census_arms_section()
    numbers = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+)\. \*\*", section)]
    assert numbers == [1, 2, 3, 4], (
        f"debt-rounds.md 'Census arms' section is not numbered exactly 1..4: got {numbers}"
    )


def test_debt_census_arm_coverage_table_still_has_all_four_arm_rows():
    section = _arm_coverage_section()
    for arm in ("Reachability", "System shape", "Tests", "Performance"):
        row = f"| {arm} |"
        assert row in section, (
            f"templates/debt-census.md Arm coverage table is missing the {arm!r} row"
        )
