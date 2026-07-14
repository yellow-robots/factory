"""Tests for Issue #168 — docs: the shadow seat and the bench reach the shipped references.

Derived from the Issue #168 acceptance criteria (the spec), not from the implementation's
internals: skills/factory/references/pipeline.md gains a shadow-review-seat section (dark by
default, the two env keys, the inert record grammars cited from code, a shadow failure never
fails a build) and a bench section (attended tool; corpus -> sealed replay -> deterministic
grading -> report; the seal rule; the grading caveat; never contending with the live dispatch
line). AGENTS.md gains the three bench record schemas, the two env keys, and the
never-a-line-anchored-VERDICT:-in-a-trail-comment rule. deploy/DISPATCH.md gains one paragraph:
the shadow keys ride the dispatch service environment, dark by default, operator-set. Every
addition must consolidate into an EXISTING section (no new doc file) and cite the defining code
by path rather than restate its grammar. The independent tester verifies: the diff (outside
tests/) is docs-only; every path/env key/symbol these additions cite actually exists in the
tree; no new doc file was added; tests/test_plugin_version_pin_canonical.py is untouched.
"""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "skills" / "factory" / "references" / "pipeline.md"
AGENTS = ROOT / "AGENTS.md"
DISPATCH_MD = ROOT / "deploy" / "DISPATCH.md"
VERSION_PIN_TEST = ROOT / "tests" / "test_plugin_version_pin_canonical.py"

ALLOWED_CHANGED_DOC_PATHS = {
    "AGENTS.md",
    "deploy/DISPATCH.md",
    "skills/factory/references/pipeline.md",
}

# Issue #168 shipped as this single merge commit (b84be92, parent 2b19472) — a closed, immutable
# slice of history. The scope checks below pin to that fixed commit range rather than the
# repo's moving base_ref: a moving base_ref would re-diff *every later* PR's own working tree
# against the docs-only invariant that only ever applied to #168's own change, failing any
# unrelated future PR (e.g. a version bump) that touches a non-doc, non-tests/ file.
MERGE_COMMIT = "b84be92a106a810149422a6b68317b491920ad77"
MERGE_PARENT = "2b19472d1389e05f5741f8ddfe05baffbf72771e"


def _text(path):
    return path.read_text(encoding="utf-8")


def _run_git(*args):
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=True
    ).stdout


def _changed_paths_in_merge_commit():
    """Every path #168's own merge commit (b84be92) touched, relative to its parent."""
    return set(_run_git("diff", "--name-only", MERGE_PARENT, MERGE_COMMIT).split())


def _md_paths_at_ref(ref):
    return {p for p in _run_git("ls-tree", "-r", "--name-only", ref).split() if p.endswith(".md")}


# ---------------------------------------------------------------------------------------------
# Test-expectation: docs-only diff (outside this stage's own tests/ additions), no new doc file
# ---------------------------------------------------------------------------------------------

def test_diff_outside_tests_touches_only_the_three_named_doc_files():
    changed = _changed_paths_in_merge_commit()
    outside_tests = {p for p in changed if not p.startswith("tests/")}
    unexpected = outside_tests - ALLOWED_CHANGED_DOC_PATHS
    assert not unexpected, (
        f"issue #168 is docs-only for pipeline.md/AGENTS.md/DISPATCH.md; found unexpected "
        f"non-doc, non-tests/ changes: {sorted(unexpected)}"
    )


def test_the_three_named_doc_files_are_modifications_not_additions():
    status = _run_git("diff", "--name-status", MERGE_PARENT, MERGE_COMMIT)
    for line in status.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1] in ALLOWED_CHANGED_DOC_PATHS:
            assert parts[0] == "M", (
                f"{parts[1]} should be a modification (M) of an existing doc, not {parts[0]!r}"
            )


def test_no_new_markdown_doc_file_was_added_anywhere_in_the_tree():
    before = _md_paths_at_ref(MERGE_PARENT)
    after = _md_paths_at_ref(MERGE_COMMIT)
    new_md = after - before
    assert not new_md, (
        f"docs are consolidated, not accreted (AGENTS.md > Invariants) — new .md file(s) "
        f"found: {sorted(new_md)}"
    )


