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

EB = 'emitted_by = ["machinery"]\n'
BASE = (
    '[marker]\nyr = "YR-"\n'
    '[[record]]\nname = "YR-EPIC-APPROVAL"\nmarker = "YR-EPIC-APPROVAL"\nmode = "prefix"\n'
    'fields = ["design", "review", "who"]\nemitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["issue-trail"]\n'
    '[[record]]\nname = "YR-DEBT-LEDGER"\nmarker = "YR-DEBT-LEDGER"\nmode = "sentinel"\n'
    'emitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["issue-trail"]\n'
    '[[record]]\nname = "REVIEW-RECORD"\nmarker = "REVIEW-RECORD:"\nmode = "prefix"\n'
    'emitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["vault-doc"]\n'
)


def _reg(tmp_path, extra=""):
    p = tmp_path / "r.toml"
    p.write_text(BASE + extra, encoding="utf-8")
    return records.load(p)


# Lane mandates now compile from process.toml; fixtures pass their own map (the pure seam).
LANES = {"epic": ["YR-EPIC-APPROVAL", "YR-DEBT-LEDGER"], "design": ["REVIEW-RECORD"]}


# ── the empty-lanes contract ─────────────────────────────────────────────────────────────────────

def test_no_lanes_means_nothing_mandated(tmp_path):
    reg = _reg(tmp_path)
    assert check_trail.check_texts(reg, "epic", {"issue-trail": ["anything"]}, lanes_map={}) == []


def test_unknown_lane_is_a_finding(tmp_path):
    reg = _reg(tmp_path)
    fs = check_trail.check_texts(reg, "nonesuch", {}, lanes_map=LANES)
    assert len(fs) == 1 and "not in the compiled lanes" in fs[0]


# ── presence + grammar, per mode ─────────────────────────────────────────────────────────────────

APPROVAL = "YR-EPIC-APPROVAL\ndesign: [[spec]]\nreview: passed\nwho: operator\n"


def test_clean_trail_passes(tmp_path):
    reg = _reg(tmp_path)
    texts = {"issue-trail": [APPROVAL, "YR-DEBT-LEDGER\nitems=3 net-lines=-120\n"]}
    assert check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=texts) == []


def test_absent_record_is_a_finding(tmp_path):
    reg = _reg(tmp_path)
    fs = check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface={"issue-trail": [APPROVAL]})
    assert len(fs) == 1 and "YR-DEBT-LEDGER" in fs[0] and "absent" in fs[0]


def test_prefix_mode_rejects_indented_and_inline_mentions(tmp_path):
    reg = _reg(tmp_path)
    texts = {"issue-trail": ["  YR-EPIC-APPROVAL indented\nsee `YR-EPIC-APPROVAL` inline\n",
                            "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=texts)
    assert len(fs) == 1 and "YR-EPIC-APPROVAL" in fs[0]


def test_sentinel_mode_tolerates_indent_but_not_prose(tmp_path):
    reg = _reg(tmp_path)
    ok = {"issue-trail": [APPROVAL, "   YR-DEBT-LEDGER   \n"]}
    assert check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=ok) == []
    prose = {"issue-trail": [APPROVAL, "the YR-DEBT-LEDGER record is coming\n"]}
    fs = check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=prose)
    assert len(fs) == 1 and "YR-DEBT-LEDGER" in fs[0]


