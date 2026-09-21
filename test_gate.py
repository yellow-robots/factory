"""The gate's acceptance tests, written from docs/seeds/the-gate.md before the code.

    uv run python -m unittest test_gate -v

Every test builds a small vault and a git repository in a temporary directory, so nothing here
touches the factory's own docs/ or tags. The interface under test is the seed's Goal:
gate.main(argv, root) shaped like builder.main, argv[0] the program name; problems on stdout, one
per line, each starting with the path relative to root; exit 1 when there is any, 0 and silence
when there is none; usage on stderr and exit 2 for a missing or unknown command.
"""

import contextlib
import dataclasses
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gate

IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def fm(**fields) -> str:
    """Frontmatter as the vault writes it: `key: value`, `key:` when the value is empty."""
    return "---\n" + "".join(f"{k}: {v}\n" if str(v) else f"{k}:\n" for k, v in fields.items()) + "---\n"


TEMPLATE_SEED = fm(created='"{{date}}"', type="seed", status="open", summary="", value="", effort="", version="") + "\n## Evidence\n\n## Idea\n"
TEMPLATE_VERSION = fm(type="version") + "\n# v0.0: name\n\nWhat the version is for.\n\n## Changelog\n\n-\n"
BASE = """\
filters:
  and:
    - file.inFolder("seeds")
    - type == "seed"
formulas:
  rank: if(value && effort, (value - if(effort == "S", 0, if(effort == "M", 0.5, 1))).round(1), "")
properties:
  status:
    displayName: Status
  formula.rank:
    displayName: Rank
  created:
    displayName: Born
views:
  - type: table
    name: Pending
    filters:
      or:
        - status == "open"
        - status == "spec"
    order:
      - file.name
      - status
      - formula.rank
      - created
    sort:
      - property: formula.rank
        direction: DESC
      - property: created
        direction: ASC
  - type: table
    name: By version
    groupBy:
      property: version
      direction: DESC
    order:
      - file.name
      - summary
  - type: table
    name: Specs
    filters:
      and:
        - version == this.file.basename
    order:
      - file.name
      - effort
"""
SEED_A = fm(created="2026-09-16", type="seed", status="open", summary="an idea", value=3, effort="S", version="") + (
    "\n## Evidence\n\nRun x, 2026-09-16.\n\n## Idea\n\nDo y, see [[b]].\n"
)
SEED_B = fm(created="2026-09-16", type="seed", status="spec", summary="a spec", value=4, effort="M", version="v0.2") + (
    "\n## Evidence\n\nRun y, 2026-09-16.\n\n## Goal\n\nAdd z so that w.\n"
)
SEED_D = fm(created="2026-09-15", type="seed", status="done", summary="delivered", value=5, effort="S", version="v0.1") + (
    "\n## Evidence\n\nRun z, 2026-09-15.\n\n## Goal\n\nThe first thing.\n"
)
V01 = fm(type="version") + (
    "\n# v0.1: the start\n\nThe first version did the first thing.\n\n"
    "## Changelog\n\n- The first thing, done.\n- The second thing, done.\n\n## Runs\n\nNone kept.\n"
)
V02 = fm(type="version") + (
    "\n# v0.2: the next\n\nThe next version does the next thing.\n\n![[backlog.base#Specs]]\n\n"
    "## Changelog\n\n- The next thing, built.\n"
)
AGENTS = "# repo\n\nOrient yourself.\n"
TEMPLATE_REVIEW = fm(created='"{{date}}"', type="review", runs="", reviewer="") + "\n## Findings\n\n### Title\n\nseverity:\nverified:\njudged:\n"
STAMP = "20260917T000000Z"
WHEEL = "dist/factory-0.2-py3-none-any.whl"
REVIEW = fm(created="2026-09-17", type="review", runs=STAMP, reviewer="a cold session") + (
    "\n## Findings\n\n### The first thing misses an edge\n\nseverity: defect\nverified: yes\njudged: test test_d\n\n"
    "What happens, and how it was reproduced.\n"
)
TEST_GREEN = '''\
import unittest


class RepoTest(unittest.TestCase):
    def test_d(self):
        """seed: d. The first thing holds."""
        self.assertEqual(1, 1)
'''
TEST_GREEN_B = TEST_GREEN + '''
    def test_b(self):
        """seed: b. The next thing holds."""
        self.assertEqual(2, 2)
'''
TEST_RED_B = TEST_GREEN + '''
    def test_b(self):
        """seed: b. The next thing does not hold yet."""
        self.assertEqual(1, 2)
'''


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_repo(base: Path) -> Path:
    """A valid repository: v0.1 tagged with seed d done, v0.2 in flight with seed b at spec."""
    root = base / "repo"
    write(root, "docs/templates/seed.md", TEMPLATE_SEED)
    write(root, "docs/templates/version.md", TEMPLATE_VERSION)
    write(root, "docs/backlog.base", BASE)
    write(root, "docs/seeds/a.md", SEED_A)
    write(root, "docs/seeds/b.md", SEED_B)
    write(root, "docs/seeds/d.md", SEED_D)
    write(root, "docs/versions/v0.1.md", V01)
    write(root, "docs/versions/v0.2.md", V02)
    write(root, "AGENTS.md", AGENTS)
    write(root, "test_repo.py", TEST_GREEN)
    write(root, ".gitignore", "__pycache__/\ndist/\n")  # dist/ ignored, as this repository ignores it
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "one")
    git(root, "tag", "v0.1")
    return root


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = gate.main(["gate.py", *args], root=root)
    return code, out.getvalue(), err.getvalue()


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, IDENTITY))
        self.root = make_repo(Path(self.tmp.name))

    def edit(self, rel: str, text: str) -> None:
        write(self.root, rel, text)

    def commit(self, message: str = "more") -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def check(self) -> tuple[int, str, str]:
        return run(self.root, "check")

    def assert_problem(self, *words: str) -> str:
        code, out, err = self.check()
        self.assertEqual(code, 1, out)
        for word in words:
            self.assertIn(word, out)
        return out