def test_version_pin_test_file_is_untouched():
    diff = _run_git(
        "diff", "--name-only", MERGE_PARENT, MERGE_COMMIT,
        "--", str(VERSION_PIN_TEST.relative_to(ROOT)),
    )
    assert diff.strip() == "", (
        "tests/test_plugin_version_pin_canonical.py must stay untouched by this docs-only slice"
    )
    assert VERSION_PIN_TEST.exists(), "the version-pin test file itself must still exist"


# ---------------------------------------------------------------------------------------------
# pipeline.md — "The shadow review seat" section
# ---------------------------------------------------------------------------------------------

def _pipeline_section(heading):
    text = _text(PIPELINE)
    match = re.search(rf"(?m)^## {re.escape(heading)}\n(.*?)(?=\n^## |\Z)", text, re.DOTALL)
    assert match, f"pipeline.md is missing a top-level '## {heading}' section"
    return match.group(1)


def _shadow_section():
    return _pipeline_section("The shadow review seat")


def _bench_section():
    return _pipeline_section("The bench")


def test_pipeline_md_gains_a_shadow_review_seat_section():
    section = _shadow_section()
    assert section.strip(), "the shadow review seat section is empty"


def test_shadow_section_names_both_env_keys_as_dark_by_default():
    section = _shadow_section()
    assert "YR_SHADOW_MODEL" in section, "shadow section drops the YR_SHADOW_MODEL env key"
    assert "YR_SHADOW_BASE_URL" in section, "shadow section drops the YR_SHADOW_BASE_URL env key"
    assert re.search(r"dark by default|dark unless|dark", section, re.IGNORECASE), (
        "shadow section doesn't state the feature is dark by default"
    )
    assert re.search(r"\bboth\b", section, re.IGNORECASE), (
        "shadow section doesn't state BOTH keys are required (no partial-on state)"
    )


def test_shadow_section_a_failure_never_fails_a_build():
    section = _shadow_section()
    assert re.search(r"never\s+(?:wired into|escalated)|non-gating", section, re.IGNORECASE), (
        "shadow section doesn't state the shadow seat is never wired into the gate/merge decision"
    )
    assert re.search(
        r"(failure|fails?).{0,80}(logged|proceeds unchanged)|proceeds unchanged.{0,80}fail",
        section, re.IGNORECASE | re.DOTALL,
    ), "shadow section doesn't state a shadow-stage failure never fails the build"


def test_shadow_section_cites_the_grammars_by_code_path_not_restated():
    section = _shadow_section()
    assert "tools/dev-runner.sh" in section, "shadow section doesn't cite tools/dev-runner.sh"
    assert "tools/verdict_diff.py" in section, "shadow section doesn't cite tools/verdict_diff.py"
    assert "YR-SHADOW-REVIEW" in section, "shadow section drops the YR-SHADOW-REVIEW record token"
    assert "YR-VERDICT-DIFF" in section, "shadow section drops the YR-VERDICT-DIFF record token"
    # Cited, not restated: the raw extraction pipeline (the actual grammar implementation) must
    # not be copy-pasted into the doc.
    assert "grep -E" not in section, (
        "shadow section restates the raw VERDICT-extraction pipeline instead of citing it"
    )


def test_shadow_section_distinguishes_from_shadow_merge_choreography():
    section = _shadow_section()
    assert re.search(r"shadow merge choreography", section, re.IGNORECASE), (
        "shadow review seat section doesn't disambiguate itself from the pre-existing "
        "'Shadow merge choreography' section above it"
    )


# ---------------------------------------------------------------------------------------------
# pipeline.md — "The bench" section
# ---------------------------------------------------------------------------------------------

def test_pipeline_md_gains_a_bench_section():
    section = _bench_section()
    assert section.strip(), "the bench section is empty"


