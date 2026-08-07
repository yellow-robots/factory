"""The trail-shape detector (tools/check_trail.py, it-30 slice 2, epic #415).

Fixtures only — no network, no live vault. The core (`check_texts`) is pure; the CLI is exercised on
its offline paths (registry errors, the empty-lanes contract). Content-blindness is pinned: a present,
well-formed record passes regardless of what its payload says.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_trail  # noqa: E402
import records  # noqa: E402

BASE = (
    '[marker]\nyr = "YR-"\n'
    '[[record]]\nname = "YR-EPIC-APPROVAL"\nmarker = "YR-EPIC-APPROVAL"\nmode = "prefix"\n'
    'fields = ["design", "review", "who"]\nemitter = "e"\nreaders = ["r"]\nsurfaces = ["issue-trail"]\n'
    '[[record]]\nname = "YR-DEBT-LEDGER"\nmarker = "YR-DEBT-LEDGER"\nmode = "sentinel"\n'
    'emitter = "e"\nreaders = ["r"]\nsurfaces = ["issue-trail"]\n'
    '[[record]]\nname = "REVIEW-RECORD"\nmarker = "REVIEW-RECORD:"\nmode = "prefix"\n'
    'emitter = "e"\nreaders = ["r"]\nsurfaces = ["vault-doc"]\n'
)


def _reg(tmp_path, extra=""):
    p = tmp_path / "r.toml"
    p.write_text(BASE + extra, encoding="utf-8")
    return records.load(p)


LANES = '[lanes]\nepic = ["YR-EPIC-APPROVAL", "YR-DEBT-LEDGER"]\ndesign = ["REVIEW-RECORD"]\n'


# ── the empty-lanes contract ─────────────────────────────────────────────────────────────────────

def test_no_lanes_means_nothing_mandated(tmp_path):
    reg = _reg(tmp_path)
    assert check_trail.check_texts(reg, "epic", {"issue-trail": ["anything"]}) == []


def test_unknown_lane_is_a_finding(tmp_path):
    reg = _reg(tmp_path, LANES)
    fs = check_trail.check_texts(reg, "nonesuch", {})
    assert len(fs) == 1 and "not in the lanes table" in fs[0]


# ── presence + grammar, per mode ─────────────────────────────────────────────────────────────────

APPROVAL = "YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: passed\nwho: operator\n"


def test_clean_trail_passes(tmp_path):
    reg = _reg(tmp_path, LANES)
    texts = {"issue-trail": [APPROVAL, "YR-DEBT-LEDGER\nitems=3 net-lines=-120\n"]}
    assert check_trail.check_texts(reg, "epic", texts) == []


def test_absent_record_is_a_finding(tmp_path):
    reg = _reg(tmp_path, LANES)
    fs = check_trail.check_texts(reg, "epic", {"issue-trail": [APPROVAL]})
    assert len(fs) == 1 and "YR-DEBT-LEDGER" in fs[0] and "absent" in fs[0]


def test_prefix_mode_rejects_indented_and_inline_mentions(tmp_path):
    reg = _reg(tmp_path, LANES)
    texts = {"issue-trail": ["  YR-EPIC-APPROVAL indented\nsee `YR-EPIC-APPROVAL` inline\n",
                            "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", texts)
    assert len(fs) == 1 and "YR-EPIC-APPROVAL" in fs[0]


def test_sentinel_mode_tolerates_indent_but_not_prose(tmp_path):
    reg = _reg(tmp_path, LANES)
    ok = {"issue-trail": [APPROVAL, "   YR-DEBT-LEDGER   \n"]}
    assert check_trail.check_texts(reg, "epic", ok) == []
    prose = {"issue-trail": [APPROVAL, "the YR-DEBT-LEDGER record is coming\n"]}
    fs = check_trail.check_texts(reg, "epic", prose)
    assert len(fs) == 1 and "YR-DEBT-LEDGER" in fs[0]


def test_malformed_fields_is_a_finding_not_content_judgment(tmp_path):
    reg = _reg(tmp_path, LANES)
    # who: missing → malformed. The VALUES are never judged — nonsense values pass.
    texts = {"issue-trail": ["YR-EPIC-APPROVAL\ndesign: utter nonsense\nreview: gibberish\n",
                            "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", texts)
    assert len(fs) == 1 and "missing field(s): who" in fs[0]


def test_content_blindness(tmp_path):
    reg = _reg(tmp_path, LANES)
    texts = {"issue-trail": ["YR-EPIC-APPROVAL\ndesign: x\nreview: THIS REVIEW NEVER HAPPENED\nwho: nobody\n",
                            "YR-DEBT-LEDGER\n"]}
    assert check_trail.check_texts(reg, "epic", texts) == []


# ── surface dispatch, vault-doc included ─────────────────────────────────────────────────────────

def test_vault_doc_surface_dispatch(tmp_path):
    reg = _reg(tmp_path, LANES)
    ok = {"vault-doc": ["---\ntype: product-spec\n---\nREVIEW-RECORD: cold pass, 3 blockers folded\n"]}
    assert check_trail.check_texts(reg, "design", ok) == []
    wrong_surface = {"issue-trail": ["REVIEW-RECORD: on the wrong surface\n"]}
    fs = check_trail.check_texts(reg, "design", wrong_surface)
    assert len(fs) == 1 and "no readable surface in scope" in fs[0]


def test_fetch_vault_docs_reads_files_and_is_loud_on_missing(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "spec.md").write_text("REVIEW-RECORD: ok\n", encoding="utf-8")
    assert check_trail.fetch_vault_docs(tmp_path, ["d/spec.md"]) == ["REVIEW-RECORD: ok\n"]
    with pytest.raises(RuntimeError, match="unreadable"):
        check_trail.fetch_vault_docs(tmp_path, ["d/spec.md", "d/missing.md"])


# ── the four other modes, behaviorally pinned ────────────────────────────────────────────────────

MODES_EXTRA = (
    '[[record]]\nname = "GATES"\nmarker = "GATES-RECORD"\nmode = "strict-line"\n'
    'emitter = "e"\nreaders = ["r"]\nsurfaces = ["issue-trail"]\n'
    '[[record]]\nname = "VERDICT"\nmarker = "VERDICT:"\nmode = "verdict-line"\n'
    'emitter = "e"\nreaders = ["r"]\nsurfaces = ["pr-trail"]\n'
    '[[record]]\nname = "ESCAPE"\nmarker = "ESCAPE: "\nmode = "stage-escape"\n'
    'emitter = "e"\nreaders = ["r"]\nsurfaces = ["stage-log"]\n'
    '[[record]]\nname = "row/1"\nmarker = "row/1"\nmode = "json-schema"\n'
    'emitter = "e"\nreaders = ["r"]\nsurfaces = ["ledger"]\n'
)
LANES_EXTRA = ('[lanes]\ngates = ["GATES"]\nreview = ["VERDICT"]\nstage = ["ESCAPE"]\nledger = ["row/1"]\n')


def _reg2(tmp_path):
    p = tmp_path / "r2.toml"
    p.write_text(BASE + MODES_EXTRA + LANES_EXTRA, encoding="utf-8")
    return records.load(p)


def test_strict_line_mode(tmp_path):
    reg = _reg2(tmp_path)
    assert check_trail.check_texts(reg, "gates", {"issue-trail": ["GATES-RECORD   \nwho: x\n"]}) == []
    assert check_trail.check_texts(reg, "gates", {"issue-trail": ["  GATES-RECORD\n"]})  # indented: finding
    assert check_trail.check_texts(reg, "gates", {"issue-trail": ["GATES-RECORD extra\n"]})  # suffix: finding


def test_verdict_line_mode(tmp_path):
    reg = _reg2(tmp_path)
    assert check_trail.check_texts(reg, "review", {"pr-trail": ["VERDICT: APPROVE\n"]}) == []
    assert check_trail.check_texts(reg, "review", {"pr-trail": ["> VERDICT: APPROVE\n"]})  # blockquoted: finding


def test_stage_escape_mode(tmp_path):
    reg = _reg2(tmp_path)
    assert check_trail.check_texts(reg, "stage", {"stage-log": ["work\nESCAPE: real reason\n"]}) == []
    assert check_trail.check_texts(reg, "stage", {"stage-log": ["ESCAPE: mid\nmore work\n"]})  # not last: finding
    assert check_trail.check_texts(reg, "stage", {"stage-log": ["work\nESCAPE: \n"]})  # empty reason: finding


def test_json_schema_mode_requires_a_parsing_object(tmp_path):
    reg = _reg2(tmp_path)
    ok = {"ledger": ['{"schema": "row/1", "cost": 1}\n']}
    assert check_trail.check_texts(reg, "ledger", ok) == []
    fenced = {"ledger": ['prose\n```json\n{"schema": "row/1"}\n```\n']}
    assert check_trail.check_texts(reg, "ledger", fenced) == []
    prose = {"ledger": ["the row/1 schema is documented here\n"]}
    assert len(check_trail.check_texts(reg, "ledger", prose)) == 1
    broken = {"ledger": ['{"schema": "row/1"  \n']}
    assert len(check_trail.check_texts(reg, "ledger", broken)) == 1
    wrong_key = {"ledger": ['{"name": "row/1"}\n']}
    assert len(check_trail.check_texts(reg, "ledger", wrong_key)) == 1


def test_fields_must_be_complete_in_one_record(tmp_path):
    reg = _reg(tmp_path, LANES)
    pooled = {"issue-trail": ["YR-EPIC-APPROVAL\ndesign: x\n",
                             "YR-EPIC-APPROVAL\nreview: y\nwho: z\n",
                             "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", pooled)
    assert len(fs) == 1 and "missing field(s)" in fs[0]


def test_field_equals_form_is_boundary_anchored(tmp_path):
    reg = _reg(tmp_path, LANES)
    texts = {"issue-trail": ["YR-EPIC-APPROVAL\nredesign=x review=y who=z\n", "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", texts)
    assert len(fs) == 1 and "design" in fs[0]


# ── the CLI's offline paths ──────────────────────────────────────────────────────────────────────

def test_cli_empty_lanes_exits_zero_and_says_so(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text(BASE, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "check_trail.py"),
         "--registry", str(p), "--lane", "epic"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "nothing mandated" in out.stdout


def test_cli_malformed_registry_exits_two(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text("not toml [", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "check_trail.py"),
         "--registry", str(p), "--lane", "epic"],
        capture_output=True, text=True,
    )
    assert out.returncode == 2
    assert "ERROR" in out.stderr


def test_cli_vault_doc_without_root_exits_two(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text(BASE + LANES, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "check_trail.py"),
         "--registry", str(p), "--lane", "design", "--vault-doc", "x.md"],
        capture_output=True, text=True,
    )
    assert out.returncode == 2
    assert "--vault-root" in out.stderr


# ── the live registry stays detector-compatible ──────────────────────────────────────────────────

def test_live_registry_modes_all_dispatchable():
    reg = records.load()
    dispatchable = {"prefix", "sentinel", "strict-line", "verdict-line", "stage-escape", "json-schema"}
    for r in records.records(reg):
        assert r["mode"] in dispatchable
