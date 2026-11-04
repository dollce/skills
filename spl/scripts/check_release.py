#!/usr/bin/env python3
"""Check skill structure and portable archives; never connect to Splunk."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

import build_release

try:
    import yaml
except ImportError:
    raise SystemExit(
        "error: Install check dependencies with "
        "python3 -m pip install -r spl/requirements-dev.txt"
    )


class CheckError(Exception):
    """A structural or packaging invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def check_local_links(skill: Path) -> None:
    """Check inline/reference-style Markdown file links, excluding code fences.

    External URLs and heading anchors are not fetched or validated.
    """
    for document in sorted(skill.rglob("*.md")):
        content = re.sub(
            r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$",
            "", document.read_text(encoding="utf-8"),
        )
        targets = re.findall(r"\]\(\s*(<[^>]+>|[^\s)]+)", content)
        targets += re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", content)
        for target in targets:
            target = target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            relative = Path(unquote(parsed.path))
            resolved = (document.parent / relative).resolve()
            require(
                not relative.is_absolute() and skill.resolve() in resolved.parents,
                f"Local link leaves the installable skill: {document}: {target}",
            )
            require(resolved.exists(), f"Broken local link: {document}: {target}")


def check_skill(skill: Path) -> None:
    document = (skill / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", document, re.S)
    require(frontmatter is not None, f"Missing YAML frontmatter: {skill / 'SKILL.md'}")
    metadata = yaml.safe_load(frontmatter.group(1))
    require(isinstance(metadata, dict), "Skill frontmatter must be a mapping")
    name = metadata.get("name")
    require(
        isinstance(name, str)
        and name == skill.name
        and len(name) <= 64
        and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is not None,
        "Skill name must match its directory and use lowercase letters, digits, and hyphens",
    )
    description = metadata.get("description")
    require(
        isinstance(description, str) and 0 < len(description.strip()) <= 1024,
        "Skill description must be nonempty text of at most 1024 characters",
    )
    ui = yaml.safe_load((skill / "agents/openai.yaml").read_text(encoding="utf-8"))
    require(isinstance(ui, dict), "UI metadata must be a mapping")
    interface = ui.get("interface")
    require(isinstance(interface, dict), "UI metadata must have an interface mapping")
    for field in ("display_name", "short_description"):
        value = interface.get(field)
        require(isinstance(value, str) and bool(value.strip()), f"UI {field} must be text")
    policy = ui.get("policy")
    require(
        isinstance(policy, dict) and policy.get("allow_implicit_invocation") is True,
        "This skill must enable policy.allow_implicit_invocation",
    )
    check_local_links(skill)


def run_build(root: Path, cwd: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(root / "scripts/build_release.py")],
        cwd=cwd, text=True, capture_output=True, check=False,
    )
    require(result.returncode == 0, f"Archive build failed:\n{result.stdout}{result.stderr}")


def check_archive(archive: Path, expected: dict[str, bytes], extraction: Path) -> None:
    directories = {
        parent.as_posix() + "/"
        for name in expected
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        require(
            len(names) == len(set(names)) and set(names) == set(expected) | directories,
            f"Unexpected archive entries: {archive.name}",
        )
        for info in package.infolist():
            require(
                info.date_time == build_release.ZIP_TIMESTAMP
                and info.compress_type == zipfile.ZIP_STORED,
                f"Noncanonical archive metadata: {archive.name}: {info.filename}",
            )
        for name, payload in expected.items():
            require(package.read(name) == payload, f"Archive content differs: {name}")
        # The exact entry set was checked against trusted relative source paths.
        package.extractall(extraction)
    extracted = {
        path.relative_to(extraction).as_posix(): path.read_bytes()
        for path in extraction.rglob("*") if path.is_file()
    }
    require(extracted == expected, f"Extracted content differs: {archive.name}")


def check() -> None:
    root = build_release.ROOT
    check_skill(root / build_release.SKILL)
    skill_files = build_release.skill_files()
    sources = {
        relative.as_posix(): build_release.checked_path(relative).read_bytes()
        for relative in (*build_release.HANDOFF_FILES, *skill_files)
    }
    with tempfile.TemporaryDirectory(prefix="spl-release-check-") as temporary:
        work = Path(temporary)
        staged = work / "source/spl"
        for name, payload in sources.items():
            destination = staged / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        # Builds must work from an unrelated current working directory.
        run_build(staged, work)
        dist = staged / "dist"
        artifacts = {
            name: (dist / name).read_bytes()
            for name in (*build_release.ARCHIVE_NAMES, "SHA256SUMS")
        }
        expected_checksums = "".join(
            f"{hashlib.sha256(artifacts[name]).hexdigest()}  {name}\n"
            for name in build_release.ARCHIVE_NAMES
        ).encode("ascii")
        require(artifacts["SHA256SUMS"] == expected_checksums, "SHA256SUMS differs")
        preview = {path.as_posix(): sources[path.as_posix()] for path in skill_files}
        handoff = {f"spl/{name}": payload for name, payload in sources.items()}
        check_archive(dist / build_release.ARCHIVE_NAMES[0], preview, work / "preview")
        check_archive(dist / build_release.ARCHIVE_NAMES[1], handoff, work / "handoff")
        check_skill(work / "preview" / build_release.SKILL)
        restored = work / "handoff/spl"
        check_skill(restored / build_release.SKILL)
        run_build(restored, work / "preview")
        for name, payload in artifacts.items():
            require((restored / "dist" / name).read_bytes() == payload, f"Rebuild differs: {name}")
    print("PASS: skill YAML, name, UI metadata, and local Markdown file links")
    print("PASS: archive boundaries, contents, checksums, extraction, and byte-identical rebuild")
    print("No live Splunk calls or behavioral/installation checks were performed.")


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1:] in (["-h"], ["--help"]):
            print("Usage: python3 /path/to/spl/scripts/check_release.py")
            print("Checks local structure and rebuilds archives in temporary directories only.")
            return 0
        print("error: This script accepts no arguments; use --help for usage.", file=sys.stderr)
        return 2
    try:
        check()
    except (CheckError, build_release.BuildError, OSError, ValueError, yaml.YAMLError,
            zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