def test_malformed_fields_is_a_finding_not_content_judgment(tmp_path):
    reg = _reg(tmp_path)
    # who: missing → malformed. The VALUES are never judged — nonsense values pass.
    texts = {"issue-trail": ["YR-EPIC-APPROVAL\ndesign: utter nonsense\nreview: gibberish\n",
                            "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=texts)
    assert len(fs) == 1 and "missing field(s): who" in fs[0]


def test_content_blindness(tmp_path):
    reg = _reg(tmp_path)
    texts = {"issue-trail": ["YR-EPIC-APPROVAL\ndesign: x\nreview: THIS REVIEW NEVER HAPPENED\nwho: nobody\n",
                            "YR-DEBT-LEDGER\n"]}
    assert check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=texts) == []


# ── surface dispatch, vault-doc included ─────────────────────────────────────────────────────────

def test_vault_doc_surface_dispatch(tmp_path):
    reg = _reg(tmp_path)
    ok = {"vault-doc": ["---\ntype: product-spec\n---\nREVIEW-RECORD: cold pass, 3 blockers folded\n"]}
    assert check_trail.check_texts(reg, "design", lanes_map=LANES, texts_by_surface=ok) == []
    wrong_surface = {"issue-trail": ["REVIEW-RECORD: on the wrong surface\n"]}
    fs = check_trail.check_texts(reg, "design", lanes_map=LANES, texts_by_surface=wrong_surface)
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
    'emitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["issue-trail"]\n'
    '[[record]]\nname = "VERDICT"\nmarker = "VERDICT:"\nmode = "verdict-line"\n'
    'emitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["pr-trail"]\n'
    '[[record]]\nname = "ESCAPE"\nmarker = "ESCAPE: "\nmode = "stage-escape"\n'
    'emitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["stage-log"]\n'
    '[[record]]\nname = "row/1"\nmarker = "row/1"\nmode = "json-schema"\n'
    'emitter = "e"\n' + EB + 'readers = ["r"]\nsurfaces = ["ledger"]\n'
)
LANES_EXTRA = {"gates": ["GATES"], "review": ["VERDICT"], "stage": ["ESCAPE"], "ledger": ["row/1"]}


def _reg2(tmp_path):
    p = tmp_path / "r2.toml"
    p.write_text(BASE + MODES_EXTRA, encoding="utf-8")
    return records.load(p)


def test_strict_line_mode(tmp_path):
    reg = _reg2(tmp_path)
    assert check_trail.check_texts(reg, "gates", lanes_map=LANES_EXTRA, texts_by_surface={"issue-trail": ["GATES-RECORD   \nwho: x\n"]}) == []
    assert check_trail.check_texts(reg, "gates", lanes_map=LANES_EXTRA, texts_by_surface={"issue-trail": ["  GATES-RECORD\n"]})  # indented: finding
    assert check_trail.check_texts(reg, "gates", lanes_map=LANES_EXTRA, texts_by_surface={"issue-trail": ["GATES-RECORD extra\n"]})  # suffix: finding


def test_verdict_line_mode(tmp_path):
    reg = _reg2(tmp_path)
    assert check_trail.check_texts(reg, "review", lanes_map=LANES_EXTRA, texts_by_surface={"pr-trail": ["VERDICT: APPROVE\n"]}) == []
    assert check_trail.check_texts(reg, "review", lanes_map=LANES_EXTRA, texts_by_surface={"pr-trail": ["> VERDICT: APPROVE\n"]})  # blockquoted: finding


def test_stage_escape_mode(tmp_path):
    reg = _reg2(tmp_path)
    assert check_trail.check_texts(reg, "stage", lanes_map=LANES_EXTRA, texts_by_surface={"stage-log": ["work\nESCAPE: real reason\n"]}) == []
    assert check_trail.check_texts(reg, "stage", lanes_map=LANES_EXTRA, texts_by_surface={"stage-log": ["ESCAPE: mid\nmore work\n"]})  # not last: finding
    assert check_trail.check_texts(reg, "stage", lanes_map=LANES_EXTRA, texts_by_surface={"stage-log": ["work\nESCAPE: \n"]})  # empty reason: finding


def test_json_schema_mode_requires_a_parsing_object(tmp_path):
    reg = _reg2(tmp_path)
    ok = {"ledger": ['{"schema": "row/1", "cost": 1}\n']}
    assert check_trail.check_texts(reg, "ledger", lanes_map=LANES_EXTRA, texts_by_surface=ok) == []
    fenced = {"ledger": ['prose\n```json\n{"schema": "row/1"}\n```\n']}
    assert check_trail.check_texts(reg, "ledger", lanes_map=LANES_EXTRA, texts_by_surface=fenced) == []
    prose = {"ledger": ["the row/1 schema is documented here\n"]}
    assert len(check_trail.check_texts(reg, "ledger", lanes_map=LANES_EXTRA, texts_by_surface=prose)) == 1
    broken = {"ledger": ['{"schema": "row/1"  \n']}
    assert len(check_trail.check_texts(reg, "ledger", lanes_map=LANES_EXTRA, texts_by_surface=broken)) == 1
    wrong_key = {"ledger": ['{"name": "row/1"}\n']}
    assert len(check_trail.check_texts(reg, "ledger", lanes_map=LANES_EXTRA, texts_by_surface=wrong_key)) == 1


