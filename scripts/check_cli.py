"""Compare the development catalog with a clean project installation by the CLI."""

import os
from pathlib import Path
import subprocess
import tempfile

from dev_links import public_skills, ROOT


def main():
    expected = public_skills(ROOT)
    with tempfile.TemporaryDirectory(prefix="skills-cli-check-") as project:
        subprocess.run(
            ["npx", "--yes", "skills@1.7.6", "add", str(ROOT),
             "--skill", "*", "--agent", "codex", "-y"],
            cwd=project, env={**os.environ, "DISABLE_TELEMETRY": "1"}, check=True,
        )
        installed = {p.name: p for p in (Path(project) / ".agents/skills").iterdir()}
        if installed.keys() != expected.keys():
            raise SystemExit(f"CLI installed {sorted(installed)}; dev-link would link {sorted(expected)}")
        for name, source in expected.items():
            if (installed[name] / "SKILL.md").read_bytes() != (source / "SKILL.md").read_bytes():
                raise SystemExit(f"CLI and development SKILL.md differ: {name}")
    print("PASS: CLI installation matches the development catalog:", ", ".join(sorted(expected)))


if __name__ == "__main__":
    main()
