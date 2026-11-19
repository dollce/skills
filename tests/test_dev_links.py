import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import dev_links


class DevLinksTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.root = base / "checkout"
        self.user = base / "user"
        self.project_links = self.root / ".agents/skills"
        self.user_links = self.user / ".agents/skills"
        self.group = self.root / "group"
        self.group.mkdir(parents=True)
        self.config = self.root / "skills.sh.json"
        self.config.write_text(json.dumps({"paths": ["./group"]}))
        for name in ("first", "second"):
            skill = self.group / name
            skill.mkdir()
            (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n")

    def command(self, *args):
        output = io.StringIO()
        with patch.object(dev_links, "ROOT", self.root), patch.object(Path, "home", return_value=self.user), \
             patch.object(sys, "argv", ["dev_links.py", *args]), contextlib.redirect_stdout(output):
            dev_links.main()
        return output.getvalue()

    def test_edits_are_live_and_cleanup_survives_catalog_changes(self):
        self.command("link")
        self.command("link")
        self.command("link", "--global")
        source = self.group / "first"
        (source / "reference.txt").write_text("edited after linking")
        for scope in (self.project_links, self.user_links):
            self.assertEqual((scope / "first").readlink(), source)
            self.assertEqual((scope / "first/reference.txt").read_text(), "edited after linking")
        source.rename(self.group / "renamed")
        self.assertIn("stale", self.command("status"))
        self.config.unlink()
        self.command("unlink")
        self.command("unlink")
        for scope in (self.project_links, self.user_links):
            self.assertEqual(list(scope.iterdir()), [])
        self.assertEqual((self.group / "renamed/reference.txt").read_text(), "edited after linking")

    def test_conflict_prevents_partial_batch_and_preserves_foreign_entries(self):
        self.project_links.mkdir(parents=True)
        conflict = self.project_links / "second"
        for kind in ("installed", "manual link", "broken link"):
            with self.subTest(kind=kind):
                if kind == "installed":
                    conflict.mkdir()
                    (conflict / "SKILL.md").write_text("published")
                else:
                    target = self.group / ("second" if kind == "manual link" else "missing")
                    conflict.symlink_to(target)
                with self.assertRaisesRegex(ValueError, "Already occupied"):
                    self.command("link")
                self.assertFalse(os.path.lexists(self.project_links / "first"))
                self.command("unlink")
                if kind == "installed":
                    self.assertEqual((conflict / "SKILL.md").read_text(), "published")
                    (conflict / "SKILL.md").unlink()
                    conflict.rmdir()
                else:
                    self.assertEqual(conflict.readlink(), target)
                    conflict.unlink()

    def test_replacements_and_other_checkouts_are_preserved(self):
        self.command("link", "--global")
        foreign = self.user_links / "first"
        source = foreign.readlink()
        foreign.unlink()
        foreign.symlink_to(source)
        other = self.root.parent / "other-checkout"
        dev_links.manage("unlink", other, self.user / ".agents", {})
        self.assertTrue((self.user_links / "second").is_symlink())
        self.assertIn("kept", self.command("unlink"))
        self.assertEqual(foreign.readlink(), source)
        self.assertFalse(os.path.lexists(self.user_links / "second"))

    def test_failed_link_rolls_back_only_new_links(self):
        self.command("link")
        for name in ("third", "fourth"):
            skill = self.group / name
            skill.mkdir()
            (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n")
        publish = os.link

        def fail_on_third(receipt, dest, **kwargs):
            if dest.name == "third":
                raise OSError("filesystem refused the link")
            return publish(receipt, dest, **kwargs)

        with patch.object(os, "link", side_effect=fail_on_third), self.assertRaises(OSError):
            self.command("link")
        self.assertEqual(sorted(p.name for p in self.project_links.iterdir()), ["first", "second"])
        self.command("link")
        self.assertTrue((self.project_links / "third").is_symlink())

    def test_catalog_rejects_duplicate_names_and_external_sources(self):
        extra = self.root / "extra"
        extra.mkdir()
        self.config.write_text(json.dumps({"paths": ["./group", "./extra"]}))
        duplicate = extra / "first"
        duplicate.mkdir()
        (duplicate / "SKILL.md").touch()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.command("link")
        self.config.write_text(json.dumps({"paths": ["./../external"]}))
        with self.assertRaisesRegex(ValueError, "Invalid collection"):
            self.command("link")
        self.assertFalse(self.project_links.exists())