def test_bench_section_states_it_is_an_attended_tool_never_the_live_line():
    section = _bench_section()
    assert re.search(r"attended", section, re.IGNORECASE), (
        "bench section doesn't state the bench is an attended (host CLI) tool"
    )
    assert re.search(
        r"never contending with the live|no dispatch coupling|not.{0,20}dispatch",
        section, re.IGNORECASE,
    ), "bench section doesn't state the bench never contends with the live dispatch line"


def test_bench_section_states_the_four_stage_pipeline_in_order():
    section = _bench_section()
    for term in ["corpus", "sealed replay", "deterministic grading", "report"]:
        assert re.search(re.escape(term), section, re.IGNORECASE), (
            f"bench section is missing the {term!r} pipeline stage"
        )
    # The stage summary line itself (not just a mention of each word anywhere in the prose)
    # must state the four stages in order: corpus -> sealed replay -> deterministic grading ->
    # report.
    match = re.search(r"(?m)^Pipeline:\s*(.+)$", section)
    assert match, "bench section has no 'Pipeline: ...' stage-summary line"
    pipeline_line = match.group(1).lower()
    positions = [
        pipeline_line.index(term)
        for term in ["corpus", "sealed replay", "deterministic grading", "report"]
    ]
    assert positions == sorted(positions), (
        "bench section's Pipeline line states the stages out of order: expected corpus -> "
        "sealed replay -> deterministic grading -> report"
    )


def test_bench_section_states_the_seal_rule():
    section = _bench_section()
    assert re.search(r"seal", section, re.IGNORECASE), "bench section drops any mention of the seal"
    assert re.search(r"before any grading", section, re.IGNORECASE), (
        "bench section doesn't state the seal is verified BEFORE any grading"
    )
    assert re.search(r"invalid-seal", section), (
        "bench section doesn't name the invalid-seal outcome"
    )


def test_bench_section_states_the_grading_caveat():
    section = _bench_section()
    assert re.search(r"grading caveat", section, re.IGNORECASE), (
        "bench section doesn't name the grading caveat"
    )
    assert re.search(r"not independent proof of correctness", section, re.IGNORECASE), (
        "bench section drops the substance of the grading caveat"
    )
    assert "bench/corpus/README.md" in section, (
        "bench section doesn't cite bench/corpus/README.md as the caveat's defining home"
    )


def test_bench_section_cites_the_defining_tools_by_path():
    section = _bench_section()
    for path in ["tools/bench_corpus.py", "tools/bench_replay.py", "tools/bench_report.py"]:
        assert path in section, f"bench section doesn't cite {path}"


# ---------------------------------------------------------------------------------------------
# AGENTS.md — Conventions: bench record schemas, the two env keys, the VERDICT: trail-comment rule
# ---------------------------------------------------------------------------------------------

def _conventions_section():
    text = _text(AGENTS)
    match = re.search(r"(?m)^## Conventions\n(.*?)(?=\n^## |\Z)", text, re.DOTALL)
    assert match, "AGENTS.md is missing its '## Conventions' section"
    return match.group(1)


def test_agents_md_conventions_names_the_three_bench_record_schemas():
    section = _conventions_section()
    for schema in ["yr-bench-corpus/1", "yr-bench-result/1", "yr-verdict-diff/1"]:
        assert schema in section, f"AGENTS.md Conventions is missing the {schema!r} record schema"


def test_agents_md_conventions_names_the_two_env_keys():
    section = _conventions_section()
    assert "YR_SHADOW_MODEL" in section, "AGENTS.md Conventions is missing YR_SHADOW_MODEL"
    assert "YR_SHADOW_BASE_URL" in section, "AGENTS.md Conventions is missing YR_SHADOW_BASE_URL"
    assert re.search(r"both|neither", section, re.IGNORECASE), (
        "AGENTS.md Conventions doesn't state both-or-neither for the two shadow env keys"
    )


