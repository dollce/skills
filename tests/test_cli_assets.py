from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.check_cli import check_installation, stage_worktree
from spl.scripts.check_release import CheckError


class CliAssetTest(unittest.TestCase):
    def test_matching_skill_md_does_not_hide_missing_or_changed_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            refs = source / "references"
            refs.mkdir(parents=True)
            (source / "SKILL.md").write_text("Read [metadata](references/metadata.json).")
            (refs / "metadata.json").write_text('{"version": 2}')
            installed = Path(temp) / "installed"
            copy = installed / "example"
            shutil.copytree(source, copy)
            asset = copy / "references/metadata.json"
            asset.unlink()  # skills@1.7.6 excludes this filename during install.
            with self.assertRaisesRegex(ValueError, "metadata.json"):
                check_installation({"example": source}, installed)
            asset.write_text('{"version": 1}')
            with self.assertRaisesRegex(ValueError, "metadata.json"):
                check_installation({"example": source}, installed)
            shutil.copyfile(refs / "metadata.json", asset)
            check_installation({"example": source}, installed)
            # An ignored local reference can be absent from both the snapshot
            # and the installation. The installed Markdown must still resolve it.
            (refs / "metadata.json").unlink()
            asset.unlink()
            with self.assertRaisesRegex(CheckError, "Broken local link.*metadata.json"):
                check_installation({"example": source}, installed)

    def test_cli_snapshot_uses_working_files_that_git_can_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "repo"
            staged = root.parent / "snapshot"
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("*.pyc\n")
            (root / "updated").write_text("old")
            (root / "deleted").touch()
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            (root / "updated").write_text("current")
            (root / "deleted").unlink()
            (root / "new").write_text("new asset")
            (root / "cache.pyc").touch()
            stage_worktree(root, staged)
            self.assertEqual(sorted(p.name for p in staged.iterdir()), [".gitignore", "new", "updated"])
            self.assertEqual((staged / "updated").read_text(), "current")
