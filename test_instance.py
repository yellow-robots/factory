"""The instance's configuration: where its records go, where it works, and the roles it runs."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import instance


class RolesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.config = self.base / "instance.toml"
        self.deepseek = self.base / "deepseek.key"
        self.glm = self.base / "glm.key"
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(self.config)}))

    def both_roles(self, *, builder_key=None, reviewer_key=None) -> None:
        """The configuration this host runs: a store, a working directory and two roles."""
        self.config.write_text(
            f'records = "{self.base / "records"}"\n'
            f'work = "{self.base / "work"}"\n'
            "\n[roles.builder]\n"
            'model = "deepseek-flash"\n'
            f'key = "{builder_key or self.deepseek}"\n'
            "\n[roles.reviewer]\n"
            'model = "glm-5.3-flash"\n'
            f'key = "{reviewer_key or self.glm}"\n'
            'base_url = "https://example.invalid/v1"\n',
            encoding="utf-8",
        )

    def refused(self, body: str) -> str:
        """The message of the ValueError a configuration of this body raises."""
        self.config.write_text(body, encoding="utf-8")
        with self.assertRaises(ValueError) as raised:
            instance.role("builder")
        return str(raised.exception)

    def test_a_role_answers_with_its_model_the_path_of_its_key_and_its_base_url(self):
        """seed: keys-of-the-instance. A role is what the instance runs a session as: the model, the
        file its key is read from as an absolute path, and the base URL of a model served somewhere
        other than the provider used by default, which is None when the role does not name one."""
        self.both_roles()
        builder = instance.role("builder")
        self.assertEqual(builder.model, "deepseek-flash")
        self.assertEqual(builder.key, self.deepseek)
        self.assertIsNone(builder.base_url)
        reviewer = instance.role("reviewer")
        self.assertEqual(reviewer.model, "glm-5.3-flash")
        self.assertEqual(reviewer.key, self.glm)
        self.assertEqual(reviewer.base_url, "https://example.invalid/v1")

    def test_the_roles_are_read_without_reading_any_key(self):
        """seed: keys-of-the-instance. `instance.py` answers with a key's place and never with its
        value, so the roles read when no key file exists at all; reading a key is the caller's, and
        the value lives in as few places as it can."""
        self.both_roles()
        self.assertFalse(self.deepseek.exists())
        self.assertFalse(self.glm.exists())
        self.assertEqual(instance.role("builder").key, self.deepseek)
        self.assertEqual(sorted(instance.key_paths()), sorted([self.deepseek, self.glm]))

    def test_every_key_the_configuration_names_is_answered(self):
        """seed: keys-of-the-instance. The search that keeps a key out of a record searches for every
        key the instance holds rather than the one a run was given, so the configuration answers
        with all of them, each as an absolute path and each named once."""
        self.both_roles(reviewer_key=self.deepseek)  # two roles, one key file between them
        self.assertEqual(instance.key_paths(), [self.deepseek])

    def test_a_role_the_configuration_does_not_hold_is_refused_naming_it(self):
        """seed: keys-of-the-instance. Asking for a role that is not configured is the configuration's
        fault and says so, naming the file and the role, as a missing `records` does."""
        self.both_roles()
        with self.assertRaises(ValueError) as raised:
            instance.role("analyst")
        self.assertIn(str(self.config), str(raised.exception))
        self.assertIn("analyst", str(raised.exception))

    def test_a_configuration_with_no_roles_is_refused_naming_the_file(self):
        """seed: keys-of-the-instance. A configuration that names no roles cannot run one, and the
        refusal names the file, in the shape `record_store` and `work_dir` already use."""
        message = self.refused(f'records = "{self.base / "records"}"\nwork = "{self.base / "work"}"\n')
        self.assertIn(str(self.config), message)
        self.assertIn("roles", message)

    def test_roles_that_are_not_a_table_of_tables_are_refused(self):
        """seed: keys-of-the-instance. `roles` is a table of roles and each role is a table; anything
        else names the fault rather than raising out of the reader."""
        flat = self.refused(f'records = "{self.base}"\nwork = "{self.base}"\nroles = "builder"\n')
        self.assertIn("roles", flat)
        entry = self.refused(f'records = "{self.base}"\nwork = "{self.base}"\n\n[roles]\nbuilder = "deepseek-flash"\n')
        self.assertIn("builder", entry)

    def test_a_role_without_a_model_or_without_a_key_is_refused_naming_which(self):
        """seed: keys-of-the-instance. A role runs a model and reads a key; a role missing either is
        refused naming the role and which of the two is absent, so the fault is not hunted for."""
        head = f'records = "{self.base}"\nwork = "{self.base}"\n\n[roles.builder]\n'
        no_model = self.refused(head + f'key = "{self.deepseek}"\n')
        self.assertIn("builder", no_model)
        self.assertIn("model", no_model)
        no_key = self.refused(head + 'model = "deepseek-flash"\n')
        self.assertIn("builder", no_key)
        self.assertIn("key", no_key)

    def test_a_model_or_a_key_of_the_wrong_kind_is_refused(self):
        """seed: keys-of-the-instance. A model is a string and a key is a string naming an absolute
        path, because a relative key would be read from wherever the run happened to start."""
        head = f'records = "{self.base}"\nwork = "{self.base}"\n\n[roles.builder]\n'
        not_a_string = self.refused(head + f'model = 3\nkey = "{self.deepseek}"\n')
        self.assertIn("model", not_a_string)
        relative = self.refused(head + 'model = "deepseek-flash"\nkey = "deepseek.key"\n')
        self.assertIn("key", relative)
        self.assertIn("deepseek.key", relative)
