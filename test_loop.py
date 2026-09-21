"""The loop, derived: what `loop.py` gives `gate.py next`.

    uv run python -m unittest test_loop -v

Written from docs/seeds/the-step-nobody-noticed.md before the code, and amended after its first
build's review. The rules are held over a `Facts` built by hand for every row, in the table's
order; `gather` is held over the gate tests' own fixture, advanced step by step as the loop would
advance it.
"""

import dataclasses
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gate import (
    AGENTS,
    IDENTITY,
    REVIEW,
    SEED_A,
    SEED_B,
    STAMP,
    TEST_GREEN_B,
    TEST_RED_B,
    git,
    make_repo,
    run,
    write,
)

import loop

ROOT = Path("/somewhere/repo")
AFTER = dict(tags=frozenset({"v0.1", "v0.2"}), highest="v0.2", in_flight=None, after_tag=True)


def seed(**over) -> loop.SeedFacts:
    """A seed of the version in flight, at `building` with red tests unless said otherwise."""
    base = dict(
        name="b",
        status="building",
        tests=("test_repo.RepoTest.test_b",),
        colour="red",
        builds=(),
        reviewed=None,
    )
    base.update(over)
    return loop.SeedFacts(**base)


def facts(**over) -> loop.Facts:
    """Facts with nothing to do before the seeds: a version in flight on its branch, checked
    out, a clean tree, no tag at the head, nothing unknown; overridden by keyword."""
    base = dict(
        root=ROOT,
        problems=(),
        tags=frozenset({"v0.1"}),
        highest="v0.1",
        head="abc1234abc1234abc1234abc1234abc1234abc12",
        branch="v0.2",
        attached=True,
        in_flight="v0.2",
        seeds=(),
        agents_changed=True,
        bullets=True,
        dirty=(),
        after_tag=False,
        changelog_current=None,
        main_at_head=None,
        mirror_at_head=None,
        instance_version=None,
        unknown=(),
    )
    base.update(over)
    return loop.Facts(**base)


def step(**over) -> str:
    return loop.next_step(facts(**over)).text