def test_fields_must_be_complete_in_one_record(tmp_path):
    reg = _reg(tmp_path)
    pooled = {"issue-trail": ["YR-EPIC-APPROVAL\ndesign: x\n",
                             "YR-EPIC-APPROVAL\nreview: y\nwho: z\n",
                             "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=pooled)
    assert len(fs) == 1 and "missing field(s)" in fs[0]


def test_field_equals_form_is_boundary_anchored(tmp_path):
    reg = _reg(tmp_path)
    texts = {"issue-trail": ["YR-EPIC-APPROVAL\nredesign=x review=y who=z\n", "YR-DEBT-LEDGER\n"]}
    fs = check_trail.check_texts(reg, "epic", lanes_map=LANES, texts_by_surface=texts)
    assert len(fs) == 1 and "design" in fs[0]


# ── the CLI's offline paths ──────────────────────────────────────────────────────────────────────

def test_cli_fixture_registry_fails_loud_not_silent(tmp_path):
    """A registry the model cannot load against must exit 2 LOUD — a silently-empty mandate set
    would disable the detector unnoticed (the exact failure class ruling 1 gates against)."""
    p = tmp_path / "r.toml"
    p.write_text(BASE, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "check_trail.py"),
         "--registry", str(p), "--lane", "epic"],
        capture_output=True, text=True,
    )
    assert out.returncode == 2
    assert "ERROR" in out.stderr


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
    p.write_text(BASE, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "check_trail.py"),
         "--registry", str(p), "--lane", "design", "--vault-doc", "x.md"],
        capture_output=True, text=True,
    )
    assert out.returncode == 2
    assert "--vault-root" in out.stderr


# ── it-33 slice 3 (epic #455): the v1.6.0 amendment's --scope-created effect, pinned both ways ─────
# process.toml's v1.6.0 amendment (effective 2026-09-06) widened YR-MERGE's fields with `commit`. A
# trail dated ON OR BEFORE the amendment's own ship date (2026-09-05, today) must still pass — the
# mandates it was actually held to (v1.5.1) never demanded the field. A trail dated on/after the
# effective date is judged under v1.6.0 and must fail when the field is missing. These exercise the
# CLI in-process (`_cli`) against the LIVE registry + process.toml, hermetically: the one external —
# `gh` — is injected via monkeypatching `fetch_pr_trail`, never a live network read.

_MISSING_COMMIT_PR_BODY = "YR-MERGE: MERGED\n\n```yr-merge-record\n{}\n```\n"


def test_scope_created_pre_ship_trail_is_version_scoped_out(monkeypatch, capsys):
    monkeypatch.setattr(check_trail, "fetch_pr_trail", lambda repo, n: [_MISSING_COMMIT_PR_BODY])
    rc = check_trail._cli(["--lane", "merge", "--pr", "1", "--scope-created", "2026-09-05"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "version-scoped" in out


def test_scope_created_post_ship_trail_fails_the_new_commit_field(monkeypatch, capsys):
    monkeypatch.setattr(check_trail, "fetch_pr_trail", lambda repo, n: [_MISSING_COMMIT_PR_BODY])
    rc = check_trail._cli(["--lane", "merge", "--pr", "1", "--scope-created", "2026-09-06"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "YR-MERGE" in out and "commit" in out


# ── the live registry stays detector-compatible ──────────────────────────────────────────────────

def test_live_registry_modes_all_dispatchable():
    reg = records.load()
    dispatchable = {"prefix", "sentinel", "strict-line", "verdict-line", "stage-escape", "json-schema"}
    for r in records.records(reg):
        assert r["mode"] in dispatchable
