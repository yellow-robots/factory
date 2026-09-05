"""The record registry (records.toml + tools/records.py, it-30 slice 1, epic #415).

Two duties: the loader's shape rules fail loud on a malformed registry, and the agreement pins hold —
the inline grammar literals that predate the registry (the runner's claim-time gates constants, the
stage-escape case-arm, the review gate's verdict literal, textutil's mode names) match their registry
rows, so there is one truth with pinned mirrors, never two independent truths.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import records  # noqa: E402
import textutil  # noqa: E402

DEV_RUNNER = (REPO / "tools" / "dev-runner.sh").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def reg():
    return records.load()


# ── the live registry parses and validates ────────────────────────────────────────────────────────

def test_live_registry_loads_and_validates(reg):
    assert records.marker_constant(reg) == "YR-"
    assert len(records.records(reg)) >= 20


def test_lanes_authored_with_the_canon(reg):
    # The lanes table is the canon slice's data (slice 3, same PR as the canon tables). Every lane
    # maps to registered records — the shape rule the loader enforces, pinned live here. The
    # absent-means-nothing-mandated contract stays pinned on fixtures in test_check_trail.py.
    lanes = records.lanes(reg)
    assert set(lanes) >= {"design", "epic", "standalone", "close"}
    names = {r["name"] for r in records.records(reg)}
    for lane, wanted in lanes.items():
        assert wanted and set(wanted) <= names, lane


def test_every_yr_family_marker_is_under_the_umbrella(reg):
    yr = records.marker_constant(reg)
    for r in records.records(reg):
        if r["name"].startswith(yr):
            assert r["marker"].startswith(yr), r["name"]


# ── it-33 slice 3 (epic #455): every machinery record carries the statement ─────────────────────────

def test_machinery_records_carry_the_commit_field(reg):
    """Every declared record `records.toml`'s own callout names — YR-MERGE, YR-MERGE-SHADOW,
    YR-AUTO-PROMOTED, the six YR-EPIC-GATE raise rows, and YR-CLOSE-HOLD — gained `commit` in `fields`
    (the emitting surface's `provenance.statement()` line, `tools/provenance.py`)."""
    names = [
        "YR-MERGE", "YR-MERGE-SHADOW", "YR-AUTO-PROMOTED",
        "YR-EPIC-GATE: no-approval", "YR-EPIC-GATE: not-a-task", "YR-EPIC-GATE: not-onboarded",
        "YR-EPIC-GATE: open-questions", "YR-EPIC-GATE: gate-touching", "YR-EPIC-GATE: stranded claim",
        "YR-CLOSE-HOLD",
    ]
    for name in names:
        assert "commit" in records.get(reg, name)["fields"], name


def test_round_record_gains_deployed(reg):
    r = records.get(reg, "YR-ROUND-RECORD")
    assert "deployed" in r["fields"]
    # the pre-existing four fields stay — additive, never a silent narrowing
    assert {"refusals", "records-demanded", "detector-findings", "escalations"} <= set(r["fields"])


def test_deploy_record_registered(reg):
    r = records.get(reg, "YR-DEPLOY")
    assert r["marker"] == "YR-DEPLOY:"
    assert r["mode"] == "prefix"
    assert set(r["fields"]) == {"surface", "commit", "who", "restart"}
    assert set(r["emitted_by"]) == {"human", "attended-agent"}
    assert r["surfaces"] == ["issue-trail"]


def test_get_unregistered_is_loud(reg):
    with pytest.raises(records.RegistryError, match="unsanctioned"):
        records.get(reg, "YR-NEVER-MINTED")


# ── loader shape rules fail loud ─────────────────────────────────────────────────────────────────

def _write(tmp_path, body):
    p = tmp_path / "r.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_marker_constant_refused(tmp_path):
    p = _write(tmp_path, '[[record]]\nname = "X"\nmarker = "X:"\nmode = "prefix"\nsurfaces = ["pr-trail"]\n')
    with pytest.raises(records.RegistryError, match=r"\[marker\]\.yr"):
        records.load(p)


def test_duplicate_name_refused(tmp_path):
    row = '[[record]]\nname = "X"\nmarker = "X:"\nmode = "prefix"\nsurfaces = ["pr-trail"]\n'
    p = _write(tmp_path, '[marker]\nyr = "YR-"\n' + row + row)
    with pytest.raises(records.RegistryError, match="duplicate"):
        records.load(p)


def test_unknown_mode_refused(tmp_path):
    p = _write(tmp_path, '[marker]\nyr = "YR-"\n[[record]]\nname = "X"\nmarker = "X:"\nmode = "vibes"\nsurfaces = ["pr-trail"]\n')
    with pytest.raises(records.RegistryError, match="mode"):
        records.load(p)


def test_unknown_surface_refused(tmp_path):
    p = _write(tmp_path, '[marker]\nyr = "YR-"\n[[record]]\nname = "X"\nmarker = "X:"\nmode = "prefix"\nsurfaces = ["slack"]\n')
    with pytest.raises(records.RegistryError, match="surface"):
        records.load(p)


def test_missing_emitter_refused(tmp_path):
    p = _write(tmp_path, '[marker]\nyr = "YR-"\n[[record]]\nname = "X"\nmarker = "X:"\nmode = "prefix"\nreaders = ["y"]\nsurfaces = ["pr-trail"]\n')
    with pytest.raises(records.RegistryError, match="emitter"):
        records.load(p)


def test_missing_readers_refused(tmp_path):
    p = _write(tmp_path, '[marker]\nyr = "YR-"\n[[record]]\nname = "X"\nmarker = "X:"\nmode = "prefix"\nemitter = "e"\nsurfaces = ["pr-trail"]\n')
    with pytest.raises(records.RegistryError, match="readers"):
        records.load(p)


def test_lanes_table_is_refused_and_emitted_by_required(tmp_path):
    """The migration's one-authority rule: lane mandates compile from process.toml, so a registry
    [lanes] table is refused loud; and every row carries the typed emitted_by column (rule S)."""
    base = ('[marker]\nyr = "YR-"\n[[record]]\nname = "X"\nmarker = "X:"\nmode = "prefix"\n'
            'emitter = "e"\nemitted_by = ["machinery"]\nreaders = ["y"]\nsurfaces = ["pr-trail"]\n')
    with pytest.raises(records.RegistryError, match="no longer lives here"):
        records.load(_write(tmp_path, base + '[lanes]\nattended = ["X"]\n'))
    no_eb = base.replace('emitted_by = ["machinery"]\n', "")
    with pytest.raises(records.RegistryError, match="emitted_by"):
        records.load(_write(tmp_path, no_eb))
    bad_cls = base.replace('["machinery"]', '["robot-overlord"]')
    with pytest.raises(records.RegistryError, match="emitted_by"):
        records.load(_write(tmp_path, bad_cls))


def test_merge_record_schema_registered(reg):
    # Review blocker 1: the fenced JSON block merge_shadow parses back out of its own comments.
    r = records.get(reg, "yr-merge-record/1")
    assert r["mode"] == "json-schema"
    src = (REPO / "tools" / "merge_shadow.py").read_text(encoding="utf-8")
    assert 'SCHEMA = "yr-merge-record/1"' in src


# ── agreement pins: inline literals match their registry rows ────────────────────────────────────

def test_claim_gate_constants_agree(reg):
    # tools/dev-runner.sh embeds the claim-time gates check (python heredoc): MARKER + FIELDS.
    r = records.get(reg, "YR-TASK-GATES")
    region = DEV_RUNNER[DEV_RUNNER.index('MARKER = "YR-TASK-GATES"'):]
    m = re.search(r'MARKER = "([^"]+)"', region)
    f = re.search(r'FIELDS = \(([^)]+)\)', region)
    assert m and m.group(1) == r["marker"]
    inline_fields = [x.strip().strip('"') for x in f.group(1).split(",") if x.strip()]
    assert inline_fields == r["fields"]
    assert r["mode"] == "strict-line"


def test_stage_escape_case_arm_agrees(reg):
    r = records.get(reg, "STAGE-BLOCKED")
    # The case-arm literal derives from the ROW, so a registry edit breaks this pin through the row:
    # "STAGE-BLOCKED: "?*)  — prefix with a mandatory single following char.
    assert f'"{r["marker"]}"?*)' in DEV_RUNNER
    assert r["mode"] == "stage-escape"


def test_review_verdict_literal_agrees(reg):
    r = records.get(reg, "VERDICT")
    # Anchored to the GATE's own comparison, not any prose mention of the literal.
    gate = f'"$(verdict_line "$RUN_DIR/review.md")" = "{r["marker"]} APPROVE"'
    assert gate in DEV_RUNNER
    assert r["mode"] == "verdict-line"


def test_textutil_modes_are_registry_modes(reg):
    assert textutil.MARKER_SENTINEL in records.MODES
    assert textutil.MARKER_PREFIX in records.MODES


def test_epic_gate_reader_modes_agree(reg):
    # The epic-gate reads YR-EPIC-APPROVAL as prefix and YR-DEBT-LEDGER as sentinel — the registry
    # rows say the same, and the source says what it said when the rows were written.
    src = (REPO / "tools" / "epic_gate.py").read_text(encoding="utf-8")
    assert records.get(reg, "YR-EPIC-APPROVAL")["mode"] == "prefix"
    assert re.search(r'APPROVAL_MARKER,\s*mode="prefix"', src)
    assert records.get(reg, "YR-DEBT-LEDGER")["mode"] == "sentinel"
    assert re.search(r'LEDGER_MARKER,\s*mode="sentinel"', src)


def test_ledger_schema_agrees(reg):
    src = (REPO / "tools" / "ledger.py").read_text(encoding="utf-8")
    r = records.get(reg, "yr-ledger-row/1")
    assert 'ROW_SCHEMA = "yr-ledger-row/1"' in src
    assert r["mode"] == "json-schema"


# ── the CLI ──────────────────────────────────────────────────────────────────────────────────────

def test_cli_validate_and_list_and_marker():
    for args, expect in (
        (["validate"], "records: ok"),
        (["marker"], "YR-"),
        (["list"], "YR-TASK-GATES"),
        (["show", "YR-NIT"], "nit_harvest"),
    ):
        out = subprocess.run(
            [sys.executable, str(REPO / "tools" / "records.py"), *args],
            capture_output=True, text=True, check=True,
        )
        assert expect in out.stdout


def test_cli_malformed_registry_exits_one(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("not toml [", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "records.py"), "--registry", str(p), "validate"],
        capture_output=True, text=True,
    )
    assert out.returncode == 1
    assert "ERROR" in out.stderr
