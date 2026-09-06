"""
Tests for issue #485 (it-32 slice 4) — README.md's manifest sentence states a
counting rule (every key tools/dev-runner.sh reads is documented in AGENTS.md
-> Conventions) instead of naming keys itself, and AGENTS.md's Conventions
section actually names every key the runner reads.

The key set is derived by regex from tools/dev-runner.sh's own read sites,
never hardcoded against today's README/AGENTS.md prose — the same "guard
derives its expectation from the tree" pattern as
test_operating_doc_consolidation.py::test_repo_map_lists_every_tracked_tools_path
(issue #397, commit eaec320). A newly added manifest key must be caught here
the same way an undocumented one would be, without editing this test.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

RUNNER = ROOT / "tools" / "dev-runner.sh"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _runner_manifest_keys():
    text = _text(RUNNER)

    bulk_match = re.search(r"for k in \(([^)]+)\):", text)
    assert bulk_match, "tools/dev-runner.sh is missing the bulk manifest-read tuple"
    keys = set(re.findall(r'"(\w+)"', bulk_match.group(1)))
    assert len(keys) >= 5, "bulk manifest-read tuple parsed suspiciously few keys"

    keys.update(re.findall(r"_manifest_read scalar (\w+)", text))
    keys.update(re.findall(r"_manifest_read strlist (\w+)", text))
    keys.update(re.findall(r"<\(_read_manifest_array (\w+)\)", text))

    assert re.search(r"_manifest_read bool", text), (
        "tools/dev-runner.sh is missing its bool manifest read (auto_merge)"
    )
    keys.add("auto_merge")

    return keys


def _agents_conventions_section():
    text = _text(AGENTS)
    start = text.index("\n## Conventions\n")
    end = text.index("\n## ", start + len("\n## Conventions\n"))
    return text[start:end]


def _readme_status_section():
    text = _text(README)
    start = text.index("\n## Status\n")
    return text[start:]


def test_runner_key_derivation_finds_fifteen_distinct_keys():
    # Locks the derivation to the spec's own count (issue #485: "the runner
    # reads fifteen"): the bulk tuple's seven (check_cmd, model, base_ref,
    # review_model, lint_cmd, lint_fix_cmd, lens_cmd) plus the eight scalar/
    # bool/list sites (merge_ci_timeout, server_ci, auto_merge, test_paths,
    # artifact_globs, stage_conduct, check_timeout, check_idle_timeout).
    keys = _runner_manifest_keys()
    assert keys == {
        "check_cmd", "model", "base_ref", "review_model",
        "lint_cmd", "lint_fix_cmd", "lens_cmd",
        "merge_ci_timeout", "server_ci", "auto_merge",
        "test_paths", "artifact_globs", "stage_conduct",
        "check_timeout", "check_idle_timeout",
    }, f"derived manifest key set drifted: {sorted(keys)!r}"


def test_every_runner_manifest_key_is_documented_in_agents_conventions():
    keys = _runner_manifest_keys()
    section = _agents_conventions_section()
    missing = [k for k in sorted(keys) if k not in section]
    assert not missing, (
        f"AGENTS.md's Conventions section does not name these manifest keys "
        f"tools/dev-runner.sh reads: {missing!r}"
    )


def test_key_derivation_is_live_dropping_a_key_is_caught():
    """Proves the guard above is live: a Conventions section missing one
    derived key must fail the same way a real newly added, undocumented key
    would."""
    keys = sorted(_runner_manifest_keys())
    dropped = keys[0]
    fake_section = " ".join(f"`{k}`" for k in keys[1:])
    missing = [k for k in keys if k not in fake_section]
    assert missing == [dropped]


def test_readme_manifest_sentence_states_the_counting_rule():
    section = _readme_status_section()
    assert re.search(r"every key.*dev-runner\.sh.*reads", section, re.DOTALL), (
        "README.md's Status section dropped the 'every key ... reads' counting rule"
    )
    assert re.search(r"Conventions", section), (
        "README.md's manifest sentence does not point at AGENTS.md's Conventions section"
    )


def test_readme_manifest_sentence_names_no_key_enumeration_of_its_own():
    keys = _runner_manifest_keys()
    section = _readme_status_section()
    named = sorted(k for k in keys if re.search(rf"`{re.escape(k)}`", section))
    assert not named, (
        f"README.md's manifest sentence names specific manifest keys {named!r} "
        f"itself instead of stating the counting rule alone"
    )


def test_readme_manifest_sentence_no_longer_names_the_stale_three_key_parenthesis():
    section = _readme_status_section()
    assert "check_cmd` / `model` / `base_ref`" not in section, (
        "README.md still carries the stale three-key parenthesis "
        "(check_cmd / model / base_ref) the manifest counting rule replaced"
    )