def test_agents_md_conventions_states_the_verdict_trail_comment_rule():
    section = _conventions_section()
    assert re.search(r"VERDICT:", section), (
        "AGENTS.md Conventions doesn't mention the VERDICT: grammar at all"
    )
    assert re.search(r"line-anchored", section, re.IGNORECASE), (
        "AGENTS.md Conventions doesn't state the rule is about a line-anchored VERDICT:"
    )
    assert re.search(r"never", section, re.IGNORECASE), (
        "AGENTS.md Conventions doesn't state the rule as a 'never' invariant"
    )
    assert re.search(r"only the gating review", section, re.IGNORECASE), (
        "AGENTS.md Conventions doesn't carve out the one exception: the gating review's own comment"
    )


def test_agents_md_conventions_cites_the_defining_tools_by_path():
    section = _conventions_section()
    for path in ["tools/bench_corpus.py", "tools/bench_replay.py", "tools/verdict_diff.py"]:
        assert path in section, f"AGENTS.md Conventions doesn't cite {path}"


# ---------------------------------------------------------------------------------------------
# deploy/DISPATCH.md — one paragraph: shadow keys ride the dispatch env, dark by default, operator-set
# ---------------------------------------------------------------------------------------------

def test_dispatch_md_states_shadow_keys_ride_the_dispatch_service_environment():
    text = _text(DISPATCH_MD)
    assert "YR_SHADOW_MODEL" in text, "DISPATCH.md doesn't mention YR_SHADOW_MODEL"
    assert "YR_SHADOW_BASE_URL" in text, "DISPATCH.md doesn't mention YR_SHADOW_BASE_URL"
    assert re.search(r"dark by default|dark unless|leave either unset", text, re.IGNORECASE), (
        "DISPATCH.md doesn't state the shadow keys are dark by default"
    )
    assert re.search(r"dispatch\.env", text), (
        "DISPATCH.md doesn't tie the shadow keys to the dispatch service's own env file, "
        "consistent with every other stage key in that doc"
    )


def test_dispatch_md_states_the_keys_are_operator_set():
    text = _text(DISPATCH_MD)
    assert re.search(r"operator.set|operator's to arm", text, re.IGNORECASE), (
        "DISPATCH.md doesn't state the shadow keys are operator-set"
    )
    assert re.search(r"auth is human work", text, re.IGNORECASE), (
        "DISPATCH.md doesn't tie the operator-set rule back to 'auth is human work'"
    )


def test_dispatch_md_shadow_paragraph_consolidates_under_an_existing_heading():
    text = _text(DISPATCH_MD)
    headings = re.findall(r"(?m)^#{2,3} (.+)$", text)
    shadow_headings = [h for h in headings if "shadow" in h.lower()]
    assert shadow_headings, "DISPATCH.md has no heading mentioning the shadow review seat"
    # Consolidated, not accreted: nested under an existing quota/env section, not a new top-level
    # '##' doc section of its own.
    assert re.search(r"(?m)^### .*shadow", text, re.IGNORECASE), (
        "the shadow paragraph should nest under the existing quota/rate-limit env section as a "
        "'###' subsection, not become a new top-level '##' section"
    )


# ---------------------------------------------------------------------------------------------
# Every path/env key/symbol these additions cite actually exists in the tree
# ---------------------------------------------------------------------------------------------

CITED_PATH_RE = re.compile(r"`([\w./\-]+\.(?:py|sh|md|toml))(?::\d+(?:-\d+)?)?[^`]*`")


def _cited_paths(text):
    return {m.group(1) for m in CITED_PATH_RE.finditer(text)}


def _assert_cited_paths_exist(paths, doc_name):
    for path in paths:
        # Some pre-existing citations in this doc name a tool by its bare filename (e.g.
        # `stage_usage.py`) rather than its full tools/ path — resolve either form.
        candidates = [ROOT / path, ROOT / "tools" / path]
        assert any(c.exists() for c in candidates), (
            f"{doc_name} cites {path!r} but it does not exist in the tree"
        )


def test_every_cited_path_in_the_new_pipeline_md_sections_exists():
    _assert_cited_paths_exist(
        _cited_paths(_shadow_section()) | _cited_paths(_bench_section()), "pipeline.md"
    )


