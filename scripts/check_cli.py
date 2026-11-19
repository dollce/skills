"""Compare the development catalog with a clean project installation by the CLI."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from spl.scripts.check_release import CheckError, check_local_links

from .dev_links import public_skills, ROOT


def stage_worktree(root: Path, staged: Path) -> None:
    # Include edits and new files awaiting commit. Ignored runtime artifacts
    # (e.g. __pycache__) aren't part of the GitHub distribution.
    files = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    for raw in files.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        source = root / relative
        if source.parent.resolve() != source.parent or not os.path.lexists(source):
            continue  # A tracked path was removed or a parent was replaced.
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)


def check_installation(expected: dict[str, Path], directory: Path) -> None:
    installed = {p.name: p for p in directory.iterdir()}
    if installed.keys() != expected.keys():
        raise ValueError(f"CLI installed {sorted(installed)}; dev-link would link {sorted(expected)}")
    for name, source in expected.items():
        result = subprocess.run(["diff", "-qr", source, installed[name]], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise ValueError(f"CLI installation differs for {name}:\n{result.stdout.strip()}")
        check_local_links(installed[name])


def main() -> None:
    expected = public_skills(ROOT)
    with tempfile.TemporaryDirectory(prefix="skills-cli-check-") as temp:
        staged = Path(temp) / "source"
        stage_worktree(ROOT, staged)
        project = Path(temp) / "project"
        project.mkdir()
        subprocess.run(
            ["npx", "--yes", "skills@1.7.6", "add", str(staged),
             "--skill", "*", "--agent", "codex", "-y"],
            cwd=project, env={**os.environ, "DISABLE_TELEMETRY": "1"}, check=True,
        )
        sources = {name: staged / path.relative_to(ROOT) for name, path in expected.items()}
        check_installation(sources, project / ".agents/skills")
    print("PASS: CLI installation matches the development catalog and skill files")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, CheckError) as exc:
        sys.exit(f"error: {exc}")
