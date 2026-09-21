"""The loop, derived: what `loop.py` gives `gate.py next`.

    uv run python -m unittest test_loop -v

Written from docs/seeds/the-step-nobody-noticed.md before the code. The rules are held over a
`Facts` built by hand for every row, in the table's order; `gather` is held over the gate tests'
own fixture, advanced step by step as the loop would advance it.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gate import (
    AGENTS,
    IDENTITY,
    REVIEW,
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


def seed(**over) -> loop.SeedFacts:
    """A seed of the version in flight, at `building` with red tests unless said otherwise."""
    base = dict(
        name="b",
        status="building",
        has_goal=True,
        tests=("test_repo.RepoTest.test_b",),
        colour="red",
        builds=(),
        reviewed=None,
    )
    base.update(over)
    return loop.SeedFacts(**base)


def facts(**over) -> loop.Facts:
    """Facts with nothing to do before the seeds: a version in flight, a clean tree, no tag at the
    head, nothing unknown; overridden by keyword."""
    base = dict(
        root=ROOT,
        problems=(),
        tags=frozenset({"v0.1"}),
        highest="v0.1",
        head="abc1234abc1234abc1234abc1234abc1234abc12",
        branch="v0.2",
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
    top to bottom; every rule a pure function of `Facts`."""

    def test_the_rules_are_an_ordered_table_and_a_step_has_a_name_and_a_text(self):
        self.assertIsInstance(loop.RULES, tuple)
        self.assertGreaterEqual(len(loop.RULES), 12)
        for rule in loop.RULES:
            self.assertTrue(rule.name)
            self.assertTrue(callable(rule.applies))
            self.assertTrue(callable(rule.step))
        found = loop.next_step(facts(in_flight=None))
        self.assertTrue(found.name)
        self.assertTrue(found.text.startswith("open a version:"))

    def test_1_a_problem_of_the_gate_comes_before_everything(self):
        text = step(problems=("docs/seeds/a.md: value 9 is not 1 to 5",), in_flight=None)
        self.assertEqual(text, "fix: docs/seeds/a.md: value 9 is not 1 to 5")

    def test_2_after_a_tag_the_acts_that_follow_it_in_order(self):
        after = dict(tags=frozenset({"v0.1", "v0.2"}), highest="v0.2", in_flight=None, after_tag=True)
        self.assertEqual(step(**after, changelog_current=False), "commit CHANGELOG.md")
        self.assertEqual(
            step(**after, changelog_current=True, main_at_head=False),
            "fast-forward main: git merge --ff-only heads/v0.2",
        )
        self.assertEqual(
            step(**after, changelog_current=True, main_at_head=True, mirror_at_head=False),
            "push: git push origin main --tags",
        )
        self.assertEqual(
            step(**after, changelog_current=True, main_at_head=True, mirror_at_head=True, instance_version="0.1"),
            "install: uv tool install --reinstall dist/factory-0.2-py3-none-any.whl",
        )
        self.assertEqual(
            step(**after, changelog_current=True, main_at_head=True, mirror_at_head=True, instance_version="0.2"),
            "v0.2 is out: open the next version",
        )

    def test_an_unknown_fact_skips_its_row_and_is_said_after_the_step(self):
        after = dict(tags=frozenset({"v0.1", "v0.2"}), highest="v0.2", in_flight=None, after_tag=True)
        unknown = ("mirror: git ls-remote origin main failed: no such remote",)
        found = facts(**after, changelog_current=True, main_at_head=True, mirror_at_head=None,
                      instance_version="0.2", unknown=unknown)  # fmt: skip
        self.assertEqual(loop.next_step(found).text, "v0.2 is out: open the next version")
        text = loop.render(found)
        self.assertTrue(text.startswith("next: v0.2 is out: open the next version\n"), text)
        self.assertIn("unknown: mirror: git ls-remote origin main failed: no such remote", text)

    def test_3_no_version_in_flight(self):
        self.assertTrue(step(in_flight=None).startswith("open a version:"))

    def test_4_a_version_with_no_seed(self):
        self.assertEqual(step(seeds=()), "promote a seed to v0.2")

    def test_5_a_seed_at_open(self):
        self.assertEqual(step(seeds=(seed(status="open", has_goal=False, tests=(), colour="none"),)),
                         "write the Goal of b; status spec")  # fmt: skip

    def test_6_a_seed_at_spec_named_by_no_test(self):
        self.assertEqual(step(seeds=(seed(status="spec", tests=(), colour="none"),)),
                         "write red tests naming seed: b; commit them; status building")  # fmt: skip

    def test_7_a_seed_named_by_tests_but_not_building(self):
        self.assertEqual(step(seeds=(seed(status="spec"),)), "set b to building: its tests name it")

    def test_8_red_tests_mean_a_build_and_a_detach_when_the_branch_is_checked_out(self):
        self.assertEqual(
            step(seeds=(seed(),)),
            f"build b: factory-build {ROOT} v0.2 docs/seeds/b.md -- detach first: git switch --detach",
        )
        self.assertEqual(step(seeds=(seed(),), branch=None), f"build b: factory-build {ROOT} v0.2 docs/seeds/b.md")

    def test_9_green_with_no_build(self):
        self.assertTrue(step(seeds=(seed(colour="green"),)).startswith("b is green with no build:"))

    def test_10_green_and_built_but_not_reviewed(self):
        built = (loop.Build("abc1234", STAMP),)
        self.assertTrue(
            step(seeds=(seed(colour="green", builds=built, reviewed=False),)).startswith(f"review build {STAMP} of b:")
        )

    def test_11_green_built_and_reviewed(self):
        built = (loop.Build("abc1234", STAMP),)
        self.assertEqual(step(seeds=(seed(colour="green", builds=built, reviewed=True),)), "set b to done")

    def test_12_every_seed_done_means_the_release_and_its_preconditions_first(self):
        done = (seed(status="done", colour="green"),)
        self.assertEqual(step(seeds=done, agents_changed=False), "revise AGENTS.md: unchanged since v0.1")
        self.assertEqual(step(seeds=done, bullets=False), "write a ## Changelog bullet in docs/versions/v0.2.md")
        self.assertEqual(step(seeds=done, dirty=("x.txt", "y.txt")), "commit: x.txt y.txt")
        self.assertEqual(step(seeds=done), "release: uv run gate.py release v0.2")
        rejected = (seed(status="rejected", tests=(), colour="none"),)
        self.assertEqual(step(seeds=rejected), "release: uv run gate.py release v0.2")

    def test_the_first_seed_with_something_to_do_is_the_one_stepped(self):
        two = (seed(name="a", status="done", colour="green"), seed(name="b"))
        self.assertTrue(step(seeds=two).startswith("build b:"))

    def test_facts_are_frozen(self):
        import dataclasses

        with self.assertRaises(dataclasses.FrozenInstanceError):
            facts().head = "elsewhere"


