"""Guard test for the harness's single classifier — moved here alongside claude_fake.py per the
19-harness-seam epic's slice 1: the accessor/classifier move and this guard's move land in one slice,
since splitting them deadlocks a mid-round tree between the guard's pin and the moved classifier.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "dev-runner.sh"


def test_runner_prompts_contain_stub_markers():
    """Guard: the stage-aware claude stub (tests/harness/claude_fake.py) classifies by the literals
    'TESTER', 'REVIEWER', 'tests FAIL', and 'REQUESTED CHANGES'. If the runner's prompts drop them the
    stub would silently misclassify, so fail loudly here."""
    src = RUNNER.read_text()
    assert "TESTER" in src and "REVIEWER" in src             # tester / reviewer role markers
    assert "tests FAIL" in src and "REQUESTED CHANGES" in src  # check-repair / review-repair markers
