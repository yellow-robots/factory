"""Tests for tools/review_bundle.py — the factory's canonical, incrementally-built, hashed review
bundle (issue #36).

Derived from the CRITERIA (the spec), not the implementation's internals:
  * a pre-review bundle assembled before the review stage: staged diff (base+head SHAs),
    acceptance-criteria block, check gate command/exit/output tail, resolved build/review entries
    with ranks;
  * each review round's verdict appended to the bundle as it lands;
  * a sha256 computed over the completed bundle at decision time;
  * the bundle written to the run directory as a single artifact;
  * canonical serialization so the hash is reproducible for identical inputs.

Exercises the module's public functions directly, and its CLI (`init` / `record-verdict`) as a
subprocess — the same two entry points tools/dev-runner.sh shells out to.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import review_bundle
from tools.review_bundle import (
    append_round, build_bundle, canonical_dumps, finalize, read_bundle, write_bundle,
)

REVIEW_BUNDLE_PY = ROOT / "tools" / "review_bundle.py"


def _sample(**overrides):
    kwargs = dict(
        base_sha="base123", head_sha="head456", diff="diff --git a/x b/x\n+hi\n",
        acceptance_criteria="- [ ] it works\n", check_cmd="pytest -q", check_exit=0,
        checks_log="collected 1 item\n1 passed\n", build_entry={"name": "sonnet", "rank": 30},
        review_entry={"name": "opus", "rank": 40},
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# build_bundle — the pre-review subset (AC: diff w/ base+head SHAs, acceptance criteria,
# check command/exit/output tail, resolved build/review entries with ranks)
# ---------------------------------------------------------------------------

def test_build_bundle_contains_diff_with_base_and_head_sha():
    b = build_bundle(**_sample())
    assert b["diff"]["base_sha"] == "base123"
    assert b["diff"]["head_sha"] == "head456"
    assert b["diff"]["patch"] == "diff --git a/x b/x\n+hi\n"


def test_build_bundle_contains_acceptance_criteria():
    b = build_bundle(**_sample(acceptance_criteria="- [ ] do the thing\n"))
    assert b["acceptance_criteria"] == "- [ ] do the thing\n"


def test_build_bundle_contains_check_command_and_exit():
    b = build_bundle(**_sample(check_cmd="make test", check_exit=1))
    assert b["check"]["command"] == "make test"
    assert b["check"]["exit_code"] == 1


def test_build_bundle_check_exit_is_int_even_if_passed_as_string():
    b = build_bundle(**_sample(check_exit="0"))
    assert b["check"]["exit_code"] == 0
    assert isinstance(b["check"]["exit_code"], int)


def test_build_bundle_check_output_tail_short_log_kept_whole():
    log = "line1\nline2\nline3\n"
    b = build_bundle(**_sample(checks_log=log))
    assert b["check"]["output_tail"] == "line1\nline2\nline3"


def test_build_bundle_check_output_tail_truncates_long_log():
    log = "\n".join(f"line{i}" for i in range(1, 101))  # 100 lines
    b = build_bundle(**_sample(checks_log=log))
    tail_lines = b["check"]["output_tail"].splitlines()
    assert tail_lines[0] == "line61"      # only the LAST 40 lines survive
    assert tail_lines[-1] == "line100"
    assert len(tail_lines) == 40


def test_build_bundle_contains_resolved_build_and_review_entries_with_ranks():
    b = build_bundle(**_sample(
        build_entry={"name": "sonnet", "id": "claude-sonnet-5", "provider": "anthropic", "rank": 30, "ranked": True},
        review_entry={"name": "opus", "id": "claude-opus-4-8", "provider": "anthropic", "rank": 40, "ranked": True},
    ))
    assert b["build"]["rank"] == 30 and b["build"]["name"] == "sonnet"
    assert b["review"]["rank"] == 40 and b["review"]["name"] == "opus"


def test_build_bundle_starts_with_no_rounds():
    b = build_bundle(**_sample())
    assert b["rounds"] == []


# ---------------------------------------------------------------------------
# append_round — each review round's verdict lands in the bundle
# ---------------------------------------------------------------------------

def test_append_round_captures_last_verdict_line():
    b = build_bundle(**_sample())
    transcript = "Reviewed the diff.\nNo blockers found.\nVERDICT: APPROVE\n"
    append_round(b, transcript)
    assert len(b["rounds"]) == 1
    assert b["rounds"][0]["verdict"] == "VERDICT: APPROVE"
    assert b["rounds"][0]["transcript"] == transcript


def test_append_round_uses_the_last_verdict_line_when_hedged():
    b = build_bundle(**_sample())
    transcript = "VERDICT: APPROVE\nactually wait\nVERDICT: REQUEST_CHANGES\n"
    append_round(b, transcript)
    assert b["rounds"][0]["verdict"] == "VERDICT: REQUEST_CHANGES"


def test_append_round_with_no_verdict_line_records_none():
    b = build_bundle(**_sample())
    append_round(b, "the reviewer crashed before saying anything")
    assert b["rounds"][0]["verdict"] is None


def test_append_round_accumulates_multiple_rounds_in_order():
    b = build_bundle(**_sample())
    append_round(b, "blockers found\nVERDICT: REQUEST_CHANGES\n")
    append_round(b, "fixed now\nVERDICT: APPROVE\n")
    assert [r["verdict"] for r in b["rounds"]] == ["VERDICT: REQUEST_CHANGES", "VERDICT: APPROVE"]
    assert [r["index"] for r in b["rounds"]] == [1, 2]


# ---------------------------------------------------------------------------
# finalize / canonical_dumps — decision-time sha256, canonical & reproducible
# ---------------------------------------------------------------------------

def test_finalize_adds_sha256_field():
    b = build_bundle(**_sample())
    out = finalize(b)
    assert "sha256" in out and isinstance(out["sha256"], str) and len(out["sha256"]) == 64


def test_finalize_hash_excludes_the_sha256_field_itself():
    b = build_bundle(**_sample())
    out = finalize(b)
    without_hash = {k: v for k, v in out.items() if k != "sha256"}
    expected = hashlib.sha256(canonical_dumps(without_hash).encode("utf-8")).hexdigest()
    assert out["sha256"] == expected


def test_identical_inputs_produce_identical_hash():
    b1 = finalize(build_bundle(**_sample()))
    b2 = finalize(build_bundle(**_sample()))
    assert b1["sha256"] == b2["sha256"]


def test_identical_inputs_produce_identical_hash_after_matching_rounds():
    b1 = build_bundle(**_sample())
    append_round(b1, "looks good\nVERDICT: APPROVE\n")
    b2 = build_bundle(**_sample())
    append_round(b2, "looks good\nVERDICT: APPROVE\n")
    assert finalize(b1)["sha256"] == finalize(b2)["sha256"]


def test_different_diff_produces_different_hash():
    b1 = finalize(build_bundle(**_sample(diff="patch A")))
    b2 = finalize(build_bundle(**_sample(diff="patch B")))
    assert b1["sha256"] != b2["sha256"]


def test_different_verdict_round_produces_different_hash():
    b1 = build_bundle(**_sample()); append_round(b1, "VERDICT: APPROVE\n")
    b2 = build_bundle(**_sample()); append_round(b2, "VERDICT: REQUEST_CHANGES\n")
    assert finalize(b1)["sha256"] != finalize(b2)["sha256"]


def test_canonical_dumps_is_stable_regardless_of_key_insertion_order():
    a = {"z": 1, "a": 2, "m": {"b": 1, "a": 2}}
    b = {"a": 2, "m": {"a": 2, "b": 1}, "z": 1}
    assert canonical_dumps(a) == canonical_dumps(b)


def test_hash_reproducible_across_separately_constructed_but_equal_bundles():
    """Same *contents*, built via independently-ordered kwarg calls -> identical hash — the whole
    point of canonical serialization (AC: 'serialize the bundle canonically so the hash is
    reproducible for identical inputs')."""
    b1 = build_bundle(
        base_sha="b", head_sha="h", diff="d", acceptance_criteria="ac",
        check_cmd="pytest", check_exit=0, checks_log="ok",
        build_entry={"rank": 30, "name": "sonnet"}, review_entry={"rank": 40, "name": "opus"},
    )
    b2 = build_bundle(
        review_entry={"name": "opus", "rank": 40}, build_entry={"name": "sonnet", "rank": 30},
        checks_log="ok", check_exit=0, check_cmd="pytest",
        acceptance_criteria="ac", diff="d", head_sha="h", base_sha="b",
    )
    assert finalize(b1)["sha256"] == finalize(b2)["sha256"]


# ---------------------------------------------------------------------------
# write_bundle / read_bundle — a single artifact on disk
# ---------------------------------------------------------------------------

def test_write_then_read_round_trips(tmp_path):
    b = finalize(build_bundle(**_sample()))
    path = tmp_path / "review-bundle.json"
    write_bundle(path, b)
    assert path.is_file()
    assert read_bundle(path) == b


def test_written_bundle_is_valid_json_and_canonical():
    b = finalize(build_bundle(**_sample()))
    assert canonical_dumps(b) == json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ---------------------------------------------------------------------------
# CLI — the two entry points tools/dev-runner.sh shells out to (init, record-verdict)
# ---------------------------------------------------------------------------

def _write(p, text):
    p.write_text(text)
    return p


def test_cli_init_writes_a_single_bundle_artifact(tmp_path):
    diff_file = _write(tmp_path / "diff.patch", "diff --git a/x b/x\n+hi\n")
    ac_file = _write(tmp_path / "ac.txt", "- [ ] it works\n")
    log_file = _write(tmp_path / "checks.log", "1 passed\n")
    bundle_path = tmp_path / "review-bundle.json"
    r = subprocess.run([
        sys.executable, str(REVIEW_BUNDLE_PY), "init",
        "--bundle", str(bundle_path), "--base-sha", "aaa", "--head-sha", "bbb",
        "--diff-file", str(diff_file), "--criteria-file", str(ac_file),
        "--checks-log", str(log_file), "--check-cmd", "pytest -q", "--check-exit", "0",
        "--build-json", json.dumps({"name": "sonnet", "rank": 30}),
        "--review-json", json.dumps({"name": "opus", "rank": 40}),
    ], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert bundle_path.is_file()
    data = json.loads(bundle_path.read_text())
    assert data["diff"]["base_sha"] == "aaa" and data["diff"]["head_sha"] == "bbb"
    assert data["diff"]["patch"] == "diff --git a/x b/x\n+hi\n"
    assert data["acceptance_criteria"] == "- [ ] it works\n"
    assert data["check"] == {"command": "pytest -q", "exit_code": 0, "output_tail": "1 passed"}
    assert data["build"]["name"] == "sonnet" and data["build"]["rank"] == 30
    assert data["review"]["name"] == "opus" and data["review"]["rank"] == 40
    assert data["rounds"] == []


def test_cli_init_omits_hash_before_any_round(tmp_path):
    """The pre-review bundle handed to the reviewer has no decision yet -> no sha256 field until
    finalize()/record-verdict runs (the hash is a DECISION-TIME artifact)."""
    diff_file = _write(tmp_path / "diff.patch", "diff\n")
    ac_file = _write(tmp_path / "ac.txt", "- [ ] x\n")
    log_file = _write(tmp_path / "checks.log", "ok\n")
    bundle_path = tmp_path / "review-bundle.json"
    r = subprocess.run([
        sys.executable, str(REVIEW_BUNDLE_PY), "init",
        "--bundle", str(bundle_path), "--base-sha", "aaa", "--head-sha", "bbb",
        "--diff-file", str(diff_file), "--criteria-file", str(ac_file),
        "--checks-log", str(log_file), "--check-cmd", "pytest -q", "--check-exit", "0",
    ], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "sha256" not in json.loads(bundle_path.read_text())


def test_cli_init_then_record_verdict_appends_round_and_hashes(tmp_path):
    diff_file = _write(tmp_path / "diff.patch", "diff\n")
    ac_file = _write(tmp_path / "ac.txt", "- [ ] x\n")
    log_file = _write(tmp_path / "checks.log", "ok\n")
    bundle_path = tmp_path / "review-bundle.json"
    subprocess.run([
        sys.executable, str(REVIEW_BUNDLE_PY), "init",
        "--bundle", str(bundle_path), "--base-sha", "aaa", "--head-sha", "bbb",
        "--diff-file", str(diff_file), "--criteria-file", str(ac_file),
        "--checks-log", str(log_file), "--check-cmd", "pytest -q", "--check-exit", "0",
    ], check=True, capture_output=True, text=True)

    review_file = _write(tmp_path / "review.md", "no blockers\nVERDICT: APPROVE\n")
    r = subprocess.run([
        sys.executable, str(REVIEW_BUNDLE_PY), "record-verdict",
        "--bundle", str(bundle_path), "--file", str(review_file),
    ], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    data = json.loads(bundle_path.read_text())
    assert len(data["rounds"]) == 1
    assert data["rounds"][0]["verdict"] == "VERDICT: APPROVE"
    assert "sha256" in data and len(data["sha256"]) == 64
    without_hash = {k: v for k, v in data.items() if k != "sha256"}
    assert data["sha256"] == hashlib.sha256(
        json.dumps(without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def test_cli_record_verdict_twice_accumulates_rounds_and_changes_hash(tmp_path):
    diff_file = _write(tmp_path / "diff.patch", "diff\n")
    ac_file = _write(tmp_path / "ac.txt", "- [ ] x\n")
    log_file = _write(tmp_path / "checks.log", "ok\n")
    bundle_path = tmp_path / "review-bundle.json"
    subprocess.run([
        sys.executable, str(REVIEW_BUNDLE_PY), "init",
        "--bundle", str(bundle_path), "--base-sha", "aaa", "--head-sha", "bbb",
        "--diff-file", str(diff_file), "--criteria-file", str(ac_file),
        "--checks-log", str(log_file), "--check-cmd", "pytest -q", "--check-exit", "0",
    ], check=True, capture_output=True, text=True)

    round1 = _write(tmp_path / "round1.md", "blockers found\nVERDICT: REQUEST_CHANGES\n")
    subprocess.run([sys.executable, str(REVIEW_BUNDLE_PY), "record-verdict",
                     "--bundle", str(bundle_path), "--file", str(round1)], check=True, capture_output=True, text=True)
    hash_after_round1 = json.loads(bundle_path.read_text())["sha256"]

    round2 = _write(tmp_path / "round2.md", "fixed\nVERDICT: APPROVE\n")
    subprocess.run([sys.executable, str(REVIEW_BUNDLE_PY), "record-verdict",
                     "--bundle", str(bundle_path), "--file", str(round2)], check=True, capture_output=True, text=True)
    data = json.loads(bundle_path.read_text())

    assert [r["verdict"] for r in data["rounds"]] == ["VERDICT: REQUEST_CHANGES", "VERDICT: APPROVE"]
    assert data["sha256"] != hash_after_round1     # the decision-time hash moves as rounds land


def test_cli_init_resolved_pair_defaults_to_empty_object_when_omitted(tmp_path):
    """--build-json/--review-json are optional at the CLI layer; still yields well-formed JSON."""
    diff_file = _write(tmp_path / "diff.patch", "diff\n")
    ac_file = _write(tmp_path / "ac.txt", "- [ ] x\n")
    log_file = _write(tmp_path / "checks.log", "ok\n")
    bundle_path = tmp_path / "review-bundle.json"
    r = subprocess.run([
        sys.executable, str(REVIEW_BUNDLE_PY), "init",
        "--bundle", str(bundle_path), "--base-sha", "aaa", "--head-sha", "bbb",
        "--diff-file", str(diff_file), "--criteria-file", str(ac_file),
        "--checks-log", str(log_file), "--check-cmd", "pytest -q", "--check-exit", "0",
    ], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(bundle_path.read_text())
    assert data["build"] == {} and data["review"] == {}
