"""Characterization pins for issue #150 — the KEPT `VERDICT:` grammar, across every surface that
reads it, before any consolidation touches the merge gate's input path. Purely accretive: no
production file changes.

Surfaces pinned (the ones the next slice will unify):
  * the runner's review gate — tools/dev-runner.sh review_stage(), the inline
    `grep -E '^VERDICT:' "$RUN_DIR/review.md" | tail -n1 | sed -E 's/[[:space:]]+$//'` compared
    exactly to "VERDICT: APPROVE" (~L906);
  * the runner's terminal-approval re-read — tools/dev-runner.sh shadow_terminal_approval(), the
    SAME grep|tail|sed pipeline over the same file, read again at merge-decision time (~L184-187);
  * tools/review_bundle.py's verdict extraction — append_round(), which picks the last line
    identified as a verdict line out of a review transcript (~L51-59).

The kept grammar (documented at the runner's review-gate comment block):
  * line-anchored `VERDICT:` — a prose or quoted mention never counts;
  * the LAST such line wins;
  * trailing whitespace is stripped;
  * pass requires EXACTLY `VERDICT: APPROVE`.

Deliberately NOT pinned: review_bundle.py's identification of a verdict line is case-INSENSITIVE
(`line.strip().upper().startswith("VERDICT:")`), so a lowercase `verdict: approve` line IS picked up
as a verdict there, unlike the runner's case-sensitive `grep -E '^VERDICT:'`. That divergence is the
drift the next slice removes — pinning it here would make that prune impossible. Case-strictness is
therefore only pinned on the two runner surfaces.

Harness: reuses the stubbed, no-live-LLM fixture idiom already established in this suite —
tests/test_dev_runner.py's stage-aware `claude`/`gh` stubs (STUB_REVIEW_VERDICT feeds an exact
review.md body) drive the review gate end to end, tests/test_dev_runner_reevaluate.py's
`--re-evaluate` two-stage harness re-reads a review.md fixture in isolation from the review gate
(no need to pass the gate to exercise the terminal re-read), and tools/review_bundle.py's
`append_round` is called directly, matching tests/test_review_bundle.py's style.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td                    # stubbed-runner fixtures (git repo, issue/item JSON)
import test_dev_runner_reevaluate as tr          # the --re-evaluate two-stage harness

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.review_bundle import append_round     # noqa: E402  (path must be set up first)


# ---------------------------------------------------------------------------------------------
# the agreement set: cases every one of the three surfaces must treat identically — line-anchor,
# last-line-wins, trailing-whitespace tolerance, exact-APPROVE-only pass. Each tuple is
# (name, transcript, expect_pass, expect_bundle_verdict): `expect_pass` is the runner surfaces'
# gate outcome, `expect_bundle_verdict` is review_bundle.py's extracted verdict field.
# ---------------------------------------------------------------------------------------------
GRAMMAR_CASES = [
    ("exact_approve",
     "VERDICT: APPROVE\n",
     True, "VERDICT: APPROVE"),
    ("non_approve_blocks",
     "VERDICT: REQUEST_CHANGES\n",
     False, "VERDICT: REQUEST_CHANGES"),
    ("trailing_whitespace_tolerated",
     "VERDICT: APPROVE   \n",
     True, "VERDICT: APPROVE"),
    ("last_line_wins_approve",
     "VERDICT: REQUEST_CHANGES\nVERDICT: APPROVE\n",
     True, "VERDICT: APPROVE"),
    ("last_line_wins_blocks",
     "VERDICT: APPROVE\nVERDICT: REQUEST_CHANGES\n",
     False, "VERDICT: REQUEST_CHANGES"),
    ("prose_mention_not_counted",
     "I believe the VERDICT: APPROVE is warranted here.\n",
     False, None),
    ("quoted_mention_not_counted",
     "> VERDICT: APPROVE\n",
     False, None),
]
GRAMMAR_IDS = [c[0] for c in GRAMMAR_CASES]

LOWERCASE_TRANSCRIPT = "verdict: approve\n"   # the drift: accepted by review_bundle.py, NOT by the runner


# ================= surface 1: the runner's review gate (review_stage(), end-to-end build) =============

def _review_gate_result(tmp_path, number, title, transcript):
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=number, title=title), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_VERDICT": transcript})
    return td._run([str(number), "--repo", "test/repo"], env)


@pytest.mark.parametrize("name,transcript,expect_pass,expect_bundle_verdict", GRAMMAR_CASES, ids=GRAMMAR_IDS)
def test_review_gate_pins_grammar(tmp_path, name, transcript, expect_pass, expect_bundle_verdict):
    r = _review_gate_result(tmp_path, 5, f"Grammar: {name}", transcript)
    if expect_pass:
        assert r.returncode == 0, r.stderr
        assert "https://stub/pr/1" in r.stdout
    else:
        assert r.returncode != 0
        assert "https://stub/pr/1" not in r.stdout


def test_review_gate_case_strict_rejects_lowercase(tmp_path):
    """Case-strictness (runner surface only — review_bundle.py's lowercase acceptance is the drift,
    not pinned here)."""
    r = _review_gate_result(tmp_path, 6, "Grammar: case-strict", LOWERCASE_TRANSCRIPT)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout


# ================= surface 2: the runner's terminal-approval re-read (shadow_terminal_approval(),  =====
# ================= exercised in isolation via --re-evaluate re-reading a review.md fixture)         =====

def _terminal_approval_result(tmp_path, number, title, transcript, pr_number):
    work, origin, env1, run_dir, branch, head_oid = tr._first_build(tmp_path, number=number, title=title)
    (run_dir / "review.md").write_text(transcript)   # overwrite: the fixture under test for this surface
    comments = [tr._rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = tr._reeval_env(tmp_path, env1, pr_number=pr_number, head_ref=branch, head_oid=head_oid,
                          comments=comments)
    r = tr._run_reeval(number, pr_number, env2)
    assert r.returncode == 0, r.stderr
    body = tr._reeval_body(run_dir)
    assert body is not None, "no re-evaluation record was written"
    return td._shadow_block(body)


@pytest.mark.parametrize("name,transcript,expect_pass,expect_bundle_verdict", GRAMMAR_CASES, ids=GRAMMAR_IDS)
def test_terminal_approval_reread_pins_grammar(tmp_path, name, transcript, expect_pass, expect_bundle_verdict):
    rec = _terminal_approval_result(tmp_path, 50, f"Grammar B: {name}", transcript, pr_number=200)
    if expect_pass:
        assert rec["decision"] == "WOULD-MERGE"
        assert rec["failed_condition"] is None
    else:
        assert rec["decision"] == "WOULD-BLOCK"
        assert rec["failed_condition"] == "terminal_approval"


def test_terminal_approval_reread_case_strict_rejects_lowercase(tmp_path):
    """Case-strictness (runner surface only)."""
    rec = _terminal_approval_result(tmp_path, 51, "Grammar B: case-strict", LOWERCASE_TRANSCRIPT,
                                    pr_number=201)
    assert rec["decision"] == "WOULD-BLOCK"
    assert rec["failed_condition"] == "terminal_approval"


# ================= surface 3: tools/review_bundle.py's verdict extraction (append_round()) =============
# review_bundle.py never gates on its own — it stores whichever last verdict-shaped line it finds, so a
# non-APPROVE last line is still pinned here as the exact non-approve string, which is the signal any
# downstream consumer (e.g. the re-evaluate re-read, which reads its own file independently) would block
# on.

@pytest.mark.parametrize("name,transcript,expect_pass,expect_bundle_verdict", GRAMMAR_CASES, ids=GRAMMAR_IDS)
def test_review_bundle_extraction_pins_grammar(name, transcript, expect_pass, expect_bundle_verdict):
    bundle = {}
    append_round(bundle, transcript)
    assert bundle["rounds"][0]["verdict"] == expect_bundle_verdict

# NOTE: no case exercises LOWERCASE_TRANSCRIPT against review_bundle.py's extraction — its
# case-insensitive identification of a verdict line is the drift the next slice removes, and pinning it
# would make that prune impossible (constraint from issue #150).
