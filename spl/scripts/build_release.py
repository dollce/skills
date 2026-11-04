#!/usr/bin/env python3
"""Build deterministic local preview and handoff archives (no external tools)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SKILL = Path("splunk-spl-writer")
HANDOFF_FILES = (
    Path("README.md"),
    Path("MAINTAINER.md"),
    Path("LICENSE"),
    Path("notes/splunk-search-cost-optimization.md"),
    Path("scripts/build_release.py"),
    Path("scripts/check_release.py"),
    Path("requirements-dev.txt"),
    Path(".gitignore"),
)
REQUIRED_SKILL_FILES = (
    SKILL / "SKILL.md",
    SKILL / "agents/openai.yaml",
    SKILL / "references/field-extraction.md",
    SKILL / "LICENSE",
)
EXCLUDED_NAMES = {
    ".git", ".DS_Store", "dist", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".cache", ".venv", "venv",
}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_NAMES = (
    "splunk-spl-writer-preview.zip",
    "splunk-spl-writer-handoff.zip",
)


class BuildError(Exception):
    """A missing or unsafe input prevents release packaging."""


def checked_path(relative: Path, *, directory: bool = False) -> Path:
    """Reject symbolic links in both an input and its parent components."""
    path = ROOT
    for component in relative.parts:
        path = path / component
        if path.is_symlink():
            raise BuildError(f"Symbolic links are not allowed: {path.relative_to(ROOT)}")
    if directory:
        if not path.is_dir():
            raise BuildError(f"Required directory is missing or invalid: {relative}")
    elif not path.is_file():
        raise BuildError(f"Required file is missing or invalid: {relative}")
    return path


def skill_files() -> list[Path]:
    """Include future skill assets while omitting generated local artifacts."""
    checked_path(SKILL, directory=True)
    for relative in REQUIRED_SKILL_FILES:
        checked_path(relative)
    files = []

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(ROOT)
            if path.is_symlink():
                raise BuildError(f"Symbolic links are not allowed: {relative}")
            if path.name in EXCLUDED_NAMES or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_dir():
                visit(path)
            elif path.is_file():
                files.append(relative)
            else:
                raise BuildError(f"Only regular files and directories are allowed: {relative}")

    visit(ROOT / SKILL)
    return sorted(files, key=lambda path: path.as_posix())


def write_archive(destination: Path, entries: dict[str, bytes]) -> None:
    # Stored entries avoid compression-library differences across computers.
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        directories = set()
        for name in entries:
            for parent in Path(name).parents:
                if parent.as_posix() != ".":
                    directories.add(parent.as_posix() + "/")
        for name in sorted(set(entries) | directories):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.create_system = 3
            if name.endswith("/"):
                info.external_attr = (stat.S_IFDIR | 0o755) << 16 | 0x10
                archive.writestr(info, b"")
            else:
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, entries[name])


def build() -> None:
    for relative in HANDOFF_FILES:
        checked_path(relative)
    selected_skill_files = skill_files()
    # Read inputs once so both archives carry the same skill snapshot.
    payloads = {
        relative.as_posix(): checked_path(relative).read_bytes()
        for relative in (*HANDOFF_FILES, *selected_skill_files)
    }
    preview = {
        relative.as_posix(): payloads[relative.as_posix()]
        for relative in selected_skill_files
    }
    handoff = {
        f"spl/{name}": data
        for name, data in payloads.items()
    }

    output = ROOT / "dist"
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise BuildError("Output path must be a real directory: dist")
    output.mkdir(exist_ok=True)
    for name in (*ARCHIVE_NAMES, "SHA256SUMS"):
        destination = output / name
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise BuildError(f"Output path must be a regular file: dist/{name}")

    with tempfile.TemporaryDirectory(prefix=".release-", dir=output) as temporary:
        staging = Path(temporary)
        write_archive(staging / ARCHIVE_NAMES[0], preview)
        write_archive(staging / ARCHIVE_NAMES[1], handoff)
        checksums = "".join(
            f"{hashlib.sha256((staging / name).read_bytes()).hexdigest()}  {name}\n"
            for name in ARCHIVE_NAMES
        )
        (staging / "SHA256SUMS").write_bytes(checksums.encode("ascii"))
        for name in (*ARCHIVE_NAMES, "SHA256SUMS"):
            os.replace(staging / name, output / name)
            print(output / name)


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1:] in (["-h"], ["--help"]):
            print("Usage: python3 /path/to/spl/scripts/build_release.py")
            print("Builds preview, handoff, and SHA256SUMS in spl/dist/.")
            return 0
        print("error: This script accepts no arguments; use --help for usage.", file=sys.stderr)
        return 2
    try:
        build()
    except (BuildError, OSError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