class RulesTest(unittest.TestCase):
    """seed: the-step-nobody-noticed. One row per state of the loop, the first that applies read
    top to bottom; every rule a pure function of `Facts`; the seeds taken in name order and the
    first with something to do stepped, whatever its row."""

    def test_the_rules_are_a_table_of_thirteen_rows_the_last_for_what_could_not_be_read(self):
        self.assertIsInstance(loop.RULES, tuple)
        self.assertEqual(len(loop.RULES), 13)
        self.assertEqual(len({rule.name for rule in loop.RULES}), 13)
        for rule in loop.RULES:
            self.assertTrue(rule.name)
            self.assertTrue(callable(rule.applies))
            self.assertTrue(callable(rule.step))
        found = loop.next_step(facts(in_flight=None))
        self.assertTrue(found.name)
        self.assertTrue(found.text.startswith("open a version:"))
        # With nothing unknown, one of the twelve rows of the loop applies to every state.
        for status in ("open", "spec", "building", "done", "rejected"):
            for colour in ("green", "red", "none"):
                for tests in ((), ("test_repo.RepoTest.test_b",)):
                    with self.subTest(status=status, colour=colour, tests=tests):
                        one = facts(seeds=(seed(status=status, colour=colour, tests=tests),))
                        self.assertNotEqual(loop.next_step(one).name, loop.RULES[-1].name)

    def test_1_a_problem_of_the_gate_comes_before_everything_after_a_tag_too(self):
        text = step(problems=("docs/seeds/a.md: value 9 is not 1 to 5",), in_flight=None)
        self.assertEqual(text, "fix: docs/seeds/a.md: value 9 is not 1 to 5")
        text = step(**AFTER, problems=("docs/seeds/b.md: seed of v0.2 is spec",), changelog_current=False)
        self.assertEqual(text, "fix: docs/seeds/b.md: seed of v0.2 is spec")

    def test_2_after_a_tag_the_acts_that_follow_it_in_order(self):
        self.assertEqual(step(**AFTER, changelog_current=False), "commit CHANGELOG.md")
        self.assertEqual(
            step(**AFTER, changelog_current=True, main_at_head=False),
            "fast-forward main: git merge --ff-only heads/v0.2",
        )
        self.assertEqual(
            step(**AFTER, changelog_current=True, main_at_head=True, mirror_at_head=False),
            "push: git push origin main --tags",
        )
        self.assertEqual(
            step(**AFTER, changelog_current=True, main_at_head=True, mirror_at_head=True, instance_version="0.1"),
            "install: uv tool install --reinstall dist/factory-0.2-py3-none-any.whl",
        )
        self.assertEqual(
            step(**AFTER, changelog_current=True, main_at_head=True, mirror_at_head=True, instance_version="0.2"),
            "v0.2 is out: open the next version",
        )
        # A fact unknown skips its act and the last still holds: no thirteenth row answers here.
        unknown = ("instance: uv tool list failed: no uv on PATH",)
        found = facts(**AFTER, changelog_current=True, main_at_head=True, mirror_at_head=True, unknown=unknown)
        self.assertEqual(loop.next_step(found).text, "v0.2 is out: open the next version")
        text = loop.render(found)
        self.assertTrue(text.startswith("next: v0.2 is out: open the next version\n"), text)
        self.assertIn("unknown: instance: uv tool list failed: no uv on PATH", text)

    def test_3_no_version_in_flight(self):
        self.assertTrue(step(in_flight=None).startswith("open a version:"))

    def test_4_a_version_with_no_seed(self):
        self.assertEqual(step(seeds=()), "promote a seed to v0.2")

    def test_5_a_seed_at_open(self):
        self.assertEqual(step(seeds=(seed(status="open", tests=(), colour="none"),)), "write the Goal of b; status spec")

    def test_6_a_seed_at_spec_or_building_named_by_no_test(self):
        text = "write red tests naming seed: b; commit them; status building"
        self.assertEqual(step(seeds=(seed(status="spec", tests=(), colour="none"),)), text)
        self.assertEqual(step(seeds=(seed(status="building", tests=(), colour="none"),)), text)

    def test_7_a_seed_at_spec_named_by_tests_is_set_to_building(self):
        self.assertEqual(step(seeds=(seed(status="spec"),)), "set b to building: its tests name it")
        # A seed rejected after its tests were written has nothing to do, whatever they say.
        self.assertEqual(step(seeds=(seed(status="rejected"),)), "release: uv run gate.py release v0.2")

    def test_8_red_tests_mean_a_build_and_a_detach_when_the_branch_is_checked_out(self):
        command = f"build b: factory-build {ROOT} v0.2 docs/seeds/b.md"
        self.assertEqual(step(seeds=(seed(),)), f"{command} -- detach first: git switch --detach")
        self.assertEqual(step(seeds=(seed(),), attached=False), command)
        self.assertEqual(step(seeds=(seed(),), branch="main", attached=True), f"build b: factory-build {ROOT} main docs/seeds/b.md -- detach first: git switch --detach")
        self.assertEqual(step(seeds=(seed(),), branch=None, attached=False), f"build b: factory-build {ROOT} <branch> docs/seeds/b.md")

    def test_9_green_with_no_build(self):
        self.assertTrue(step(seeds=(seed(colour="green"),)).startswith("b is green with no build:"))

    def test_10_green_and_built_but_not_reviewed(self):
        built = (loop.Build("abc1234", STAMP),)
        text = step(seeds=(seed(colour="green", builds=built, reviewed=False),))
        self.assertTrue(text.startswith(f"review build {STAMP} of b:"), text)

    def test_11_green_built_and_reviewed(self):
        built = (loop.Build("abc1234", STAMP),)
        self.assertEqual(step(seeds=(seed(colour="green", builds=built, reviewed=True),)), "set b to done")

    def test_12_every_seed_done_or_rejected_means_the_release_and_its_preconditions_first(self):
        done = (seed(status="done", colour="green"),)
        self.assertEqual(step(seeds=done, agents_changed=False), "revise AGENTS.md: unchanged since v0.1")
        self.assertEqual(step(seeds=done, bullets=False), "write a ## Changelog bullet in docs/versions/v0.2.md")
        self.assertEqual(step(seeds=done, dirty=("x.txt", "y.txt")), "commit: x.txt y.txt")
        self.assertEqual(step(seeds=done), "release: uv run gate.py release v0.2")
        # Done or rejected is terminal: red tests, or none, do not reopen a seed.
        self.assertEqual(step(seeds=(seed(status="done", colour="red"),)), "release: uv run gate.py release v0.2")
        self.assertEqual(step(seeds=(seed(status="rejected", tests=(), colour="none"),)), "release: uv run gate.py release v0.2")

    def test_13_a_seed_whose_tests_could_not_run_is_the_last_row_and_names_the_unknown(self):
        unknown = ("tests of b: python -m unittest test_repo.RepoTest.test_b failed: timed out after 300 seconds",)
        found = facts(seeds=(seed(colour=None),), unknown=unknown)
        self.assertEqual(loop.next_step(found).name, loop.RULES[-1].name)
        self.assertEqual(loop.next_step(found).text, f"nothing to do that is known: {unknown[0]}")

    def test_the_first_seed_with_something_to_do_is_the_one_stepped_whatever_its_row(self):
        two = (seed(name="a"), seed(name="b", status="open", tests=(), colour="none"))
        self.assertTrue(step(seeds=two).startswith("build a:"))
        two = (seed(name="a", status="done", colour="green"), seed(name="b"))
        self.assertTrue(step(seeds=two).startswith("build b:"))
        two = (seed(name="a", colour=None), seed(name="b", status="open", tests=(), colour="none"))
        self.assertEqual(step(seeds=two, unknown=("tests of a: could not run",)), "write the Goal of b; status spec")

    def test_a_row_whose_fact_is_unknown_is_skipped_and_never_read_as_a_value(self):
        """From the second review: an unknown version in flight printed "open a version", an
        unknown tree printed "release", an act with an unknown fact was dropped three different
        ways. A fact that is None is skipped with its row, whatever the row."""
        last = loop.RULES[-1].name
        why = ("tags: git tag -l failed: git died",)
        self.assertEqual(loop.next_step(facts(tags=None, highest=None, in_flight=None, unknown=why)).name, last)
        done = (seed(status="done", colour="green"),)
        for field in ("dirty", "agents_changed", "bullets"):
            with self.subTest(field=field):
                found = facts(seeds=done, unknown=(f"{field}: git died",), **{field: None})
                self.assertEqual(loop.next_step(found).name, last)
        unbuilt = (seed(colour="green", builds=None),)
        self.assertEqual(loop.next_step(facts(seeds=unbuilt, unknown=("builds of b: git died",))).name, last)
        # After a tag, an act whose fact is unknown is skipped and the next act considered.
        after = dict(**AFTER, unknown=("main: git died",))
        self.assertEqual(step(**after, changelog_current=True, main_at_head=None, mirror_at_head=False), "push: git push origin main --tags")
        after = dict(**AFTER, unknown=("changelog: cannot be read",))
        self.assertEqual(step(**after, changelog_current=None, main_at_head=False), "fast-forward main: git merge --ff-only heads/v0.2")
        after = dict(**AFTER, unknown=("changelog: x", "main: x", "mirror: x", "instance: x"))
        self.assertEqual(step(**after), "v0.2 is out: open the next version")

    def test_the_table_is_the_only_dispatch_and_has_no_fallback_beside_it(self):
        """From the second review: the seed rows were decided by two if-chains beside RULES, a
        dead tuple named them a third time, and next_step kept a fallback after the table."""
        with mock.patch.object(loop, "RULES", ()):
            with self.assertRaises(Exception):
                loop.next_step(facts())
        self.assertFalse(hasattr(loop, "SEED_ROWS"))
        source = Path(loop.__file__).read_text()
        self.assertEqual(source.count("nothing to do that is known"), 1, "the last row's text, once")

    def test_facts_are_frozen_and_have_no_field_nobody_reads(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            facts().head = "elsewhere"
        self.assertNotIn("has_goal", {field.name for field in dataclasses.fields(loop.SeedFacts)})


class GatherTest(unittest.TestCase):
    """seed: the-step-nobody-noticed. `gather(root)` reads every fact once through vault and
    repo, runs a seed's own tests for their colour, and answers `None` with a line rather than
    guessing; the fixture is advanced as the loop would advance it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, IDENTITY))
        self.root = make_repo(Path(self.tmp.name))
        # The gate's fixture has its head at the v0.1 tag; a version in flight is two commits
        # past its release at least -- the changelog's and its own -- so the loop's fixture is.
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## v0.1: the start\n")
        self.commit("CHANGELOG.md rendered for v0.1")
        write(self.root, "opened.txt", "v0.2 opens\n")
        self.commit("v0.2 opens")
        self.shim_uv("factory v0.1\n- factory-build\n")

    def shim_uv(self, says: str) -> None:
        """A `uv` first on PATH whose `tool list` says what the instance is -- and which, unlike
        the attended agent's first shim, refuses any other invocation, since the first build
        passed `tool list` as one word and the shim answered anyway."""
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        shim = bin_dir / "uv"
        shim.write_text(
            "#!/bin/sh\n"
            'if [ "$1 $2" != "tool list" ]; then echo "error: unrecognized subcommand" >&2; exit 2; fi\n'
            f"printf '%b' '{says}'\n"
        )
        shim.chmod(0o755)
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}))

    def commit(self, message: str = "more") -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def current_branch(self) -> str:
        return git(self.root, "branch", "--show-current").strip()

    def test_the_fixture_is_read_as_it_is(self):
        found = loop.gather(self.root)
        self.assertEqual(found.root, self.root)
        self.assertEqual(found.problems, ())
        self.assertEqual((found.tags, found.highest), (frozenset({"v0.1"}), "v0.1"))
        self.assertEqual(found.head, git(self.root, "rev-parse", "HEAD").strip())
        self.assertEqual((found.branch, found.attached), (self.current_branch(), True))
        self.assertEqual(found.in_flight, "v0.2")
        self.assertEqual([s.name for s in found.seeds], ["b"])
        b = found.seeds[0]
        self.assertEqual((b.status, b.tests, b.colour, b.builds, b.reviewed), ("spec", (), "none", (), None))
        self.assertEqual((found.agents_changed, found.bullets, found.dirty), (False, True, ()))
        self.assertFalse(found.after_tag)
        self.assertEqual(found.unknown, ())  # nothing after a tag is asked before one
        self.assertEqual(loop.next_step(found).text, "write red tests naming seed: b; commit them; status building")

    def test_the_loop_advances_with_the_fixture(self):
        write(self.root, "test_repo.py", TEST_RED_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("red")
        found = loop.gather(self.root)
        self.assertEqual(found.seeds[0].tests, ("test_repo.RepoTest.test_b",))
        self.assertEqual(found.seeds[0].colour, "red")
        self.assertEqual(
            loop.next_step(found).text,
            f"build b: factory-build {self.root} {self.current_branch()} docs/seeds/b.md -- detach first: git switch --detach",
        )

        write(self.root, "test_repo.py", TEST_GREEN_B)
        self.commit("green")
        found = loop.gather(self.root)
        self.assertEqual(found.seeds[0].colour, "green")
        self.assertTrue(loop.next_step(found).text.startswith("b is green with no build:"))

        write(self.root, "feature.py", "X = 1\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", f"b\n\nBuilt-By: factory at v0.1, run {STAMP}")
        built = git(self.root, "rev-parse", "HEAD").strip()
        found = loop.gather(self.root)
        self.assertEqual(found.seeds[0].builds, (loop.Build(built, STAMP),))
        self.assertFalse(found.seeds[0].reviewed)
        self.assertTrue(loop.next_step(found).text.startswith(f"review build {STAMP} of b:"))

        write(self.root, "docs/templates/review.md", REVIEW.replace("2026-09-17", '"{{date}}"').replace(STAMP, ""))
        write(self.root, f"docs/reviews/{STAMP}.md", REVIEW)
        self.commit("reviewed")
        found = loop.gather(self.root)
        self.assertTrue(found.seeds[0].reviewed)
        self.assertEqual(loop.next_step(found).text, "set b to done")

        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        self.commit("done")
        found = loop.gather(self.root)
        self.assertEqual(loop.next_step(found).text, "revise AGENTS.md: unchanged since v0.1")
        write(self.root, "AGENTS.md", AGENTS + "\nRevised for v0.2.\n")
        found = loop.gather(self.root)
        self.assertEqual(found.dirty, ("AGENTS.md",))
        self.assertEqual(loop.next_step(found).text, "commit: AGENTS.md")
        self.commit("revised")
        found = loop.gather(self.root)
        self.assertEqual(loop.next_step(found).text, "release: uv run gate.py release v0.2")

    def test_a_commit_named_like_the_seed_without_a_trailer_is_no_build(self):
        write(self.root, "test_repo.py", TEST_GREEN_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("b")  # the seed's name as a subject, and no Built-By
        found = loop.gather(self.root)
        self.assertEqual(found.seeds[0].builds, ())
        self.assertTrue(loop.next_step(found).text.startswith("b is green with no build:"))

    def test_a_detached_head_is_not_attached_and_the_build_names_the_branch_at_the_head(self):
        write(self.root, "test_repo.py", TEST_RED_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("red")
        branch = self.current_branch()
        git(self.root, "switch", "-q", "--detach")
        found = loop.gather(self.root)
        self.assertEqual((found.branch, found.attached), (branch, False))
        self.assertEqual(loop.next_step(found).text, f"build b: factory-build {self.root} {branch} docs/seeds/b.md")

    def test_after_the_tag_the_acts_are_read_and_the_mirror_is_unknown_here(self):
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        write(self.root, "test_repo.py", TEST_GREEN_B)
        self.commit("b done, as a release requires")
        git(self.root, "tag", "-a", "v0.2", "-m", "the next")
        found = loop.gather(self.root)
        self.assertEqual(found.problems, ())
        self.assertTrue(found.after_tag)
        self.assertIsNone(found.in_flight)
        self.assertFalse(found.changelog_current)
        self.assertEqual(loop.next_step(found).text, "commit CHANGELOG.md")
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## v0.2: the next\n")
        self.commit("CHANGELOG.md rendered for v0.2")
        found = loop.gather(self.root)
        self.assertTrue(found.after_tag)  # one commit past the tag, the changelog's
        self.assertTrue(found.changelog_current)
        self.assertIsNone(found.mirror_at_head)  # no origin here
        self.assertTrue(any(line.startswith("mirror:") for line in found.unknown), found.unknown)
        self.assertEqual(found.instance_version, "0.1")
        expected = "install: uv tool install --reinstall dist/factory-0.2-py3-none-any.whl"
        if self.current_branch() != "main":
            expected = "fast-forward main: git merge --ff-only heads/v0.2"
        self.assertEqual(loop.next_step(found).text, expected)
        write(self.root, "later.txt", "x\n")  # the attended agent's first version committed a clean tree
        self.commit("two past the tag")
        self.assertFalse(loop.gather(self.root).after_tag)

    def test_a_tree_that_is_no_checkout_inside_another_repository_reads_nothing_of_it(self):
        outer = Path(self.tmp.name) / "outer"
        outer.mkdir()
        git(outer, "init", "-q")
        (outer / "seed.txt").write_text("x\n")
        git(outer, "add", "-A")
        git(outer, "commit", "-q", "-m", "one")
        git(outer, "tag", "v9.9")
        copy = outer / "inner"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        calls: list[list[str]] = []
        real = subprocess.run

        def recording(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", recording):
            found = loop.gather(copy)
        for name in ("tags", "highest", "head", "branch", "attached", "dirty", "agents_changed", "after_tag", "in_flight"):
            self.assertIsNone(getattr(found, name), name)
            self.assertTrue(any(line.startswith(f"{name}:") for line in found.unknown), f"{name}: no line in {found.unknown}")
        text = loop.render(found)
        self.assertNotIn("v9.9", text)
        self.assertTrue(text.startswith("next: fix: "), text)  # the gate's own lines on a non-checkout
        asked = [argv for argv in calls if argv and argv[0] == "git" and ("tag" in argv or "rev-list" in argv)]
        self.assertEqual(asked, [], "the enclosing repository was asked for its tags or commits")

    def test_tests_that_cannot_run_are_unknown_and_not_none(self):
        write(self.root, "test_repo.py", TEST_RED_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("red")
        real = subprocess.run

        def hanging(argv, *args, **kwargs):
            if "unittest" in argv:
                raise subprocess.TimeoutExpired(argv, 300)
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", hanging):
            found = loop.gather(self.root)
        self.assertEqual(found.seeds[0].tests, ("test_repo.RepoTest.test_b",))
        self.assertIsNone(found.seeds[0].colour)
        self.assertTrue(any(line.startswith("tests of b:") for line in found.unknown), found.unknown)
        self.assertTrue(loop.next_step(found).text.startswith("nothing to do that is known: tests of b:"))

    def test_the_mirror_is_asked_only_after_a_tag_and_with_a_timeout(self):
        calls: list[tuple[list[str], dict]] = []
        real = subprocess.run

        def recording(argv, *args, **kwargs):
            calls.append((list(argv), kwargs))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", recording):
            loop.gather(self.root)
        self.assertFalse([argv for argv, _ in calls if "ls-remote" in argv])
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        write(self.root, "test_repo.py", TEST_GREEN_B)
        self.commit("done")
        git(self.root, "tag", "-a", "v0.2", "-m", "the next")
        calls.clear()
        with mock.patch.object(subprocess, "run", recording):
            loop.gather(self.root)
        remote = [kwargs for argv, kwargs in calls if "ls-remote" in argv]
        self.assertEqual(len(remote), 1)
        self.assertGreater(remote[0].get("timeout") or 0, 0)

    def test_every_fact_that_could_not_be_read_has_its_line(self):
        real = subprocess.run

        def failing(argv, *args, **kwargs):
            if "status" in argv or ("tag" in argv and "-l" in argv):
                raise OSError("git died")
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", failing):
            found = loop.gather(self.root)
        self.assertIsNone(found.dirty)
        self.assertIsNone(found.tags)
        self.assertIsNone(found.in_flight)  # not inferred from the notes when the tags are unknown
        self.assertTrue(any(line.startswith("dirty:") for line in found.unknown), found.unknown)
        self.assertTrue(any(line.startswith("tags:") for line in found.unknown), found.unknown)

    def test_changelog_current_is_exact_and_the_instance_survives_colour(self):
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        write(self.root, "test_repo.py", TEST_GREEN_B)
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## v0.10: far ahead\n")
        self.commit("done, with a changelog naming a later version")
        git(self.root, "tag", "-a", "v0.1.1", "-m", "no")  # not a version tag; ignored
        git(self.root, "tag", "-a", "v0.2", "-m", "the next")
        self.shim_uv("\\033[1mfactory\\033[0m v0.2\\n- factory-build\\n")
        found = loop.gather(self.root)
        self.assertEqual(found.highest, "v0.2")
        self.assertFalse(found.changelog_current)
        self.assertEqual(found.instance_version, "0.2")

    def test_seeds_are_in_name_order(self):
        write(self.root, "docs/seeds/b-c.md", SEED_B.replace("status: spec", "status: open").replace("## Goal", "## Idea"))
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: open").replace("## Goal", "## Idea"))
        self.commit("two open seeds")
        found = loop.gather(self.root)
        self.assertEqual([s.name for s in found.seeds], ["b", "b-c"])

    def test_each_fact_is_read_once(self):
        for name in ("c", "e"):
            write(self.root, f"docs/seeds/{name}.md", SEED_B)
        self.commit("three seeds of v0.2")
        calls: list[list[str]] = []
        real = subprocess.run

        def recording(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", recording):
            loop.gather(self.root)
        gits = [argv[1:] for argv in calls if argv and argv[0] == "git"]
        # The Vault is read once and handed to the gate; the gate's own check reads the tags and
        # the builds for itself, and gather reads each once besides, so at most two of those.
        self.assertEqual(sum(1 for argv in gits if "ls-files" in argv), 1, gits)
        for words in (["rev-list"], ["tag", "-l"]):
            self.assertLessEqual(sum(1 for argv in gits if all(w in argv for w in words)), 2, words)
        subjects = [argv for argv in gits if "log" in argv and "--format=%s" in argv]
        self.assertEqual(len(subjects), len({tuple(argv) for argv in subjects}), "a subject read twice")

    def test_a_problem_of_the_gate_is_the_step(self):
        write(self.root, "docs/seeds/a.md", SEED_A.replace("value: 3", "value: 9"))
        found = loop.gather(self.root)
        self.assertTrue(found.problems)
        self.assertTrue(loop.next_step(found).text.startswith("fix: docs/seeds/a.md"))

    def test_the_next_version_note_does_not_hide_the_acts_after_a_tag(self):
        """From the second review: after_tag was short-circuited by a version in flight, so writing
        the next note before push and install dropped those rows -- the class of miss this seed
        exists to remove. after_tag is git's distance, nothing else."""
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        write(self.root, "test_repo.py", TEST_GREEN_B)
        self.commit("done")
        git(self.root, "tag", "-a", "v0.2", "-m", "the next")
        write(self.root, "docs/versions/v0.3.md", "---\ntype: version\n---\n\n# v0.3: after\n\nSoon.\n\n## Changelog\n\n-\n")
        found = loop.gather(self.root)
        self.assertTrue(found.after_tag)
        self.assertEqual(found.in_flight, "v0.3")
        self.assertEqual(loop.next_step(found).text, "commit CHANGELOG.md")

    def test_a_listing_failure_inside_a_checkout_is_named_as_such_and_the_rest_is_still_read(self):
        """From the second review: with `git ls-files` failing inside a real checkout, every git
        fact was declared "not a git checkout"; the directory is one, git answered everything
        else, and only the listing failed."""
        head = git(self.root, "rev-parse", "HEAD").strip()
        real = subprocess.run

        def failing(argv, *args, **kwargs):
            if "ls-files" in argv:
                raise OSError("git died")
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", failing):
            found = loop.gather(self.root)
        self.assertEqual(found.head, head)
        self.assertEqual(found.tags, frozenset({"v0.1"}))
        self.assertFalse(any("not a git checkout" in line for line in found.unknown), found.unknown)
        self.assertTrue(loop.next_step(found).text.startswith("fix: docs/: git ls-files"), loop.render(found))

    def test_every_none_after_a_tag_has_its_line_too(self):
        """From the second review: an unreadable CHANGELOG.md read as "not current" with no line,
        and a failing rev-list as "no build" with none."""
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        write(self.root, "test_repo.py", TEST_GREEN_B)
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## v0.2: the next\n")
        self.commit("done, changelog written")
        git(self.root, "tag", "-a", "v0.2", "-m", "the next")
        changelog = self.root / "CHANGELOG.md"
        changelog.chmod(0)
        self.addCleanup(changelog.chmod, 0o644)
        found = loop.gather(self.root)
        self.assertIsNone(found.changelog_current)
        self.assertTrue(any(line.startswith("changelog:") for line in found.unknown), found.unknown)
        changelog.chmod(0o644)
        write(self.root, "docs/seeds/c.md", SEED_B.replace("version: v0.2", "version: v0.3").replace("status: spec", "status: building"))
        write(self.root, "docs/versions/v0.3.md", "---\ntype: version\n---\n\n# v0.3: after\n\nSoon.\n\n## Changelog\n\n-\n")
        write(self.root, "test_repo.py", TEST_GREEN_B.replace("seed: b.", "seed: c."))
        self.commit("v0.3 opens")
        real = subprocess.run

        def failing(argv, *args, **kwargs):
            if "rev-list" in argv:
                raise OSError("git died")
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", failing):
            found = loop.gather(self.root)
        self.assertEqual([s.name for s in found.seeds], ["c"])
        self.assertIsNone(found.seeds[0].builds)
        self.assertTrue(any(line.startswith("builds of c:") for line in found.unknown), found.unknown)

    def test_a_stamp_with_junk_after_it_names_no_run_here_as_in_the_gate(self):
        """From the second review: the loop's own reading of a trailer took `...000Zjunk` as a
        run where the gate refuses it. One definition, `repo.run_stamp`, for both."""
        write(self.root, "test_repo.py", TEST_GREEN_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", f"b\n\nBuilt-By: factory at v0.1, run {STAMP}junk")
        found = loop.gather(self.root)
        self.assertTrue(found.problems)  # the gate refuses it as a build that names no run
        self.assertEqual(found.seeds[0].builds, ())

    def test_two_branches_at_a_detached_head_are_no_branch_and_say_so(self):
        write(self.root, "test_repo.py", TEST_RED_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("red")
        git(self.root, "branch", "other")
        git(self.root, "switch", "-q", "--detach")
        found = loop.gather(self.root)
        self.assertEqual((found.branch, found.attached), (None, False))
        self.assertTrue(any(line.startswith("branch:") and "other" in line for line in found.unknown), found.unknown)

    def test_a_method_naming_its_own_seed_is_that_seeds_and_not_its_classs(self):
        """Found live: a class whose docstring names one seed holds a method whose docstring names
        another, and running the class for the first seed ran the second's method and coloured
        the first red. A test's seed is the innermost docstring that names one."""
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        write(self.root, "docs/seeds/c.md", SEED_B.replace("status: spec", "status: building"))
        write(
            self.root,
            "test_repo.py",
            'import unittest\n\n\nclass RepoTest(unittest.TestCase):\n    """seed: b. The next thing holds."""\n\n'
            "    def test_b(self):\n        self.assertEqual(2, 2)\n\n"
            '    def test_c(self):\n        """seed: c. Not yet."""\n        self.assertEqual(1, 2)\n',
        )
        self.commit("a class naming b with a method naming c")
        found = loop.gather(self.root)
        by_name = {s.name: s for s in found.seeds}
        self.assertEqual(by_name["b"].tests, ("test_repo.RepoTest.test_b",))  # the class's methods, not the class
        self.assertEqual(by_name["b"].colour, "green")
        self.assertEqual(by_name["c"].tests, ("test_repo.RepoTest.test_c",))
        self.assertEqual(by_name["c"].colour, "red")

    def test_a_done_or_rejected_seeds_tests_are_not_run(self):
        """From the second review: a done seed's tests were run for a colour no row reads, up to
        the run's timeout each."""
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: done"))
        write(self.root, "test_repo.py", TEST_GREEN_B)
        write(self.root, "docs/seeds/c.md", SEED_B.replace("status: spec", "status: open").replace("## Goal", "## Idea"))
        self.commit("b done, c open")
        calls: list[list[str]] = []
        real = subprocess.run

        def recording(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", recording):
            found = loop.gather(self.root)
        self.assertFalse([argv for argv in calls if "unittest" in argv], calls)
        self.assertEqual(loop.next_step(found).text, "write the Goal of c; status spec")

    def test_the_loop_reads_through_vault_and_repo_and_nothing_else(self):
        """From the first build's review: `loop.py` imported `ast` and `subprocess`, read files
        and ran nine raw git commands of its own -- the readers the split gave a home to."""
        source = Path(loop.__file__).read_text()
        for token in ("import ast", "ast.", "subprocess", "read_text(", "repo.git(", ".glob(", "open("):
            self.assertNotIn(token, source, token)

    def test_gate_next_prints_the_step_first_and_writes_nothing(self):
        before = sorted(p.name for p in self.root.iterdir())
        code, out, err = run(self.root, "next")
        self.assertEqual((code, err), (0, ""), out)
        self.assertTrue(out.startswith("next: write red tests naming seed: b"), out)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)
        self.assertIn("next", __import__("gate").USAGE)
        code, _, err = run(self.root, "next", "extra")
        self.assertEqual(code, 2)
        self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
