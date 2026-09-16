"""The gate's acceptance tests, written from docs/seeds/the-gate.md before the code.

    uv run python -m unittest test_gate -v

Every test builds a small vault and a git repository in a temporary directory, so nothing here
touches the factory's own docs/ or tags. The interface under test is the seed's Goal:
gate.main(argv, root) shaped like builder.main, argv[0] the program name; problems on stdout, one
per line, each starting with the path relative to root; exit 1 when there is any, 0 and silence
when there is none; usage on stderr and exit 2 for a missing or unknown command.
"""

import contextlib
import io
import os
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
    write(root, ".gitignore", "__pycache__/\n")
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

    def test_templates_are_exempt(self):
        self.edit("docs/templates/seed.md", TEMPLATE_SEED.replace("type: seed", "type: whatever"))
        self.assertEqual(self.check(), (0, "", ""))


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
        """v0.2 ready: its seed done and named by a test, AGENTS.md changed since v0.1, committed."""
        self.edit("docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.edit("test_repo.py", TEST_GREEN_B)
        self.edit("AGENTS.md", AGENTS + "\nRevised for v0.2.\n")
        self.commit("two")

    def release(self, version: str = "v0.2") -> tuple[int, str, str]:
        return run(self.root, "release", version)

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
        self.assertEqual(self.release(), (0, "", ""))
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
        self.assertNotIn("v0.2\n", git(self.root, "tag", "-l"))
        self.assertFalse((self.root / "CHANGELOG.md").exists())

    def test_release_refuses_a_note_without_changelog_bullets(self):
        self.ready()
        self.edit("docs/versions/v0.2.md", V02.replace("- The next thing, built.\n", "At release.\n"))
        self.commit("three")
        self.assert_refused("Changelog")


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


if __name__ == "__main__":
    unittest.main()