def test_every_cited_path_in_agents_md_conventions_exists():
    _assert_cited_paths_exist(_cited_paths(_conventions_section()), "AGENTS.md")


def test_every_cited_path_in_dispatch_md_exists():
    _assert_cited_paths_exist(_cited_paths(_text(DISPATCH_MD)), "DISPATCH.md")


def test_dev_runner_sh_line_citations_land_on_the_named_symbols():
    """The shadow section cites specific tools/dev-runner.sh line numbers — those lines must
    actually be where the named symbols live, not a stale pointer."""
    section = _shadow_section()
    dev_runner_lines = (ROOT / "tools" / "dev-runner.sh").read_text(encoding="utf-8").splitlines()

    for match in re.finditer(r"tools/dev-runner\.sh:(\d+)(?:-(\d+))?", section):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        assert 1 <= start <= end <= len(dev_runner_lines), (
            f"cited tools/dev-runner.sh:{start}-{end} is out of range "
            f"(file has {len(dev_runner_lines)} lines)"
        )


def test_shadow_env_keys_actually_declared_in_dev_runner_sh():
    src = (ROOT / "tools" / "dev-runner.sh").read_text(encoding="utf-8")
    assert "YR_SHADOW_MODEL" in src, "tools/dev-runner.sh no longer declares YR_SHADOW_MODEL"
    assert "YR_SHADOW_BASE_URL" in src, "tools/dev-runner.sh no longer declares YR_SHADOW_BASE_URL"


def test_cited_shadow_symbols_exist_in_their_named_files():
    dev_runner_src = (ROOT / "tools" / "dev-runner.sh").read_text(encoding="utf-8")
    verdict_diff_src = (ROOT / "tools" / "verdict_diff.py").read_text(encoding="utf-8")

    for symbol in ["shadow_review_round", "shadow_verdict_token", "verdict_line"]:
        assert re.search(rf"\b{re.escape(symbol)}\s*\(\)", dev_runner_src), (
            f"cited symbol {symbol!r} not found defined in tools/dev-runner.sh"
        )
    for symbol in ["render_comment", "build_records"]:
        assert re.search(rf"def {re.escape(symbol)}\(", verdict_diff_src), (
            f"cited symbol {symbol!r} not found defined in tools/verdict_diff.py"
        )


def test_cited_bench_symbols_exist_in_their_named_files():
    corpus_src = (ROOT / "tools" / "bench_corpus.py").read_text(encoding="utf-8")
    replay_src = (ROOT / "tools" / "bench_replay.py").read_text(encoding="utf-8")
    report_src = (ROOT / "tools" / "bench_report.py").read_text(encoding="utf-8")

    assert re.search(r'add_parser\(\s*["\']extract["\']', corpus_src) or "extract" in corpus_src, (
        "tools/bench_corpus.py no longer exposes an 'extract' entry point"
    )
    for symbol in ["grade", "run_candidate"]:
        assert re.search(rf"def {re.escape(symbol)}\(", replay_src), (
            f"cited symbol {symbol!r} not found defined in tools/bench_replay.py"
        )
    assert re.search(r"def load_grading_caveat\(", report_src), (
        "cited symbol load_grading_caveat not found defined in tools/bench_report.py"
    )
    assert re.search(r'add_parser\(\s*["\']report["\']', report_src), (
        "tools/bench_report.py no longer exposes a 'report' entry point"
    )
    assert re.search(r'add_parser\(\s*["\']sweep-diffs["\']', report_src), (
        "tools/bench_report.py no longer exposes a 'sweep-diffs' entry point"
    )


def test_bench_corpus_readme_still_carries_the_grading_caveat_heading():
    readme = ROOT / "bench" / "corpus" / "README.md"
    assert readme.exists(), "bench/corpus/README.md (the caveat's cited home) is missing"
    assert "## Grading caveat" in _text(readme), (
        "bench/corpus/README.md no longer carries the '## Grading caveat' section pipeline.md "
        "and AGENTS.md cite"
    )