class CheckTest(GateTest):
    """seed: the-gate. check validates docs/ and the repository against it, silently when valid."""

    def test_a_valid_vault_is_silent(self):
        self.assertEqual(self.check(), (0, "", ""))

    def test_every_note_has_frontmatter_whose_type_names_a_template(self):
        self.edit("docs/seeds/a.md", SEED_A.replace("type: seed", "type: idea"))
        self.assert_problem("docs/seeds/a.md", "idea")
        self.edit("docs/seeds/a.md", "# no frontmatter\n")
        self.assert_problem("docs/seeds/a.md")
        self.edit("docs/seeds/a.md", SEED_A)
        self.edit("docs/versions/v0.2.md", V02.replace("type: version", "type: release"))
        self.assert_problem("docs/versions/v0.2.md", "release")

    def test_wikilinks_resolve_to_a_note_by_path_or_name_or_to_a_base(self):
        self.edit("docs/seeds/a.md", SEED_A + "\nSee [[versions/v0.1]], [[v0.1#Changelog]], [[b|the spec]] and ![[backlog.base#Specs]].\n")
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/seeds/a.md", SEED_A + "\nSee [[nowhere]].\n")
        self.assert_problem("docs/seeds/a.md", "nowhere")
        self.edit("docs/seeds/a.md", SEED_A + "\nSee ![[gone.base#View]].\n")
        self.assert_problem("docs/seeds/a.md", "gone.base")

    def test_a_seed_status_is_one_of_five(self):
        self.edit("docs/seeds/a.md", SEED_A.replace("status: open", "status: later"))
        self.assert_problem("docs/seeds/a.md", "later")
        self.edit("docs/seeds/a.md", SEED_A.replace("status: open", "status:"))
        self.assert_problem("docs/seeds/a.md", "status")

    def test_an_open_seed_has_summary_value_in_range_and_effort_in_sizes(self):
        broken = (
            (SEED_A.replace("summary: an idea", "summary:"), "summary"),
            (SEED_A.replace("value: 3", "value: 7"), "value"),
            (SEED_A.replace("value: 3", "value: high"), "value"),
            (SEED_A.replace("effort: S", "effort: XL"), "effort"),
        )
        for text, word in broken:
            self.edit("docs/seeds/a.md", text)
            self.assert_problem("docs/seeds/a.md", word)

    def test_frontmatter_has_no_field_without_a_consumer(self):
        self.edit("docs/seeds/a.md", SEED_A.replace("version:\n", "version:\nowner: me\n"))
        self.assert_problem("docs/seeds/a.md", "owner")
        self.edit("docs/seeds/a.md", SEED_A)
        self.edit("docs/versions/v0.2.md", V02.replace("type: version\n", "type: version\ntag: v0.2\n"))
        self.assert_problem("docs/versions/v0.2.md", "tag")

    def test_a_spec_names_an_existing_version_note_and_has_a_goal(self):
        self.edit("docs/seeds/b.md", SEED_B.replace("version: v0.2", "version: v9.9"))
        self.assert_problem("docs/seeds/b.md", "v9.9")
        self.edit("docs/seeds/b.md", SEED_B.replace("version: v0.2", "version:"))
        self.assert_problem("docs/seeds/b.md", "version")
        self.edit("docs/seeds/b.md", SEED_B.replace("## Goal\n\nAdd z so that w.\n", "## Idea\n\nMaybe z.\n"))
        self.assert_problem("docs/seeds/b.md", "Goal")
        self.edit("docs/seeds/b.md", SEED_B.replace("Add z so that w.\n", ""))
        self.assert_problem("docs/seeds/b.md", "Goal")
        self.edit("docs/seeds/b.md", SEED_B)
        self.assertEqual(self.check(), (0, "", ""))

    def test_the_goal_is_read_as_the_builder_reads_it(self):
        """seed: one-goal-reader. The gate reads ## Goal with the builder's reader, so it reports a
        Goal whose only text is a %% comment, a ## Goal inside a comment block, a heading indented
        four spaces, and a comment left open, and accepts a Goal whose text starts with a
        level-three heading or a fence, as builder.read_seed would."""
        goal = "## Goal\n\nAdd z so that w.\n"
        for body, word in (
            ("## Goal\n\n%%drafted%%\n", "Goal"),
            ("%%\n## Goal\n\nnot yet\n%%\n\n## Idea\n\nMaybe.\n", "Goal"),
            ("    ## Goal\n\nindented\n", "Goal"),
            ("## Goal\n\nAdd z %% and a comment never closed.\n", "comment"),
        ):
            self.edit("docs/seeds/b.md", SEED_B.replace(goal, body))
            self.assert_problem("docs/seeds/b.md", word)
        for body in ("## Goal\n\n### Details\n\nAdd z so that w.\n", "## Goal\n\n```\n## Idea\n```\n\nAdd z.\n"):
            self.edit("docs/seeds/b.md", SEED_B.replace(goal, body))
            self.assertEqual(self.check(), (0, "", ""), body)

    def test_a_building_or_done_seed_is_named_by_a_test_docstring(self):
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.assert_problem("docs/seeds/b.md", "seed: b")
        self.edit("test_repo.py", TEST_GREEN + "\n# seed: b\n")  # a comment is not a docstring
        self.assert_problem("docs/seeds/b.md", "seed: b")
        self.edit("test_repo.py", TEST_GREEN_B)
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("test_repo.py", TEST_GREEN)
        self.assert_problem("docs/seeds/b.md", "seed: b")

    def test_a_version_note_is_named_like_a_tag(self):
        self.edit("docs/versions/gate.md", V02.replace("v0.2: the next", "gate: misnamed"))
        self.assert_problem("docs/versions/gate.md")

    def test_at_most_one_version_note_is_not_a_tag(self):
        self.edit("docs/versions/v0.3.md", V02.replace("v0.2: the next", "v0.3: the one after"))
        self.assert_problem("docs/versions/")
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.edit("test_repo.py", TEST_GREEN_B)
        git(self.root, "tag", "v0.2")  # v0.2 released: v0.3 alone is in flight
        self.assertEqual(self.check(), (0, "", ""))

    def test_a_tagged_version_has_its_seeds_done_or_rejected(self):
        self.edit("docs/seeds/d.md", SEED_D.replace("status: done", "status: building"))
        self.assert_problem("docs/seeds/d.md", "v0.1")
        self.edit("docs/seeds/d.md", SEED_D.replace("status: done", "status: rejected"))
        self.assertEqual(self.check(), (0, "", ""))

    def test_a_rejected_seed_needs_only_the_open_fields(self):
        """rejected is a way out at any stage, not a stage after done: no version, Goal or test."""
        self.edit("docs/seeds/a.md", SEED_A.replace("status: open", "status: rejected") + "\nRejected: no run shows it matters.\n")
        self.assertEqual(self.check(), (0, "", ""))

    def test_a_seed_carries_the_date_it_was_born(self):
        """seed: created-field. created is allowed, required from open on and shaped YYYY-MM-DD; the
        templates stay exempt."""
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/seeds/a.md", SEED_A.replace("created: 2026-09-16\n", ""))
        self.assert_problem("docs/seeds/a.md", "created")
        for bad in ("created: yesterday", "created: 2026-9-16", "created: 16-09-2026", "created:"):
            self.edit("docs/seeds/a.md", SEED_A.replace("created: 2026-09-16", bad))
            self.assert_problem("docs/seeds/a.md", "created")
        self.edit("docs/seeds/a.md", SEED_A.replace("created: 2026-09-16", "created: 2026-09-17"))
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/seeds/a.md", SEED_A.replace("status: open", "status: rejected").replace("created: 2026-09-16\n", ""))
        self.assert_problem("docs/seeds/a.md", "created")

    def test_the_backlog_names_only_fields_of_the_seed_template(self):
        """seed: base-against-the-template. Every property the base names in filters, formulas,
        properties, order, sort and groupBy is a template field; file., formula., this and the
        function names belong to the language and are never reported."""
        self.assertEqual(self.check(), (0, "", ""))
        cases = (
            (BASE.replace("      - status\n", "      - status\n      - owner\n"), "owner"),
            (BASE.replace('    - type == "seed"\n', '    - type == "seed"\n    - priority > 3\n'), "priority"),
            (BASE.replace("if(value && effort,", "if(value && weight,"), "weight"),
            (BASE.replace("      - property: created\n", "      - property: born\n"), "born"),
            (BASE.replace("  created:\n    displayName: Born\n", "  stale:\n    displayName: Stale\n"), "stale"),
            (BASE.replace("      property: version\n", "      property: release\n"), "release"),
        )
        for bad, word in cases:
            self.assertNotEqual(bad, BASE, word)
            self.edit("docs/backlog.base", bad)
            out = self.assert_problem("docs/backlog.base", word)
            self.assertNotIn("file.name", out)
            self.assertNotIn("basename", out)
        self.edit("docs/backlog.base", BASE)
        self.assertEqual(self.check(), (0, "", ""))

    def test_a_record_in_the_project_is_not_the_gates(self):
        """seed: compress-the-wire. seed: records-outside-the-project. A record is the factory's and
        is kept in its store, where its wire is compressed before it is committed; the gate reads
        no `runs/` in the project, so a wire tracked uncompressed there, as a record once was, is
        no problem of the gate's."""
        self.edit("runs/20260916T000000Z/wire.jsonl", '{"dir": "request"}\n')
        self.edit("runs/20260916T000000Z/numbers.json", "{}\n")
        self.commit("a record in the project, its wire uncompressed")
        self.assertEqual(self.check(), (0, "", ""))

    def test_a_note_git_ignores_is_no_note(self):
        """seed: the-vault-as-git-tracks-it. The gate reads the vault as git tracks it: a path git
        ignores is no note, so a scratchpad inside the vault refuses nothing, neither for its
        frontmatter nor for a wikilink it holds, and a wikilink of a note's that names an ignored
        path resolves to nothing and is a problem. A note git tracks is checked as before, and so
        is one nobody has committed yet, which git does not ignore."""
        self.edit(".gitignore", "__pycache__/\ndocs/scratchpad/\n")
        self.edit("docs/scratchpad/notes.md", "no frontmatter at all, and [[a link to nowhere]].\n")
        self.commit("the owner's scratchpad, which git ignores")
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertEqual(self.check(), (0, "", ""))

        self.edit("docs/seeds/a.md", SEED_A.replace("see [[b]]", "see [[b]] and [[scratchpad/notes]]"))
        self.assert_problem("docs/seeds/a.md", "scratchpad/notes")
        self.edit("docs/seeds/a.md", SEED_A)
        self.assertEqual(self.check(), (0, "", ""))

        git(self.root, "add", "-f", "docs/scratchpad/notes.md")
        self.commit("the scratchpad note tracked after all")
        self.assert_problem("docs/scratchpad/notes.md")

        git(self.root, "rm", "-q", "--cached", "docs/scratchpad/notes.md")
        self.commit("ignored again")
        self.assertEqual(self.check(), (0, "", ""))

        self.edit("docs/seeds/c.md", "no frontmatter and nobody has committed it\n")
        self.assert_problem("docs/seeds/c.md")  # untracked is not ignored

    def test_a_vault_that_is_not_a_git_checkout_is_read_whole(self):
        """seed: the-vault-as-git-tracks-it. Asking git what it tracks is how the vault is read where
        git can answer: a directory that is no git checkout is read whole as it was, so the notes
        of a copy of the vault are checked and nothing is passed over for want of git."""
        copy = Path(self.tmp.name) / "copy"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        write(copy, "docs/scratchpad/notes.md", "no frontmatter at all\n")
        code, out, err = run(copy, "check")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/scratchpad/notes.md", out)

    def test_a_vault_that_is_not_a_git_checkout_names_git_once_for_the_tags_and_once_for_the_builds(self):
        """seed: the-gate-in-three. From the review: a git that failed answered with nothing, so a
        tree that is no checkout got one false problem per version note -- twenty on this
        repository's own vault -- beside the one true line about the builds. A failure is one
        problem naming its cause, and what depends on the answer is not checked as if the answer
        were empty."""
        copy = Path(self.tmp.name) / "copy"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        code, out, _ = run(copy, "check")
        self.assertEqual(code, 1, out)
        versions = [line for line in out.splitlines() if line.startswith("docs/versions/")]
        self.assertEqual(len(versions), 2, out)
        self.assertTrue(any("tag" in line and "failed" in line for line in versions), out)
        self.assertTrue(any("rev-list" in line and "failed" in line for line in versions), out)
        self.assertNotIn("may not be a tag", out)

    def test_a_test_file_that_does_not_parse_is_one_problem_and_no_seed_is_unnamed_for_it(self):
        """seed: the-gate-in-three. From the review: a test file with a syntax error was skipped in
        silence, so every building or done seed was then named by no test and every `judged:
        test` was unfound, with no line saying why."""
        self.edit("test_bad.py", "def (\n")
        self.commit("a test file that does not parse")
        out = self.assert_problem("test_bad.py", "does not parse")
        self.assertNotIn("docs/seeds/d.md", out)  # d is named by test_d in test_repo.py, which parses

    def test_a_note_that_cannot_be_read_is_one_problem_and_not_an_empty_note(self):
        """seed: the-gate-in-three. From the review: an unreadable note read as "" and was reported
        as having no frontmatter."""
        note = self.root / "docs" / "seeds" / "a.md"
        note.chmod(0)
        self.addCleanup(note.chmod, 0o644)
        out = self.assert_problem("docs/seeds/a.md", "cannot be read")
        self.assertNotIn("no frontmatter", out)

    def test_a_problem_is_one_line_starting_with_its_path_whatever_git_said(self):
        """seed: the-gate-in-three. From the review: git's words carry newlines and advice, and a
        failure line carried them whole -- four lines for two problems on a tree that is no
        checkout. One line per problem, starting with its path, git's words collapsed to one."""
        copy = Path(self.tmp.name) / "copy"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        code, out, _ = run(copy, "check")
        self.assertEqual(code, 1, out)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, out)
        for line in lines:
            self.assertTrue(line.startswith("docs/versions/: git "), line)
            self.assertIn("failed: fatal: not a git repository", line)

    def test_a_template_without_frontmatter_is_its_own_problem_and_an_unreadable_one_hides_nothing(self):
        """seed: the-gate-in-three. From the review: a template with no frontmatter was called
        unreadable, and an unreadable template silenced every check of every note of its kind --
        status, value, effort, Goal, findings -- none of which derives from the template."""
        self.edit("docs/templates/seed.md", "# a template with no frontmatter\n")
        self.commit("a template without frontmatter")
        out = self.assert_problem("docs/templates/seed.md", "no frontmatter")
        self.assertNotIn("cannot be read", out)
        self.edit("docs/templates/seed.md", TEMPLATE_SEED)
        self.edit("docs/seeds/a.md", SEED_A.replace("status: open", "status: later"))
        self.commit("a status that is not one")
        template = self.root / "docs" / "templates" / "seed.md"
        template.chmod(0)
        self.addCleanup(template.chmod, 0o644)
        out = self.assert_problem("docs/templates/seed.md", "cannot be read")
        self.assertIn("docs/seeds/a.md: status later", out)

    def test_a_test_file_that_does_not_parse_is_one_line_and_the_other_files_still_count(self):
        """seed: the-gate-in-three. From the review: the line repeated the file's name and leaked
        an absolute path, and one broken file dropped every test-derived check, so a seed named by
        no test went unreported for as long as any unrelated test file was broken."""
        self.edit("test_bad.py", "def (\n")
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("a broken test file and a building seed no test names")
        out = self.assert_problem("test_bad.py: does not parse")
        self.assertNotIn("test_bad.py: test_bad.py", out)
        self.assertNotIn(str(self.root), out)
        self.assertIn("docs/seeds/b.md: no test names it", out)
        self.assertNotIn("docs/seeds/d.md", out)

    def test_notes_are_read_in_path_order_and_once(self):
        """seed: the-gate-in-three. From the review: notes were sorted as strings, so a directory
        with `-` in its name came before its neighbour where it used to come after; and every note
        was read twice per check, once for its fields and once for its links."""
        self.edit("docs/x/y.md", SEED_A.replace("value: 3", "value: 9"))
        self.edit("docs/x-y/z.md", SEED_A.replace("value: 3", "value: 9"))
        self.commit("two")
        reads: list[Path] = []
        real = Path.read_text

        def counting(path, *args, **kwargs):
            reads.append(path)
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", counting):
            code, out, _ = self.check()
        self.assertEqual(code, 1, out)
        lines = out.splitlines()
        self.assertLess(lines.index("docs/x/y.md: value 9 is not in 1 to 5"), lines.index("docs/x-y/z.md: value 9 is not in 1 to 5"))
        notes = [str(path) for path in reads if str(path).endswith(".md")]
        twice = sorted({path for path in notes if notes.count(path) > 1})
        self.assertEqual(twice, [], "read twice: " + ", ".join(twice))

    def test_a_vault_git_answers_about_somebody_else_is_read_whole(self):
        """seed: the-vault-as-git-tracks-it. From the review: a copy of the vault inside a repository
        that ignores it had git answer about that repository, which tracks nothing of the copy, so
        every note was passed over and check went silent on a vault with no frontmatter anywhere.
        git's answer is taken only when it is about this directory, its own top level, as the
        builder asks of a checkout; otherwise the vault is read whole."""
        outer = Path(self.tmp.name) / "outer"
        outer.mkdir()
        git(outer, "init", "-q")
        (outer / ".gitignore").write_text("copy/\n")
        (outer / "seed.txt").write_text("x\n")
        git(outer, "add", "-A")
        git(outer, "commit", "-q", "-m", "one")
        copy = outer / "copy"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        write(copy, "docs/scratchpad/notes.md", "no frontmatter at all\n")
        listed = git(copy, "ls-files", "--cached", "--others", "--exclude-standard")
        self.assertEqual(listed.split(), [])  # git answers, about the enclosing repository
        code, out, err = run(copy, "check")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/scratchpad/notes.md", out)

    def test_the_vault_is_asked_of_git_once(self):
        """seed: the-vault-as-git-tracks-it. From the review: what git ignores is asked once for the
        whole vault, not once a note, which a check of this repository's own vault would pay for
        fifty times over; a release asks once too."""
        calls = []
        real = subprocess.run

        def counting(argv, *args, **kwargs):
            if isinstance(argv, (list, tuple)) and "ls-files" in argv:
                calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", counting):
            self.assertEqual(self.check(), (0, "", ""))
        self.assertEqual(len(calls), 1, calls)

    def test_an_ignored_base_a_template_and_a_version_note_are_no_part_of_the_vault(self):
        """seed: the-vault-as-git-tracks-it. A path git ignores is no note wherever the gate reads
        one: the base it checks the properties of, a template a note's type names, and the version
        note a spec must have."""
        self.edit(".gitignore", "__pycache__/\ndocs/templates/\n")
        self.commit("the templates ignored")
        self.assert_problem("docs/seeds/a.md", "template")
        self.edit(".gitignore", "__pycache__/\ndocs/backlog.base\n")
        self.commit("the base ignored")
        out = self.assert_problem("backlog.base")  # a wikilink to a base nobody tracks
        self.assertNotIn("is not a field", out)
        self.edit(".gitignore", "__pycache__/\ndocs/versions/v0.2.md\n")
        self.commit("the version note ignored")
        self.assert_problem("docs/seeds/b.md", "v0.2")

    def test_the_backlog_check_reads_what_obsidian_writes(self):
        """seed: base-against-the-template. From the review: a nested filter group names no
        property but its items do, note. is a prefix of a property, a hyphen in an expression is
        the minus, a regex literal and an inline comment name nothing, summaries name properties,
        and a missing seed template is one problem elsewhere, not one per property."""
        nested = BASE.replace(
            '      or:\n        - status == "open"\n        - status == "spec"\n',
            '      and:\n        - or:\n            - status == "open"\n            - status == "spec"\n'
            '        - not:\n            - version == ""\n        - not: status == "rejected"\n',
        )
        self.assertNotEqual(nested, BASE)
        self.edit("docs/backlog.base", nested)
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/backlog.base", nested.replace('- status == "spec"', '- stauts == "spec"'))
        out = self.assert_problem("docs/backlog.base", "stauts")
        for keyword in (": and ", ": or ", ": not "):
            self.assertNotIn(keyword, out)
        self.edit("docs/backlog.base", BASE.replace('    - type == "seed"\n', '    - note.type == "seed"\n    - note.stauts == "open"\n'))
        out = self.assert_problem("docs/backlog.base", "stauts")
        self.assertNotIn(": note ", out)
        self.assertNotIn(": type ", out)
        self.edit("docs/backlog.base", BASE.replace("(value - if(effort", "(value-if(effort"))
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/backlog.base", BASE.replace("(value - if(effort", "(valeu-if(effort"))
        self.assert_problem("docs/backlog.base", "valeu")
        self.edit("docs/backlog.base", BASE.replace('    - type == "seed"\n', '    - type == "seed" # only seeds\n    - /^\\d{4}-\\d{2}-\\d{2}$/.matches(created)\n'))
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/backlog.base", BASE + "    summaries:\n      valeu: Sum\n")
        self.assert_problem("docs/backlog.base", "valeu")
        self.edit("docs/backlog.base", BASE + "    summaries:\n      value: Sum\n")
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("docs/backlog.base", BASE)
        (self.root / "docs" / "templates" / "seed.md").unlink()
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertNotIn("docs/backlog.base", out)

    def test_templates_are_exempt(self):
        self.edit("docs/templates/seed.md", TEMPLATE_SEED.replace("type: seed", "type: whatever"))
        self.assertEqual(self.check(), (0, "", ""))

    def test_check_reports_a_build_git_cannot_list_before_main_moves(self):
        """seed: built-by-trailer. From the reviews: check reads the builds since the highest tag as
        release does and reports the same problems, under the note of the version in flight, or
        under `docs/versions/` when no version is in flight, and reads every commit when there is
        no tag, so a build git cannot list is seen in the version's worktree, where it can still be
        amended."""
        self.edit("feature.py", "X = 1\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "feature", "-m", f"Built-By: factory at 1234567, run {STAMP}",
            "-m", "Co-Authored-By: t <t@t>")  # fmt: skip
        short = git(self.root, "rev-parse", "HEAD").strip()[:7]
        out = self.assert_problem("docs/versions/v0.2.md:", short)
        self.assertTrue(any(
            line.startswith("docs/versions/v0.2.md:") and short in line and "as a trailer" in line
            for line in out.splitlines()
        ), out)  # fmt: skip
        git(self.root, "commit", "-q", "--amend", "-m", "feature",
            "-m", f"Built-By: factory at 1234567, run {STAMP}\nCo-Authored-By: t <t@t>")  # fmt: skip
        self.assertFalse((self.root / "runs").exists())  # the record is in the factory's store
        self.assertEqual(self.check(), (0, "", ""))

        self.edit("other.py", "Y = 1\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "other", "-m", "Built-By: factory at 7654321",
            "-m", "Co-Authored-By: t <t@t>")  # fmt: skip
        other = git(self.root, "rev-parse", "HEAD").strip()[:7]
        git(self.root, "tag", "v0.2", "HEAD^")  # no version in flight, the build after the highest tag
        out = self.assert_problem("docs/versions/:", other)
        self.assertTrue(any(line.startswith("docs/versions/:") and other in line and "as a trailer" in line
                            for line in out.splitlines()), out)  # fmt: skip
        git(self.root, "tag", "-d", "v0.1", "v0.2")  # no tag: every commit is read
        out = self.assert_problem("docs/versions/:", other)
        self.assertTrue(any(line.startswith("docs/versions/:") and other in line and "names no run" in line
                            for line in out.splitlines()), out)  # fmt: skip


class ReviewTest(GateTest):
    """seed: review-as-document. A review note, one per review from docs/templates/review.md, is
    checked like a seed: its runs are stamps and one names it, its findings carry a severity and
    a verified of fixed words, and a verified finding is judged by an existing test, case or seed,
    or none with a reason; read with comments out, and release refuses a review not whole."""

    def setUp(self):
        super().setUp()
        self.edit("docs/templates/review.md", TEMPLATE_REVIEW)
        self.edit(f"docs/reviews/{STAMP}.md", REVIEW)
        self.commit("review")
        self.note = f"docs/reviews/{STAMP}.md"

    def review(self, text: str) -> None:
        self.edit(self.note, text)

    def test_a_whole_review_is_silent_and_its_fields_are_the_templates(self):
        self.assertEqual(self.check(), (0, "", ""))
        self.review(REVIEW.replace("reviewer: a cold session", "reviewer: a cold session\nverdict: accept"))
        self.assert_problem(self.note, "verdict")
        self.review(REVIEW.replace("reviewer: a cold session", "reviewer:"))
        self.assert_problem(self.note, "reviewer")
        self.review(REVIEW.replace("created: 2026-09-17", "created: yesterday"))
        self.assert_problem(self.note, "created")

    def test_the_runs_are_stamps_and_one_of_them_names_the_note(self):
        """seed: records-outside-the-project. A review's stamps point into the factory's store as a
        build's trailer does: the gate asks for no record `runs/<stamp>` in the project."""
        self.assertFalse((self.root / "runs").exists())
        self.assertEqual(self.check(), (0, "", ""))
        self.review(REVIEW.replace(f"runs: {STAMP}", "runs:"))
        self.assert_problem(self.note, "runs")
        self.review(REVIEW.replace(f"runs: {STAMP}", f"runs: {STAMP} 20260917T000001Z"))
        self.assertEqual(self.check(), (0, "", ""))
        self.edit("runs/20260101T000000Z/numbers.json", "{}\n")  # from the review: a runs/ that lacks the stamps
        self.commit("a runs/ of another record")
        self.assertEqual(self.check(), (0, "", ""))
        self.review(REVIEW.replace(f"runs: {STAMP}", "runs: 20260917T000001Z"))
        self.assert_problem(self.note, "named")

    def test_a_finding_has_a_severity_and_a_verified_of_fixed_words(self):
        for old, new, word in (
            ("severity: defect", "severity: nit", "severity"),
            ("severity: defect\n", "", "severity"),
            ("verified: yes", "verified: maybe", "verified"),
            ("verified: yes\n", "", "verified"),
        ):
            self.review(REVIEW.replace(old, new))
            self.assert_problem(self.note, "The first thing misses an edge", word)
        self.review(REVIEW.replace("severity: defect", "severity: smell"))
        self.assertEqual(self.check(), (0, "", ""))

    def test_a_verified_finding_is_judged_by_what_exists_or_none_with_a_reason(self):
        for judged, word in (
            ("", "judged"),
            ("judged: test test_zz", "test_zz"),
            ("judged: case zz", "zz"),
            ("judged: seed zz", "zz"),
            ("judged: fixed", "judged"),
            ("judged: none:", "judged"),
            ("judged: none", "judged"),
            ("judged: test test_d, case zz", "zz"),
        ):
            self.review(REVIEW.replace("judged: test test_d\n", judged + "\n"))
            self.assert_problem(self.note, "The first thing misses an edge", word)
        self.edit("cases/zz/goal.md", "goal\n")
        self.edit("cases/zz/test_zz.py", TEST_GREEN)
        for judged in (
            "judged: test test_d",
            "judged: test RepoTest",
            "judged: case zz",
            "judged: seed a",
            "judged: test test_d, seed a, case zz",
            "judged: none: the measure never takes the value",
        ):
            self.review(REVIEW.replace("judged: test test_d", judged))
            self.assertEqual(self.check(), (0, "", ""), judged)
        self.review(REVIEW.replace("verified: yes", "verified: no").replace("judged: test test_d\n", ""))
        self.assertEqual(self.check(), (0, "", ""))

    def test_the_findings_are_read_with_comments_out_and_release_refuses_a_review_not_whole(self):
        self.review(REVIEW.replace("judged: test test_d", "%%\njudged: test test_d\n%%"))
        self.assert_problem(self.note, "judged")
        self.review(REVIEW + "\n%% a comment never closed\n")
        self.assert_problem(self.note, "comment")
        self.review(REVIEW.replace("judged: test test_d", "judged: test test_zz"))
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.edit("test_repo.py", TEST_GREEN_B)
        self.edit("AGENTS.md", AGENTS + "\nMore.\n")
        self.commit("ready")
        code, out, err = run(self.root, "release", "v0.2")
        self.assertEqual(code, 1, out)
        self.assertIn("test_zz", out)
        self.assertNotIn("v0.2", git(self.root, "tag", "-l"))

    def test_a_stamp_or_a_judged_name_is_one_path_segment(self):
        """From the review: a stamp or a name was joined to a path and looked up, so `/etc` was a
        record and `../templates/review` a seed."""
        for stamp in ("/etc", "../docs", "..", "a/b", "a\\b"):
            self.review(REVIEW.replace(f"runs: {STAMP}", f"runs: {STAMP} {stamp}"))
            self.assert_problem(self.note, stamp)
        self.edit("cases/zz/goal.md", "goal\n")
        for judged, word in (
            ("judged: seed ../templates/review", "../templates/review"),
            ("judged: case /etc", "/etc"),
            ("judged: case ../cases/zz", "../cases/zz"),
            ("judged: seed .", "judged"),
            ("judged: test ../test_repo", "../test_repo"),
        ):
            self.review(REVIEW.replace("judged: test test_d", judged))
            self.assert_problem(self.note, "The first thing misses an edge", word)

    def test_the_lines_are_read_outside_code_and_an_empty_judgement_is_none(self):
        """From the review: a `severity:` inside a fence or indented code satisfied the check, and
        `judged:` left empty, as the template ships it, was reported as an unknown judgement."""
        self.review(REVIEW.replace("severity: defect\n", "") + "\n```\nseverity: defect\n```\n")
        self.assert_problem(self.note, "The first thing misses an edge", "severity")
        self.review(REVIEW.replace("severity: defect\n", "") + "\n    severity: defect\n")
        self.assert_problem(self.note, "The first thing misses an edge", "severity")
        self.review(REVIEW.replace("severity: defect", "```\nseverity: nit\njudged: test test_zz\n```\nseverity: defect"))
        self.assertEqual(self.check(), (0, "", ""))
        self.review(REVIEW.replace("severity: defect", "~~~\nseverity: nit\n~~~\n\n    judged: none\n\nseverity: defect"))
        self.assertEqual(self.check(), (0, "", ""))
        for judged in ("judged:", "judged: test test_d,", "judged: test test_d, , seed a"):
            self.review(REVIEW.replace("judged: test test_d", judged))
            self.assert_problem(self.note, "The first thing misses an edge", "no judged")


class RenderTest(GateTest):
    """seed: the-gate. render writes CHANGELOG.md from the tags, newest first."""

    def test_render_writes_the_changelog_newest_first(self):
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.edit("test_repo.py", TEST_GREEN_B)
        self.commit("two")
        git(self.root, "tag", "v0.2")
        self.assertEqual(run(self.root, "render"), (0, "", ""))
        log = (self.root / "CHANGELOG.md").read_text()
        self.assertLess(log.index("v0.2: the next"), log.index("v0.1: the start"))
        for text in (
            "The next version does the next thing.",
            "The next thing, built.",
            "The first version did the first thing.",
            "The first thing, done.",
            "The second thing, done.",
            git(self.root, "log", "-1", "--format=%cs", "v0.1").strip(),
        ):
            self.assertIn(text, log)
        self.assertNotIn("![[", log)  # the embed is the note's, not the changelog's
        self.assertNotIn("None kept", log)  # nor are the other sections


class ReleaseTest(GateTest):
    """seed: the-gate. release refuses until everything derived agrees, then tags and renders."""

    def ready(self):
        """v0.2 ready: its seed done and named by a test, AGENTS.md changed since v0.1, committed;
        and a `uv` on PATH that builds, since a release builds the product."""
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.edit("test_repo.py", TEST_GREEN_B)
        self.edit("AGENTS.md", AGENTS + "\nRevised for v0.2.\n")
        self.commit("two")
        self.shim_uv()

    def shim_uv(self, fail: bool = False) -> Path:
        """seed: installation-and-surfaces. A `uv` first on PATH standing in for the real one: it
        logs its arguments, the directory it was run in and whether CHANGELOG.md existed when it
        ran, then makes the wheel and says so exactly as uv does -- on stderr, the path relative
        to the root and wrapped in colour escapes, nothing on stdout, measured 2026-09-21 on uv
        0.8.0 with FORCE_COLOR set -- or fails, saying why."""
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        log = Path(self.tmp.name) / "uv.log"
        body = f"#!/bin/sh\nprintf '%s\\n' \"$*\" \"$PWD\" >> '{log}'\n"
        body += f"if [ -e CHANGELOG.md ]; then echo rendered >> '{log}'; fi\n"
        if fail:
            body += "echo 'error: no build backend' >&2\nexit 1\n"
        else:
            esc = "\\033"
            body += f"mkdir -p dist && : > '{WHEEL}'\n"
            body += f"printf '{esc}[1mBuilding wheel...{esc}[0m\\n' >&2\n"
            body += f"printf 'Successfully built {esc}[36m{esc}[1m{WHEEL}{esc}[0m{esc}[39m\\n' >&2\n"
        shim = bin_dir / "uv"
        shim.write_text(body)
        shim.chmod(0o755)
        path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        self.enterContext(mock.patch.dict(os.environ, {"PATH": path}))
        self.uv_log = log
        return log

    def release(self, version: str = "v0.2") -> tuple[int, str, str]:
        return run(self.root, "release", version)

    def assert_released(self) -> str:
        """seed: installation-and-surfaces. A release that went through: exit 0, nothing on
        stderr, and the wheel it built as the last line of stdout. Returns stdout."""
        code, out, err = self.release()
        self.assertEqual((code, err), (0, ""), out)
        self.assertTrue(out.rstrip("\n").endswith(WHEEL), out)
        return out

    def assert_refused(self, *words: str, version: str = "v0.2") -> None:
        code, out, _ = self.release(version)
        self.assertEqual(code, 1, out)
        for word in words:
            self.assertIn(word, out)
        self.assertNotIn("v0.2\n", git(self.root, "tag", "-l"))
        self.assertFalse((self.root / "CHANGELOG.md").exists())

    def test_a_ready_version_is_tagged_annotated_with_the_changelog_and_rendered(self):
        self.ready()
        head = git(self.root, "rev-parse", "HEAD").strip()
        code, out, err = self.release()
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(git(self.root, "cat-file", "-t", "v0.2").strip(), "tag")
        self.assertEqual(git(self.root, "rev-parse", "v0.2^{commit}").strip(), head)
        message = git(self.root, "tag", "-l", "--format=%(contents)", "v0.2")
        self.assertIn("The next version does the next thing.", message)
        self.assertIn("The next thing, built.", message)
        self.assertNotIn("![[", message)
        log = (self.root / "CHANGELOG.md").read_text()
        self.assertLess(log.index("v0.2: the next"), log.index("v0.1: the start"))
        self.assertEqual(self.check(), (0, "", ""))  # no version in flight is fine

    def test_release_refuses_when_check_fails(self):
        self.ready()
        self.edit("docs/seeds/a.md", SEED_A.replace("value: 3", "value: 9"))
        self.commit("three")
        self.assert_refused("docs/seeds/a.md")

    def test_release_refuses_a_version_without_a_note_or_already_tagged(self):
        self.ready()
        self.assert_refused("v0.3", version="v0.3")
        self.assert_refused("v0.1", version="v0.1")

    def test_release_refuses_while_a_seed_of_the_version_is_not_done(self):
        self.ready()
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("three")
        self.assert_refused("docs/seeds/b.md")

    def test_release_refuses_a_dirty_tree(self):
        self.ready()
        (self.root / "stray.txt").write_text("stray\n")
        self.assert_refused("stray.txt")

    def test_release_refuses_when_agents_md_is_unchanged_since_the_previous_tag(self):
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.edit("test_repo.py", TEST_GREEN_B)
        self.commit("two")  # AGENTS.md as it was at v0.1
        self.assert_refused("AGENTS.md")

    def test_release_refuses_a_red_suite(self):
        self.ready()
        self.edit("test_repo.py", TEST_RED_B)
        self.commit("three")
        self.assert_refused("test")

    def test_release_reports_a_tag_it_could_not_create(self):
        """A stale lock on the ref makes git refuse the tag; the release says so, exits 1 and
        renders nothing, instead of reporting a release that did not happen."""
        self.ready()
        (self.root / ".git" / "refs" / "tags" / "v0.2.lock").write_text("held\n")
        code, out, _ = self.release()
        self.assertEqual(code, 1, out)
        self.assertIn("v0.2", out)
        self.assertIn("lock", out.lower())  # seed: the-gate-in-three. git's own words, as uv's are kept
        self.assertNotIn("v0.2\n", git(self.root, "tag", "-l"))
        self.assertFalse((self.root / "CHANGELOG.md").exists())

    def test_a_tag_git_could_not_create_is_one_line(self):
        """seed: the-gate-in-three. From the review: git's advice on a locked ref ran to eight
        lines after the problem's own; one line per problem, git's words collapsed to one."""
        self.ready()
        (self.root / ".git" / "refs" / "tags" / "v0.2.lock").write_text("held\n")
        code, out, _ = self.release()
        self.assertEqual(code, 1, out)
        lines = out.splitlines()
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("docs/versions/v0.2.md: git tag"), out)
        self.assertIn("lock", lines[0].lower())

    def test_a_release_whose_git_status_or_diff_fails_refuses_naming_the_command(self):
        """seed: the-gate-in-three. From the review, two failures the seed's Evidence named and
        its Goal forgot: `git status` failing read as a clean tree, so a tag was cut on a dirty
        one; `git diff` failing read as AGENTS.md unchanged -- the wrong problem."""
        self.ready()
        self.edit("AGENTS.md", AGENTS + "\nuncommitted\n")
        real = subprocess.run

        def failing(word):
            def run_(argv, *args, **kwargs):
                if word in argv:
                    raise OSError("git died")
                return real(argv, *args, **kwargs)

            return run_

        with mock.patch.object(subprocess, "run", failing("status")):
            code, out, _ = self.release()
        self.assertEqual(code, 1, out)
        self.assertIn("git status", out)
        self.assertIn("failed", out)
        self.assertNotIn("v0.2\n", git(self.root, "tag", "-l"))
        self.commit("committed after all")
        with mock.patch.object(subprocess, "run", failing("diff")):
            code, out, _ = self.release()
        self.assertEqual(code, 1, out)
        self.assertIn("git diff", out)
        self.assertIn("failed", out)
        self.assertNotIn("unchanged since", out)
        self.assertNotIn("v0.2\n", git(self.root, "tag", "-l"))

    def test_an_unreadable_version_note_refuses_the_release_and_render_alike(self):
        """seed: the-gate-in-three. From the review: `render` and the tag's message read an
        unreadable note as empty and rendered an empty heading, the fallback the Goal forbids."""
        self.ready()
        note = self.root / "docs" / "versions" / "v0.1.md"
        note.chmod(0)
        self.addCleanup(note.chmod, 0o644)
        code, out, _ = run(self.root, "render")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/versions/v0.1.md: cannot be read", out)
        self.assertFalse((self.root / "CHANGELOG.md").exists())
        self.assert_refused("docs/versions/v0.1.md")

    def test_release_refuses_a_note_without_changelog_bullets(self):
        self.ready()
        self.edit("docs/versions/v0.2.md", V02.replace("- The next thing, built.\n", "At release.\n"))
        self.commit("three")
        self.assert_refused("Changelog")

    def test_release_builds_the_product_at_the_clean_tag_and_says_where_it_is(self):
        """seed: installation-and-surfaces. Once the tag is cut and before the changelog is
        rendered -- the version is read from the tree, and a dirty tree is marked as one --
        `uv build --wheel` runs at the root, and the wheel's path is the release's last line -- the
        wheel this release built, not an older one `dist/` still holds, and not read off uv's
        chatter, which is on stderr and coloured."""
        self.ready()
        older = self.root / "dist" / "factory-0.1-py3-none-any.whl"
        older.parent.mkdir()
        older.write_text("")
        code, out, _ = self.release()
        self.assertEqual(code, 0, out)
        log = self.uv_log.read_text().splitlines()
        self.assertEqual(log[0].split()[:2], ["build", "--wheel"])
        self.assertEqual(Path(log[1]).resolve(), self.root.resolve())
        self.assertNotIn("rendered", log)
        self.assertEqual(git(self.root, "cat-file", "-t", "v0.2").strip(), "tag")
        self.assertTrue((self.root / "CHANGELOG.md").exists())
        last = out.rstrip("\n").splitlines()[-1]
        self.assertTrue(last.endswith(WHEEL), last)
        self.assertTrue((self.root / last).exists(), last)

    def test_a_build_that_fails_is_the_releases_failure_with_the_tag_standing_and_nothing_rendered(self):
        """seed: installation-and-surfaces. Nothing has been pushed and a tag is not a deployment:
        exit 1, naming the version and what `uv build` said; the tag stands, the changelog is not
        rendered, and there is no wheel."""
        self.ready()
        self.shim_uv(fail=True)
        code, out, _ = self.release()
        self.assertEqual(code, 1, out)
        self.assertIn("v0.2", out)
        self.assertIn("no build backend", out)
        self.assertEqual(git(self.root, "cat-file", "-t", "v0.2").strip(), "tag")
        self.assertFalse((self.root / "CHANGELOG.md").exists())
        self.assertFalse((self.root / WHEEL).exists())

    def test_a_path_under_dist_that_git_does_not_ignore_still_refuses_the_release(self):
        """seed: installation-and-surfaces. `dist/` is the release's own output only where git
        ignores it, as this repository does; in a repository that does not, a path there is an
        uncommitted change like any other and the tree is not clean. Found by the review of build
        e92ce0e, which skipped `dist/` to pass a fixture that did not ignore it."""
        self.ready()
        self.edit(".gitignore", "__pycache__/\n")
        self.commit("dist/ no longer ignored")
        stray = self.root / "dist" / "notes.txt"
        stray.parent.mkdir()
        stray.write_text("stray\n")
        self.assert_refused("dist/")

    def build(self, *paragraphs: str, amend: bool = False) -> str:
        """Everything committed as a build whose message is `feature` and then each paragraph, a
        blank line before each, or the last commit amended so; the first seven characters of the
        commit's hash."""
        git(self.root, "add", "-A")
        args = ["commit", "-q", *(["--amend"] if amend else []), "-m", "feature"]
        for paragraph in paragraphs:
            args += ["-m", paragraph]
        git(self.root, *args)
        return git(self.root, "rev-parse", "HEAD").strip()[:7]

    def build_raw(self, message: bytes, amend: bool = False) -> str:
        """Everything committed with `message` byte for byte, as `git commit -F` cleans it, or the
        last commit amended so; the first seven characters of the commit's hash."""
        git(self.root, "add", "-A")
        path = Path(self.tmp.name) / "message.txt"
        path.write_bytes(message)
        git(self.root, "commit", "-q", *(["--amend"] if amend else []), "-F", str(path))
        return git(self.root, "rev-parse", "HEAD").strip()[:7]

    def built_by(self) -> str:
        """What git's own trailer parser reads as `Built-By` in the last commit."""
        return git(self.root, "log", "-1", "--format=%(trailers:key=Built-By,valueonly)").strip()

    def built_by_bytes(self) -> bytes:
        """The same, as the bytes git prints."""
        return subprocess.run(["git", "log", "-1", "--format=%(trailers:key=Built-By,valueonly)"],
                              cwd=self.root, capture_output=True, check=True).stdout  # fmt: skip

    def assert_refused_with(self, start: str, *words: str) -> str:
        """Refused as the release refuses, with a problem line that starts with `start` and holds
        every word, no problem printed twice and no commit named by its full hash; the output."""
        code, out, _ = self.release()
        self.assertEqual(code, 1, out)
        lines = out.splitlines()
        self.assertTrue(any(line.startswith(start) and all(word in line for word in words) for line in lines), out)
        self.assertEqual(len(lines), len(set(lines)), out)
        self.assertNotRegex(out, r"\b[0-9a-f]{40}\b")
        self.assertNotIn("v0.2\n", git(self.root, "tag", "-l"))
        self.assertFalse((self.root / "CHANGELOG.md").exists())
        return out

    def test_release_refuses_a_build_whose_built_by_git_does_not_read_as_a_trailer(self):
        """seed: built-by-trailer. A `Built-By` line apart from the paragraph git reads as the
        trailers is a build the version's list misses, one line of two included: the release names
        the commit under the version's note, by its abbreviated hash whatever `core.abbrev` says,
        saying git does not read it as a trailer. The same build with its trailers together is
        released."""
        git(self.root, "config", "core.abbrev", "40")
        self.ready()
        self.edit("feature.py", "X = 1\n")
        built_by = f"Built-By: factory at 1234567, run {STAMP}"
        apart = self.build(built_by, "Co-Authored-By: t <t@t>")
        self.assertEqual(self.built_by(), "")
        out = self.assert_refused_with("docs/versions/v0.2.md:", apart, "as a trailer")
        self.assertRegex(out, rf"docs/versions/v0\.2\.md: {apart}: ")  # git's abbreviation, seven here
        one_of_two = self.build(
            f"Built-By: factory at 7654321, run {STAMP}", built_by + "\nCo-Authored-By: t <t@t>", amend=True
        )
        self.assertEqual(self.built_by(), f"factory at 1234567, run {STAMP}")
        self.assert_refused_with("docs/versions/v0.2.md:", one_of_two, "as a trailer")
        self.build(built_by + "\nCo-Authored-By: t <t@t>", amend=True)
        self.assert_released()

    def test_release_refuses_a_build_that_names_no_run(self):
        """seed: built-by-trailer. seed: records-outside-the-project. A `Built-By` whose value does
        not end `run <stamp>`, the word `run` as written and the whole stamp in the builder's
        shape, is refused under the version's note as naming no run, a stamp in git's revision
        syntax among them. The record is the factory's, kept in its store: no `runs/<stamp>` is
        asked of the project, so a build whose trailer names a run is released with no `runs/` in
        the tree, and as well with a file there named like the run, and no problem begins `runs/`."""
        self.ready()
        self.edit("feature.py", "X = 1\n")
        no_run = self.build("Built-By: factory at 1234567\nCo-Authored-By: t <t@t>")
        self.assertEqual(self.built_by(), "factory at 1234567")
        self.assert_refused_with("docs/versions/v0.2.md:", no_run, "names no run")
        dots = self.build("Built-By: factory at 1234567, run ..\nCo-Authored-By: t <t@t>", amend=True)
        self.assert_refused_with("docs/versions/v0.2.md:", dots, "names no run")
        capital = self.build(f"Built-By: factory at 1234567, Run {STAMP}\nCo-Authored-By: t <t@t>", amend=True)
        self.assert_refused_with("docs/versions/v0.2.md:", capital, "names no run")
        first = git(self.root, "rev-list", "--max-parents=0", "HEAD").strip()
        crafted = self.build(f"Built-By: factory at 1234567, run x-g{first[:7]}^{{tree}}\nCo-Authored-By: t <t@t>",
                             amend=True)  # fmt: skip
        self.assert_refused_with("docs/versions/v0.2.md:", crafted, "names no run")
        prefixed = f"{STAMP}x-g{first[:7]}^{{tree}}"
        shaped = self.build(f"Built-By: factory at 1234567, run {prefixed}\nCo-Authored-By: t <t@t>", amend=True)
        out = self.assert_refused_with("docs/versions/v0.2.md:", shaped, "names no run")  # the whole stamp has the shape
        arabic = "\u0662\u0660\u0662\u0666\u0660\u0669\u0661\u0667T\u0662\u0661\u0665\u0666\u0665\u0669Z"
        indic = self.build(f"Built-By: factory at 1234567, run {arabic}\nCo-Authored-By: t <t@t>", amend=True)
        self.assert_refused_with("docs/versions/v0.2.md:", indic, "names no run")  # from the review: the digits are ASCII's
        self.assertFalse(any(line.startswith("runs/") for line in out.splitlines()), out)
        self.build(f"Built-By: factory at 1234567, run {STAMP}\nCo-Authored-By: t <t@t>", amend=True)
        self.assertFalse((self.root / "runs").exists())
        self.edit(f"runs/{STAMP}", "a file named like the run, none of the gate's\n")
        self.commit("a file named like the run")
        self.assert_released()

    def test_the_stamp_of_a_second_run_in_one_second_is_a_run(self):
        """seed: records-outside-the-project. From the review: two runs that share a UTC second leave
        `<stamp>` and `<stamp>-2`, the builder's own names for them, and the gate read the second as
        naming no run, so a build the command had pushed would be refused at release. The shape the
        gate reads is the shape the builder writes, the stamp and, when a second shares its second,
        a dash and the run's number; the digits stay ASCII's."""
        self.ready()
        self.edit("feature.py", "X = 1\n")
        second = self.build(f"Built-By: factory at 1234567, run {STAMP}-2\nCo-Authored-By: t <t@t>")
        self.assertEqual(self.built_by(), f"factory at 1234567, run {STAMP}-2")
        self.assert_released()
        git(self.root, "tag", "-d", "v0.2")
        (self.root / "CHANGELOG.md").unlink()
        for stamp in (f"{STAMP}-", f"{STAMP}-x", f"{STAMP}-2-3", f"{STAMP}-\u0662"):
            self.build(f"Built-By: factory at 1234567, run {stamp}\nCo-Authored-By: t <t@t>", amend=True)
            self.assert_refused_with("docs/versions/v0.2.md:", "names no run")


    def test_release_reads_only_the_builds_since_the_previous_tag(self):
        """seed: built-by-trailer. A build before the previous tag, the highest `v<major>.<minor>` by
        number, v0.10 above v0.9, is not read, whatever its `Built-By`, so the four released build
        commits of v0.7 and v0.8 stay as they are. From the final review: a release lists the
        builds once, through check, and not again."""
        first = git(self.root, "rev-list", "--max-parents=0", "HEAD").strip()
        git(self.root, "tag", "v0.9", first)
        self.edit("feature.py", "X = 1\n")
        self.build("Built-By: factory at 1234567, run 20260101T000000Z", "Co-Authored-By: t <t@t>")
        git(self.root, "tag", "-f", "v0.1")
        git(self.root, "tag", "v0.10")
        self.ready()
        listings = []
        real_run = subprocess.run

        def counting(argv, *args, **kwargs):
            if argv and argv[0] == "git" and "rev-list" in argv:
                listings.append(list(argv))
            return real_run(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", counting):
            self.assert_released()
        self.assertEqual(len(listings), 1, listings)

    def test_every_problem_of_every_build_is_printed_in_one_release(self):
        """seed: built-by-trailer. seed: records-outside-the-project. From the reviews: a `Built-By`
        git does not read is still checked for its run; an empty `Built-By:` among the trailers is
        one git reads and names no run, and one apart from them is one git does not read; a line
        apart is counted unread though git reads an equal one in the trailers; a value is quoted
        with nothing but its control characters escaped; one release prints every problem of every
        build, each once; and no problem is a record's, which is the factory's to keep."""
        self.ready()
        self.edit("feature.py", "X = 1\n")
        apart = self.build(f"Built-By: factory at 1234567, run {STAMP}", "Co-Authored-By: t <t@t>")
        self.edit("other.py", "Y = 1\n")
        empty = self.build("Built-By:\nCo-Authored-By: t <t@t>")
        self.assertIn("Built-By:", git(self.root, "log", "-1", "--format=%(trailers:key=Built-By)"))
        self.edit("third.py", "Z = 1\n")
        empty_apart = self.build("Built-By:", "Co-Authored-By: t <t@t>")
        self.assertEqual(self.built_by_bytes(), b"\n")
        self.edit("fourth.py", "W = 1\n")
        built_by = f"Built-By: factory at 1234567, run {STAMP}"
        twice = self.build(built_by, f"{built_by}\nBuilt-By: factory at 7654321, run {STAMP}\nCo-Authored-By: t <t@t>")
        self.edit("fifth.py", "V = 1\n")
        cafe = self.build("Built-By: factory at café \\ x\x7fy\nCo-Authored-By: t <t@t>")
        self.assertIn("café \\ x\x7fy", git(self.root, "log", "-1", "--format=%B"))
        out = self.assert_refused_with("docs/versions/v0.2.md:", apart, "as a trailer")
        lines = out.splitlines()

        def has(start: str, commit: str, *words: str) -> bool:
            return any(line.startswith(start) and commit in line and all(w in line for w in words) for line in lines)

        self.assertFalse(any(line.startswith("runs/") for line in lines), out)
        self.assertTrue(has("docs/versions/v0.2.md:", empty, "names no run"), out)
        self.assertFalse(has("docs/versions/v0.2.md:", empty, "as a trailer"), out)
        self.assertTrue(has("docs/versions/v0.2.md:", empty_apart, "as a trailer"), out)
        self.assertTrue(has("docs/versions/v0.2.md:", empty_apart, "names no run"), out)
        self.assertTrue(has("docs/versions/v0.2.md:", twice, "as a trailer"), out)
        self.assertTrue(has("docs/versions/v0.2.md:", cafe, "names no run", "café \\ x\\x7fy"), out)

    def test_the_builds_are_read_as_git_reads_trailers(self):
        """seed: built-by-trailer. From the reviews: a `Built-By` line begins with the key in ASCII
        letters of any case, spaces allowed before the colon; what git prints is read as bytes and
        split at newlines alone, so a form feed or a carriage return is part of a value, and the
        value git reads unfolded must name the run as the line's own must; a no-break space is kept
        as git keeps it; the whole message is read, so a `Built-By` under a title with no blank
        line is a build git does not read; an indented key, a key with a letter outside ASCII, a
        key after a carriage return, a form feed before the colon and `Built-By:` past a line's
        start are no build."""
        self.ready()
        self.edit("feature.py", "X = 1\n")
        lower = self.build("built-by: factory at 1234567\nCo-Authored-By: t <t@t>")
        self.assertEqual(self.built_by(), "factory at 1234567")
        self.assert_refused_with("docs/versions/v0.2.md:", lower, "names no run")
        spaced = self.build("Built-By : factory at 1234567\nCo-Authored-By: t <t@t>", amend=True)
        self.assertEqual(self.built_by(), "factory at 1234567")
        self.assert_refused_with("docs/versions/v0.2.md:", spaced, "names no run")
        self.build(f"built-by : factory at 1234567, run {STAMP}\nCo-Authored-By: t <t@t>", amend=True)
        self.assertEqual(self.built_by(), f"factory at 1234567, run {STAMP}")  # a build, and whole
        self.edit("other.py", "Y = 1\n")
        formfeed = self.build(f"Built-By: factory at 1234567, run {STAMP}\x0cjunk\nCo-Authored-By: t <t@t>")
        self.assertEqual(self.built_by(), f"factory at 1234567, run {STAMP}\x0cjunk")
        self.assert_refused_with("docs/versions/v0.2.md:", formfeed, "names no run")
        carriage = self.build_raw(
            f"feature\n\nBuilt-By: factory at 1234567, run {STAMP}\rjunk\nCo-Authored-By: t <t@t>\n".encode(), amend=True
        )
        self.assertIn(b"\rjunk", self.built_by_bytes())
        self.assert_refused_with("docs/versions/v0.2.md:", carriage, "names no run")
        folded = self.build(f"Built-By: factory at 1234567, run {STAMP}\n  retried after a timeout\n"
                            "Co-Authored-By: t <t@t>", amend=True)  # fmt: skip
        self.assertIn("retried after a timeout", self.built_by())
        self.assert_refused_with("docs/versions/v0.2.md:", folded, "names no run")
        nbsp = self.build(f"Built-By: factory at 1234567, run {STAMP} \nCo-Authored-By: t <t@t>", amend=True)
        self.assertIn(" ".encode(), self.built_by_bytes())
        out = self.assert_refused_with("docs/versions/v0.2.md:", nbsp, "names no run")  # not the builder's shape
        self.assertNotIn("as a trailer", out)
        titled = self.build_raw(f"feature\nBuilt-By: factory at 1234567, run {STAMP}\n".encode(), amend=True)
        self.assertEqual(self.built_by_bytes(), b"\n")
        self.assert_refused_with("docs/versions/v0.2.md:", titled, "as a trailer")
        self.build_raw(
            (
                "feature\n\nnotes\n"
                "  Built-By: factory at 1234567, run 20260101T000000Z\n"
                "Built-By\x0c: factory at 1234567, run 20260101T000000Z\n"
                "Buılt-By: factory at 1234567, run 20260101T000000Z\n"
                "notes\rBuilt-By: factory at 1234567, run 20260101T000000Z\n"
                "the words Built-By: and a run name a build only at a line's start\n\n"
                "Co-Authored-By: t <t@t>\n"
            ).encode(),
            amend=True,
        )
        self.assert_released()

    def test_a_git_failure_refuses_the_release_and_no_path_hides_the_builds(self):
        """seed: built-by-trailer. From the reviews: the commits are listed, and each read, as
        revisions whatever paths the checkout holds, a file named like the range or like a
        commit's hash, and a git command that fails while the builds are read refuses the release
        under the version's note, never reads as no builds."""
        self.ready()
        self.edit("v0.1..HEAD", "a file named like the range\n")
        apart = self.build(f"Built-By: factory at 1234567, run {STAMP}", "Co-Authored-By: t <t@t>")
        self.assert_refused_with("docs/versions/v0.2.md:", apart, "as a trailer")
        self.edit(git(self.root, "rev-parse", "HEAD").strip(), "a file named like the build's hash\n")
        self.commit("a file named like the build")
        self.assert_refused_with("docs/versions/v0.2.md:", apart, "as a trailer")
        parent = git(self.root, "rev-parse", "HEAD^").strip()
        (self.root / ".git" / "objects" / parent[:2] / parent[2:]).unlink()
        listed = subprocess.run(["git", "rev-list", "v0.1..HEAD", "--"], cwd=self.root, capture_output=True)
        self.assertNotEqual(listed.returncode, 0)
        self.assert_refused_with("docs/versions/v0.2.md:", "git", "rev-list")

    def test_a_message_git_prints_in_another_encoding_does_not_end_the_release(self):
        """seed: built-by-trailer. From the reviews: output git gives in an encoding other than UTF-8
        is read with what cannot be decoded replaced, so a commit whose message git would print in
        Latin-1 leaves the release to tag instead of raising; and the repository's display settings
        do not change what is read, so a build git does not read is refused whether git would print
        messages in Latin-1 or in UTF-16."""
        git(self.root, "config", "i18n.logOutputEncoding", "ISO-8859-1")
        self.ready()
        self.edit("notes.txt", "n\n")
        self.commit("café: a commit, not a build")
        self.edit("feature.py", "X = 1\n")
        apart = self.build(f"Built-By: factory at 1234567, run {STAMP}", "Co-Authored-By: t <t@t>")
        self.assert_refused_with("docs/versions/v0.2.md:", apart, "as a trailer")
        git(self.root, "config", "i18n.logOutputEncoding", "UTF-16")
        self.assert_refused_with("docs/versions/v0.2.md:", apart, "as a trailer")
        git(self.root, "config", "i18n.logOutputEncoding", "ISO-8859-1")
        self.build("a feature, not a build", amend=True)
        self.assert_released()


class UsageTest(GateTest):
    """seed: the-gate. A missing or unknown command is a usage error on stderr, exit 2."""

    def test_usage_errors_exit_two(self):
        for args in ((), ("bogus",), ("release",)):
            code, out, err = run(self.root, *args)
            self.assertEqual(code, 2, args)
            self.assertIn("usage", err)
            self.assertEqual(out, "")
        self.assertFalse((self.root / "CHANGELOG.md").exists())
        self.assertEqual(git(self.root, "tag", "-l").split(), ["v0.1"])


class ShapeTest(GateTest):
    """seed: the-gate-in-three. The gate's own shapes once its readers have gone to their
    modules: a `Problem` that prints as `path: message`, a `check` that returns problems, a
    `render` that returns the changelog's text and writes nothing, and no reader left behind."""

    def test_a_problem_is_a_path_and_a_message_and_prints_as_one_line(self):
        problem = gate.Problem("docs/seeds/a.md", "no such thing")
        self.assertEqual(str(problem), "docs/seeds/a.md: no such thing")
        self.assertEqual((problem.path, problem.message), ("docs/seeds/a.md", "no such thing"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            problem.path = "elsewhere"

    def test_check_returns_problems_and_render_returns_the_changelog(self):
        self.assertEqual(gate.problems_check(self.root), [])
        self.edit("docs/seeds/a.md", SEED_A.replace("value: 3", "value: 9"))
        problems = gate.problems_check(self.root)
        self.assertTrue(problems)
        self.assertTrue(all(isinstance(problem, gate.Problem) for problem in problems))
        self.assertEqual(problems[0].path, "docs/seeds/a.md")
        text = gate.render(self.root)
        self.assertTrue(text.startswith("# Changelog"))
        self.assertIn("v0.1: the start", text)
        self.assertFalse((self.root / "CHANGELOG.md").exists())
        self.assertFalse(hasattr(gate, "problems_render"))

    def test_the_readers_live_in_their_modules_and_not_in_the_gate(self):
        import repo
        import vault

        for name in ("frontmatter", "review_findings", "changelog_bullets", "base_named"):
            self.assertTrue(callable(getattr(vault, name, None)), f"vault.{name}")
        for name in ("git", "tags", "builds", "trailers", "tests", "suite", "tag", "build_wheel"):
            self.assertTrue(callable(getattr(repo, name, None)), f"repo.{name}")
        gone = (
            "frontmatter", "_read_vault", "_git", "_git_bytes", "_tags", "_builds", "_build_trailers",
            "_test_docstrings", "_test_names", "_suite_green", "_annotate", "_build_wheel", "_wheels",
        )  # fmt: skip
        for name in gone:
            self.assertFalse(hasattr(gate, name), f"gate.{name}")

    def test_the_gate_reads_no_file_and_runs_no_git_of_its_own(self):
        """seed: the-gate-in-three. From the review: `_read` stayed in the gate with three raw git
        reads beside it, and they were exactly the failures still silent. Every read goes through
        vault and repo, and the module is imported by its name."""
        source = Path(gate.__file__).read_text()
        for token in ("read_text(", "subprocess", "repo.git(", "def _read(", "import vault as"):
            self.assertNotIn(token, source, token)
        self.assertFalse(hasattr(gate, "_read"))


if __name__ == "__main__":
    unittest.main()