class GatherTest(unittest.TestCase):
    """seed: the-step-nobody-noticed. `gather(root)` reads every fact once through vault and
    repo, runs a seed's own tests for their colour, and answers `unknown` rather than guessing;
    the fixture is advanced as the loop would advance it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, IDENTITY))
        self.root = make_repo(Path(self.tmp.name))
        self.shim_uv("factory v0.1\n- factory-build\n")

    def shim_uv(self, says: str) -> None:
        """A `uv` first on PATH whose `tool list` says what the instance is."""
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        shim = bin_dir / "uv"
        shim.write_text("#!/bin/sh\n" f"printf '%s' '{says}'\n")
        shim.chmod(0o755)
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}))

    def commit(self, message: str = "more") -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def test_the_fixture_is_read_as_it_is(self):
        found = loop.gather(self.root)
        self.assertEqual(found.root, self.root)
        self.assertEqual(found.problems, ())
        self.assertEqual((found.tags, found.highest), (frozenset({"v0.1"}), "v0.1"))
        self.assertEqual(found.head, git(self.root, "rev-parse", "HEAD").strip())
        self.assertEqual(found.branch, git(self.root, "branch", "--show-current").strip())
        self.assertEqual(found.in_flight, "v0.2")
        self.assertEqual([s.name for s in found.seeds], ["b"])
        b = found.seeds[0]
        self.assertEqual((b.status, b.has_goal, b.tests, b.colour, b.builds, b.reviewed), ("spec", True, (), "none", (), None))
        self.assertEqual((found.agents_changed, found.bullets, found.dirty), (False, True, ()))
        self.assertFalse(found.after_tag)
        self.assertEqual(loop.next_step(found).text, "write red tests naming seed: b; commit them; status building")

    def test_the_loop_advances_with_the_fixture(self):
        write(self.root, "test_repo.py", TEST_RED_B)
        write(self.root, "docs/seeds/b.md", SEED_B.replace("status: spec", "status: building"))
        self.commit("red")
        found = loop.gather(self.root)
        self.assertEqual(found.seeds[0].tests, ("test_repo.RepoTest.test_b",))
        self.assertEqual(found.seeds[0].colour, "red")
        self.assertTrue(loop.next_step(found).text.startswith("build b: factory-build"))

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

    def test_after_the_tag_the_acts_are_read_and_the_mirror_is_unknown_here(self):
        git(self.root, "tag", "-a", "v0.2", "-m", "the next")
        found = loop.gather(self.root)
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
        main_here = git(self.root, "branch", "--show-current").strip() == "main"
        expected = "install: uv tool install --reinstall dist/factory-0.2-py3-none-any.whl"
        if not main_here:
            expected = "fast-forward main: git merge --ff-only heads/v0.2"
        self.assertEqual(loop.next_step(found).text, expected)

    def test_a_problem_of_the_gate_is_the_step_and_a_tree_that_is_no_checkout_still_answers(self):
        write(self.root, "docs/seeds/a.md", open(self.root / "docs" / "seeds" / "a.md").read().replace("value: 3", "value: 9"))
        found = loop.gather(self.root)
        self.assertTrue(found.problems)
        self.assertTrue(loop.next_step(found).text.startswith("fix: docs/seeds/a.md"))

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
