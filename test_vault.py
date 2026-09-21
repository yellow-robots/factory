"""The vault's reader, apart: what `vault.py` gives the gate and the loop.

    uv run python -m unittest test_vault -v

Written from docs/seeds/the-gate-in-three.md before the code, over the gate tests' own fixtures:
a small vault in a git repository in a temporary directory. Nothing here touches the factory's
own docs/.
"""

import dataclasses
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gate import BASE, IDENTITY, TEMPLATE_REVIEW, git, make_repo, write

import vault


class VaultTest(unittest.TestCase):
    """seed: the-gate-in-three. `Vault.read(root)` asks the repository once what `docs/` holds
    and reads every note once; a `Note` carries its path, its fields, its body and, when it could
    not be read, the error, so nothing downstream parses twice or mistakes a failure for an empty
    note."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, IDENTITY))
        self.root = make_repo(Path(self.tmp.name))
        self.vault = vault.Vault.read(self.root)

    def note(self, rel: str, root: Path | None = None) -> vault.Note:
        notes = vault.Vault.read(root or self.root).notes()
        return next(n for n in notes if n.rel == rel)

    def test_every_note_is_read_once_with_its_path_its_fields_and_its_body(self):
        notes = self.vault.notes()
        rels = [n.rel for n in notes]
        self.assertEqual(rels, sorted(rels))
        self.assertEqual(
            set(rels),
            {
                "docs/seeds/a.md",
                "docs/seeds/b.md",
                "docs/seeds/d.md",
                "docs/versions/v0.1.md",
                "docs/versions/v0.2.md",
            },
        )
        a = next(n for n in notes if n.rel == "docs/seeds/a.md")
        self.assertEqual(a.path, self.root / "docs" / "seeds" / "a.md")
        self.assertEqual(a.fm["type"], "seed")
        self.assertEqual(a.kind, "seed")
        self.assertIn("## Idea", a.body)
        self.assertEqual(a.error, "")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            a.rel = "elsewhere"

    def test_a_note_without_frontmatter_has_no_fields_and_no_kind(self):
        write(self.root, "docs/seeds/c.md", "no frontmatter at all\n")
        c = self.note("docs/seeds/c.md")
        self.assertIsNone(c.fm)
        self.assertEqual(c.kind, "")
        self.assertEqual(c.body, "no frontmatter at all\n")

    def test_a_note_that_cannot_be_read_says_so_and_is_not_an_empty_note(self):
        path = self.root / "docs" / "seeds" / "a.md"
        path.chmod(0)
        self.addCleanup(path.chmod, 0o644)
        a = self.note("docs/seeds/a.md")
        self.assertTrue(a.error)
        self.assertIsNone(a.fm)
        self.assertEqual(a.body, "")

    def test_templates_are_no_notes_and_an_ignored_note_is_no_note(self):
        write(self.root, ".gitignore", "__pycache__/\ndist/\ndocs/scratchpad/\n")
        write(self.root, "docs/scratchpad/notes.md", "no frontmatter at all\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "a scratchpad git ignores")
        rels = {n.rel for n in vault.Vault.read(self.root).notes()}
        self.assertNotIn("docs/templates/seed.md", rels)
        self.assertNotIn("docs/scratchpad/notes.md", rels)
        self.assertIn("docs/seeds/a.md", rels)

    def test_the_vault_knows_its_root_and_what_it_holds(self):
        self.assertEqual(self.vault.root, self.root)
        self.assertEqual(self.vault.docs, self.root / "docs")
        self.assertTrue(self.vault.holds(self.root / "docs" / "seeds" / "a.md"))
        self.assertFalse(self.vault.holds(Path("/etc/passwd")))  # outside the root, whatever git says

    def test_a_directory_that_is_no_checkout_is_read_whole(self):
        copy = Path(self.tmp.name) / "copy"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        write(copy, "docs/scratchpad/notes.md", "no frontmatter at all\n")
        rels = {n.rel for n in vault.Vault.read(copy).notes()}
        self.assertIn("docs/scratchpad/notes.md", rels)
        self.assertIn("docs/seeds/a.md", rels)

    def test_a_wikilink_target_resolves_by_path_by_name_or_to_the_base(self):
        self.assertTrue(self.vault.resolves("a"))
        self.assertTrue(self.vault.resolves("seeds/a.md"))
        self.assertTrue(self.vault.resolves("backlog.base"))
        self.assertFalse(self.vault.resolves("nowhere"))
        self.assertFalse(self.vault.resolves(""))

    def test_a_wikilink_out_of_the_vault_resolves_to_nothing(self):
        """seed: wikilinks-inside-the-vault. Obsidian cannot follow a link out of the vault: a
        target that leaves `docs/` by an absolute path or by `..` resolves to nothing, whatever
        file that path reaches and whether git tracks it."""
        self.assertTrue((self.root / "AGENTS.md").is_file())  # reachable by .., tracked, not the vault's
        self.assertFalse(self.vault.resolves("../AGENTS.md"))
        self.assertFalse(self.vault.resolves("../AGENTS"))
        self.assertFalse(self.vault.resolves("/etc/hostname"))
        self.assertTrue(self.vault.resolves("seeds/../seeds/a.md"))  # inside, however spelled

    def test_the_fields_a_kind_needs_are_read_from_its_template_and_written_nowhere_else(self):
        docs = self.root / "docs"
        write(self.root, "docs/templates/review.md", TEMPLATE_REVIEW)  # the fixture ships no review template
        self.assertEqual(
            vault.template_fields(docs, "seed"),
            {"created", "type", "status", "summary", "value", "effort", "version"},
        )
        self.assertEqual(vault.template_fields(docs, "review"), {"created", "type", "runs", "reviewer"})
        import gate

        for module in (vault, gate):
            self.assertFalse(hasattr(module, "SEED_FIELDS"), module.__name__)
            self.assertFalse(hasattr(module, "REVIEW_FIELDS"), module.__name__)


class TextTest(unittest.TestCase):
    """seed: the-gate-in-three. The readers of a note's text, moved as they are: frontmatter, the
    title, the first paragraph, the changelog bullets, a review's findings and their prose, and
    the base's names."""

    def test_frontmatter_is_the_block_between_the_dashes(self):
        fm, body = vault.frontmatter("---\ntype: seed\nvalue: 3\n---\nthe body\n")
        self.assertEqual(fm, {"type": "seed", "value": "3"})
        self.assertEqual(body, "the body")
        self.assertEqual(vault.frontmatter("no block here\n")[0], None)

    def test_title_first_paragraph_and_changelog_bullets(self):
        body = (
            "\n# v0.2: the next\n\nThe next version does the next thing.\n\n"
            "![[backlog.base#Specs]]\n\n## Changelog\n\n- The next thing, built.\n- [[a]] is no bullet\n"
        )
        self.assertEqual(vault.title(body), "v0.2: the next")
        self.assertEqual(vault.first_paragraph(body), "The next version does the next thing.")
        self.assertEqual(vault.changelog_bullets(body), ["- The next thing, built."])

    def test_the_findings_of_a_review_and_the_prose_of_a_finding(self):
        text = (
            "## Findings\n\n### One\n\nseverity: defect\n```\n### not a heading\n```\n\n"
            "### Two\n\n    indented code\nverified: yes\n\n## After\n\nnot a finding\n"
        )
        findings = vault.review_findings(text)
        self.assertEqual([title for title, _ in findings], ["One", "Two"])
        self.assertIn("### not a heading", findings[0][1])  # a fence belongs whole
        self.assertEqual([line for line in vault.prose_lines(findings[0][1]) if line], ["severity: defect"])
        self.assertEqual([line for line in vault.prose_lines(findings[1][1]) if line], ["verified: yes"])

    def test_a_base_is_read_into_the_names_it_uses(self):
        named = vault.base_named(BASE)
        self.assertTrue(named)
        self.assertTrue({kind for kind, _ in named} <= {"name", "expr"})
        self.assertIn("status", " ".join(text for _, text in named))


if __name__ == "__main__":
    unittest.main()
