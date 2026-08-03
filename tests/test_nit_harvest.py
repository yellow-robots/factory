"""Acceptance tests for tools/nit_harvest.py — the census's nit-harvest arm (issue #362, slice P5 of
epic #357).

Derived from the acceptance CRITERIA (the spec), never from nit_harvest.py's own internals:

  * WHEN a finding carries no line-anchored record, the arm parses it from prose, marks the row
    heuristically sourced, and NEVER fails the build.
  * The arm ranks harvested nits by recurrence across independent reviews (a path named by findings in
    two or more separate PRs, still resolving in the tree), and treats a stored line number as
    provenance only — never as an actionable pointer.

And the deliverable's own spec text: two per-row-labelled sources (`record` = a column-0 `YR-NIT:` line,
`heuristic` = the prose parser); a `YR-NIT:` string that is indented or blockquoted is NOT matched (the
shadow-transcript guard); the arm never touches the network or `tests/harness/`.

Every test runs over INJECTED fixture comments (the `issues/comments` array shape) and a controlled
tree root built under tmp_path — no network, no `gh` fake, nothing under `tests/harness/`. Assertions
ride the public arm entrypoints `harvest(comments, tree_root=...)` (which returns both
arms — `by_path`, `by_symbol` and `counts` — so these path-arm assertions read `["by_path"]`) and the `main` CLI (`--comments-file`
/ `--tree-root`), so they track the contract rather than any helper's name.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import nit_harvest  # noqa: E402


# --- fixtures --------------------------------------------------------------------------------------

def _tree(root, *relpaths):
    """Create each repo-relative path under `root` as a real file so it resolves in the tree, and return
    `root`. A path NOT passed here does not resolve, so the arm must drop any cluster keyed on it."""
    for rel in relpaths:
        p = pathlib.Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    return root


def _comment(pr, body):
    """An injected `issues/comments`-shaped dict carrying an explicit PR number and a body."""
    return {"pr": pr, "body": body}


def _record_line(path, *, tag="nit", line=None, sentence="a finding"):
    """A well-formed column-0 YR-NIT record line, per the grammar in the module docstring:
    `YR-NIT: tag=<blocker|nit> path=<repo-relative path> [line=<n>] — <one sentence>`."""
    line_part = f" line={line}" if line is not None else ""
    return f"YR-NIT: tag={tag} path={path}{line_part} — {sentence}"


def _cluster_by_path(clusters):
    return {c["path"]: c for c in clusters}


# --- source labelling: a record row and a heuristic row are both labelled -------------------------

def test_record_sourced_row_is_labelled_record(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(11, _record_line("tools/dupe.py")),
        _comment(22, _record_line("tools/dupe.py")),
    ]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    by_path = _cluster_by_path(clusters)
    assert "tools/dupe.py" in by_path
    sources = {f["source"] for f in by_path["tools/dupe.py"]["findings"]}
    assert sources == {"record"}


def test_heuristic_sourced_row_is_labelled_heuristic(tmp_path):
    """A finding carrying NO column-0 record degrades to the prose parser and is marked heuristic."""
    tree = _tree(tmp_path, "tools/dupe.py")
    prose = "This overlaps the logic already in tools/dupe.py and should be merged."
    comments = [_comment(11, prose), _comment(22, prose)]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    by_path = _cluster_by_path(clusters)
    assert "tools/dupe.py" in by_path
    sources = {f["source"] for f in by_path["tools/dupe.py"]["findings"]}
    assert sources == {"heuristic"}


def test_record_and_heuristic_rows_coexist_each_labelled(tmp_path):
    tree = _tree(tmp_path, "tools/rec.py", "tools/heu.py")
    comments = [
        _comment(1, _record_line("tools/rec.py")),
        _comment(2, _record_line("tools/rec.py")),
        _comment(1, "duplicates tools/heu.py, please consolidate"),
        _comment(2, "again, tools/heu.py overlaps here"),
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert {f["source"] for f in by_path["tools/rec.py"]["findings"]} == {"record"}
    assert {f["source"] for f in by_path["tools/heu.py"]["findings"]} == {"heuristic"}


# --- recurrence across independent reviews: one PR is not a cluster, two are -----------------------

def test_finding_named_in_one_pr_is_not_a_cluster(tmp_path):
    tree = _tree(tmp_path, "tools/only.py")
    comments = [_comment(7, _record_line("tools/only.py"))]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    assert "tools/only.py" not in _cluster_by_path(clusters)


def test_finding_named_in_two_prs_is_a_cluster(tmp_path):
    tree = _tree(tmp_path, "tools/twice.py")
    comments = [
        _comment(7, _record_line("tools/twice.py")),
        _comment(8, _record_line("tools/twice.py")),
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert "tools/twice.py" in by_path
    cluster = by_path["tools/twice.py"]
    assert cluster["recurrence"] == 2
    assert sorted(cluster["prs"]) == [7, 8]


def test_two_comments_in_the_same_pr_do_not_make_a_cluster(tmp_path):
    """Recurrence counts DISTINCT PRs — two comments on one PR is a single independent review."""
    tree = _tree(tmp_path, "tools/same.py")
    comments = [
        _comment(5, _record_line("tools/same.py", sentence="first mention")),
        _comment(5, _record_line("tools/same.py", sentence="second mention")),
    ]
    assert "tools/same.py" not in _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])

    # A genuinely independent second review promotes it to a cluster.
    comments.append(_comment(6, _record_line("tools/same.py")))
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert by_path["tools/same.py"]["recurrence"] == 2


def test_clusters_ranked_by_recurrence_descending(tmp_path):
    tree = _tree(tmp_path, "tools/hot.py", "tools/warm.py")
    comments = [
        _comment(1, _record_line("tools/hot.py")),
        _comment(2, _record_line("tools/hot.py")),
        _comment(3, _record_line("tools/hot.py")),
        _comment(1, _record_line("tools/warm.py")),
        _comment(2, _record_line("tools/warm.py")),
    ]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    paths = [c["path"] for c in clusters]
    assert paths.index("tools/hot.py") < paths.index("tools/warm.py")
    by_path = _cluster_by_path(clusters)
    assert by_path["tools/hot.py"]["recurrence"] == 3
    assert by_path["tools/warm.py"]["recurrence"] == 2


# --- tree resolution: a symbol no longer resolving is dropped -------------------------------------

def test_path_that_no_longer_resolves_is_dropped(tmp_path):
    tree = _tree(tmp_path)  # empty tree — nothing resolves
    comments = [
        _comment(1, _record_line("tools/gone.py")),
        _comment(2, _record_line("tools/gone.py")),
    ]
    assert nit_harvest.harvest(comments, tree_root=tree)["by_path"] == []


def test_only_resolving_paths_survive(tmp_path):
    tree = _tree(tmp_path, "tools/live.py")  # gone.py absent
    comments = [
        _comment(1, _record_line("tools/live.py")),
        _comment(2, _record_line("tools/live.py")),
        _comment(1, _record_line("tools/gone.py")),
        _comment(2, _record_line("tools/gone.py")),
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert "tools/live.py" in by_path
    assert "tools/gone.py" not in by_path


# --- the absent-record path never fails the build -------------------------------------------------

def test_absent_record_never_raises(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, "free prose that mentions tools/dupe.py without any record"),
        _comment(2, ""),                       # empty body
        {"pr": 3, "body": None},               # null body
        {"body": "shapeless — no pr/issue_url"},  # no PR number resolvable
        {"issue_url": "https://api.github.com/repos/o/n/issues/4", "body": "text"},
    ]
    # The whole point of the criterion: this degrades precision, it does not raise.
    result = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    assert isinstance(result, list)


def test_cli_over_prose_only_trail_never_fails_and_exits_zero(tmp_path, capsys):
    """The absent-record path must not fail a build: the CLI exits 0 and prints valid JSON even when
    every finding is prose-sourced."""
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, "duplicates tools/dupe.py"),
        _comment(2, "tools/dupe.py again"),
    ]
    cfile = tmp_path / "comments.json"
    cfile.write_text(json.dumps(comments))
    rc = nit_harvest.main(["--comments-file", str(cfile), "--tree-root", str(tree)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert _cluster_by_path(out["by_path"])["tools/dupe.py"]["recurrence"] == 2
    assert out["counts"]["records"] == 0 and out["counts"]["heuristic"] > 0


# --- a stored line number is provenance only, never an actionable pointer -------------------------

def test_stored_line_is_carried_as_provenance(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, _record_line("tools/dupe.py", line=12)),
        _comment(2, _record_line("tools/dupe.py", line=None)),
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    lines = {f["line"] for f in by_path["tools/dupe.py"]["findings"]}
    assert 12 in lines  # the record's line survives on the row as provenance


def test_line_number_is_never_used_to_locate(tmp_path):
    """A record whose line points past the end of the (one-line) file still resolves — resolution keys
    on the path alone, never the line. If the line were used to locate, this would drop."""
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, _record_line("tools/dupe.py", line=99999)),
        _comment(2, _record_line("tools/dupe.py", line=99999)),
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert "tools/dupe.py" in by_path
    assert by_path["tools/dupe.py"]["recurrence"] == 2


def test_differing_line_numbers_do_not_split_a_cluster(tmp_path):
    """Two reviews naming the same path at different lines are ONE cluster — clustering keys on the path,
    never on the provenance line."""
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, _record_line("tools/dupe.py", line=3)),
        _comment(2, _record_line("tools/dupe.py", line=800)),
    ]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    dupe = [c for c in clusters if c["path"] == "tools/dupe.py"]
    assert len(dupe) == 1
    assert dupe[0]["recurrence"] == 2


# --- the column-0 anchor: an indented or blockquoted YR-NIT is NOT matched ------------------------

def test_indented_and_blockquoted_yr_nit_are_not_matched_as_records(tmp_path):
    """The shadow-transcript guard: a `YR-NIT:` line that is indented or blockquoted (behind `> `) is
    not a record. Each comment carries a genuine column-0 record for `anchor.py`, so the prose branch
    never runs — the ONLY reason `indented.py` / `quoted.py` are absent is that the off-column lines
    were not matched. All three files resolve in the tree, so a match would have clustered them."""
    tree = _tree(tmp_path, "tools/anchor.py", "tools/indented.py", "tools/quoted.py")
    body = "\n".join([
        _record_line("tools/anchor.py"),
        "    " + _record_line("tools/indented.py"),   # indented — not column 0
        "> " + _record_line("tools/quoted.py"),        # blockquoted transcript
    ])
    comments = [_comment(1, body), _comment(2, body)]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert "tools/anchor.py" in by_path
    assert "tools/indented.py" not in by_path
    assert "tools/quoted.py" not in by_path


def test_indented_yr_nit_alone_yields_no_record_row(tmp_path):
    tree = _tree(tmp_path, "tools/indented.py")
    body = "  " + _record_line("tools/indented.py")
    comments = [_comment(1, body), _comment(2, body)]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    for c in clusters:
        for f in c["findings"]:
            assert f["source"] != "record"


# --- the record grammar's fields -----------------------------------------------------------------

def test_record_tag_is_carried(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, _record_line("tools/dupe.py", tag="blocker")),
        _comment(2, _record_line("tools/dupe.py", tag="blocker")),
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert {f["tag"] for f in by_path["tools/dupe.py"]["findings"]} == {"blocker"}


# --- the injected read shape: issue_url tail resolves a PR number ---------------------------------

def test_issue_url_shape_resolves_pr_number(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        {"issue_url": "https://api.github.com/repos/o/n/issues/40", "body": _record_line("tools/dupe.py")},
        {"issue_url": "https://api.github.com/repos/o/n/issues/41", "body": _record_line("tools/dupe.py")},
    ]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert by_path["tools/dupe.py"]["recurrence"] == 2
    assert sorted(by_path["tools/dupe.py"]["prs"]) == [40, 41]


def test_cli_requires_a_source(capsys):
    """No --repo and no --comments-file is an argparse error (exit 2), never a network reach."""
    with pytest.raises(SystemExit):
        nit_harvest.main(["--tree-root", "."])


# --- the arm's output lands in the census template and is described in the round reference ---------

def test_debt_census_template_names_the_arm():
    text = (ROOT / "templates" / "debt-census.md").read_text(encoding="utf-8")
    section = text.split("## Duplication / consolidation sets", 1)
    assert len(section) == 2, "debt-census.md is missing the Duplication / consolidation sets section"
    body = section[1]
    assert "tools/nit_harvest.py" in body
    assert "record" in body and "heuristic" in body
    assert "provenance" in body.lower()


def test_debt_rounds_reference_describes_the_arm():
    text = (ROOT / "skills" / "factory" / "references" / "debt-rounds.md").read_text(encoding="utf-8")
    assert "tools/nit_harvest.py" in text
    assert "recurrence" in text.lower()
    assert "heuristic" in text.lower() and "record" in text.lower()


def test_agents_repo_map_and_readme_name_the_tool():
    assert "tools/nit_harvest.py" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "nit_harvest" in (ROOT / "README.md").read_text(encoding="utf-8")


# --- the symbol arm (the half the spec justified the arm by, missing from the first ship) ---------

def test_symbol_clustering_finds_a_contract_named_across_two_prs(tmp_path):
    """A contract's consumers share a NAME, not a file — the signal path clustering cannot see.

    it-27 § 6 rests the arm's whole case on a symbol result (`read_ci_timeout` [264, 280],
    `read_server_ci` [280, 282], `MERGE_CI_TIMEOUT` [264, 282] — "one chain, one shape, found without
    being told what to look for"). The first ship clustered on the path alone, so that demonstration
    was not reproducible: the criterion's letter was met and the argument behind it was not.
    """
    tree = _tree(tmp_path, "tools/a.py", "tools/b.py")
    (tree / "tools" / "a.py").write_text("def read_ci_timeout():\n    pass\n", encoding="utf-8")
    comments = [
        _comment(264, "the `read_ci_timeout` reader is duplicated in tools/a.py"),
        _comment(280, "follows the `read_ci_timeout` precedent in tools/b.py"),
    ]
    out = nit_harvest.harvest(comments, tree_root=tree)
    by_symbol = {c["symbol"]: c for c in out["by_symbol"]}
    assert "read_ci_timeout" in by_symbol, (
        "a symbol named by findings in two separate PRs did not cluster — the arm cannot report that "
        "a contract has acquired consumers, which is the only thing it was justified by"
    )
    assert by_symbol["read_ci_timeout"]["recurrence"] == 2
    assert by_symbol["read_ci_timeout"]["prs"] == [264, 280]


def test_a_symbol_named_in_one_pr_only_is_not_a_cluster(tmp_path):
    tree = _tree(tmp_path, "tools/a.py")
    (tree / "tools" / "a.py").write_text("def read_ci_timeout():\n    pass\n", encoding="utf-8")
    comments = [_comment(1, "the `read_ci_timeout` reader in tools/a.py")]
    assert nit_harvest.harvest(comments, tree_root=tree)["by_symbol"] == []


def test_a_symbol_no_longer_in_the_tree_is_dropped(tmp_path):
    """The symbol arm's analogue of path resolution: a name two reviews discussed and that is now
    gone is a finding about code that no longer exists."""
    tree = _tree(tmp_path, "tools/a.py")
    comments = [
        _comment(1, "the `long_since_deleted_helper` is cloned"),
        _comment(2, "`long_since_deleted_helper` again"),
    ]
    assert nit_harvest.harvest(comments, tree_root=tree)["by_symbol"] == []


def test_english_words_in_backticks_are_not_symbols():
    """Backticks wrap code AND ordinary words a reviewer is quoting. Both resolve as identifiers in a
    tree this size, so tree-resolution alone cannot separate them — the first symbol run surfaced six
    English words inside its top fourteen."""
    for word in ("active", "main", "log", "superseded", "None", "draft"):
        assert not nit_harvest.is_compound_identifier(word), f"{word!r} clustered as a code symbol"
    for symbol in ("read_ci_timeout", "MERGE_CI_TIMEOUT", "STAGE_CHARTER", "runLint", "_json_field"):
        assert nit_harvest.is_compound_identifier(symbol), f"{symbol!r} was rejected as a symbol"


# --- the report-scaffolding filter ----------------------------------------------------------------

def test_review_report_scaffolding_is_not_harvested_as_a_finding():
    """A report's own structure names files without reporting a defect in them, and it dominated the
    first live run's yield. The failure direction is deliberately "too many rows", never a lost
    finding, so the vocabulary is closed and anything unmatched stays prose."""
    for line in (
        "**`tools/dev-runner.sh` line 26**",
        "## Findings",
        "- **Scope integrity** ✓ — only the three in-scope files changed",
        "- No changes to `docs/rfcs/`. ✅",
        "**AC3 — scope.** Outside `tests/`, the only file touched is `.github/workflows/ci.yml`",
        "**Verdict:** approve",
    ):
        assert nit_harvest.is_report_scaffolding(line), f"scaffolding not filtered: {line!r}"

    for line in (
        "`tools/merge_shadow.py` uses a bare substring where the others anchor at column 0",
        "- the manifest reader in `tools/dev-runner.sh` is cloned again here",
        "this duplicates the helper in tools/textutil.py",
    ):
        assert not nit_harvest.is_report_scaffolding(line), f"real finding filtered out: {line!r}"


def test_a_bold_heading_is_not_stripped_into_a_finding():
    """Regression: the filter's first version stripped list bullets with `.lstrip('-*+ ')`, which ate
    the `**` of a bold heading, so every heading then failed the bold-only test and was harvested."""
    assert nit_harvest.is_report_scaffolding("**`tools/dev-runner.sh` line 26**")
    assert nit_harvest.is_report_scaffolding("* **Summary**")


def test_scaffolding_lines_do_not_reach_the_clusters(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    comments = [
        _comment(1, "**Scope.** Only `tools/dupe.py` changed ✓"),
        _comment(2, "**Scope.** Only `tools/dupe.py` changed ✓"),
    ]
    assert nit_harvest.harvest(comments, tree_root=tree)["by_path"] == []


# --- a decorated `path=` value must not vanish ----------------------------------------------------

def test_a_backticked_path_value_still_resolves(tmp_path):
    """A record the reviewer got right in substance must not be lost to punctuation: it parses, then
    fails `.exists()`, and is dropped with nothing reporting it."""
    tree = _tree(tmp_path, "tools/dupe.py")
    body = "YR-NIT: tag=nit path=`tools/dupe.py` — a second reader"
    comments = [_comment(1, body), _comment(2, body)]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert "tools/dupe.py" in by_path


def test_a_file_line_suffix_on_the_path_is_lifted_into_provenance(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    body = "YR-NIT: tag=nit path=tools/dupe.py:42 — a second reader"
    comments = [_comment(1, body), _comment(2, body)]
    clusters = nit_harvest.harvest(comments, tree_root=tree)["by_path"]
    by_path = _cluster_by_path(clusters)
    assert "tools/dupe.py" in by_path, "a `:NN` suffix dropped an otherwise-valid record"
    assert by_path["tools/dupe.py"]["findings"][0]["line"] == 42, (
        "the suffix was discarded rather than kept as provenance — the record did carry it"
    )


def test_an_explicit_line_field_wins_over_a_path_suffix(tmp_path):
    tree = _tree(tmp_path, "tools/dupe.py")
    body = "YR-NIT: tag=nit path=tools/dupe.py:42 line=7 — a second reader"
    comments = [_comment(1, body), _comment(2, body)]
    by_path = _cluster_by_path(nit_harvest.harvest(comments, tree_root=tree)["by_path"])
    assert by_path["tools/dupe.py"]["findings"][0]["line"] == 7
