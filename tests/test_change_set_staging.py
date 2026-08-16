"""it-31 slice 3 (#435): change-set staging — the validator judges the group's end state.

Ruling 1's split tier is the constraint this composes with: the shipped tree's own load-time gate
is untouched (a broken tree still refuses to load); `validate --set` judges a PROPOSED end state —
a group of gate-touching edits that is invalid per-file and valid together stops fighting the
load-time tier one edit at a time. The staged registry is resolved from the staged model's own
`records_registry` reference when the set carries it (the crossing's named gotcha).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import process  # noqa: E402


NEW_ROW = '''
[[record]]
name = "YR-STAGED-PROBE"
marker = "YR-STAGED-PROBE:"
mode = "prefix"
fields = ["who"]
emitted_by = ["attended-agent"]
emitter = "a change-set staging test fixture"
readers = ["tools/check_trail.py"]
surfaces = ["issue-trail"]
notes = ""
'''

NEW_GUARD = '''
  [[transition.guard]]
  predicate = "record_present"
  args = { record = "YR-STAGED-PROBE" }
  why = "a staged guard citing a record only the staged registry carries"
'''


@pytest.fixture()
def staged(tmp_path):
    """A records+process pair that is INVALID per-file against the tree and VALID as a set:
    the staged model adds a guard citing a record only the staged registry carries."""
    model_text = (REPO / "process.toml").read_text(encoding="utf-8")
    anchor = '  [[transition.guard]]\n  predicate = "record_present"\n  args = { record = "YR-TASK-GATES" }'
    assert anchor in model_text, "fixture anchor drifted — realign with process.toml"
    staged_model = tmp_path / "process.toml"
    staged_model.write_text(model_text.replace(anchor, NEW_GUARD.strip("\n") + "\n\n" + anchor, 1),
                            encoding="utf-8")
    staged_registry = tmp_path / "records.toml"
    staged_registry.write_text((REPO / "records.toml").read_text(encoding="utf-8") + NEW_ROW,
                               encoding="utf-8")
    return staged_model, staged_registry


def test_staged_model_alone_fails_per_file(staged):
    staged_model, _ = staged
    with pytest.raises(process.ModelError):
        process.load(staged_model)


def test_the_set_end_state_loads(staged):
    staged_model, staged_registry = staged
    model = process.load_set([staged_model, staged_registry])
    assert "YR-STAGED-PROBE" in {r["name"] for r in model["_registry"]["record"]}


def test_shipped_tree_gate_untouched(staged):
    """The staging mode never relaxes the tree's own gate: the default load is byte-identical in
    behavior, and a staged set with a genuinely broken end state still refuses."""
    assert process.load() is not None
    staged_model, _ = staged
    with pytest.raises(process.ModelError):
        process.load_set([staged_model])          # the set WITHOUT the registry half: still broken


def test_set_names_the_files_it_cannot_validate(staged, capsys):
    """A change-set may carry files the load-time tier has no rules for (a wall, a hook); the
    validator names them as not-validated — loud, never silent."""
    staged_model, staged_registry = staged
    other = staged_model.parent / "wall.py"
    other.write_text("# staged code the load-time tier does not judge\n", encoding="utf-8")
    rc = process.main(["validate", "--set", str(staged_model), str(staged_registry), str(other)])
    out = capsys.readouterr()
    assert rc == 0
    assert "wall.py" in out.out + out.err and "not validated" in (out.out + out.err)


def test_cli_set_passes_and_per_file_fails(staged, tmp_path):
    staged_model, staged_registry = staged
    rc_set = process.main(["validate", "--set", str(staged_model), str(staged_registry)])
    assert rc_set == 0
    rc_alone = process.main(["validate", "--set", str(staged_model)])
    assert rc_alone == 1
