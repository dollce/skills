"""Link this checkout's public skills for local testing on macOS and Linux."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]


def public_skills(root: Path) -> dict[str, Path]:
    """Each configured collection contains one directory per published skill."""
    config = json.loads((root / "skills.sh.json").read_text(encoding="utf-8"))
    paths = config.get("paths") if isinstance(config, dict) else None
    if not isinstance(paths, list):
        raise ValueError("skills.sh.json must have a paths array")
    skills = {}
    for entry in paths:
        if not isinstance(entry, str) or not entry.startswith("./") or ".." in Path(entry).parts:
            raise ValueError(f"Invalid collection path: {entry!r}")
        group = root / entry
        if group == root or group.resolve() != group or not group.is_dir():
            raise ValueError(f"Expected a collection directory inside the checkout: {group}")
        for document in sorted(group.glob("*/SKILL.md")):
            source = document.parent
            if document.resolve() != document or not document.is_file():
                raise ValueError(f"Expected a regular in-repo skill: {document}")
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", source.name):
                raise ValueError(f"Invalid skill directory name: {source.name}")
            if source.name in skills:
                raise ValueError(f"Duplicate skill directory name: {source.name}")
            skills[source.name] = source
    return skills


def owned(link: Path, receipt: Path) -> bool:
    # The receipt is a second name for the symlink itself. A replacement pointing
    # to the very same source is still a different inode and must be preserved.
    try:
        info = receipt.lstat()
        return stat.S_ISLNK(info.st_mode) and os.path.samestat(info, link.lstat())
    except FileNotFoundError:
        return False


def release_link(link: Path, receipt: Path) -> None:
    if not receipt.is_symlink():
        raise ValueError(f"Unexpected file in development link records: {receipt}")
    if owned(link, receipt):
        link.unlink()
        print(f"removed  {link}")
    elif os.path.lexists(link):
        print(f"kept     {link} (replaced since linking)")
    receipt.unlink()


def link_skills(skills: dict[str, Path], dest: Path, records: Path) -> None:
    # Preflight the whole batch before creating its first link.
    for name, source in skills.items():
        link, receipt = dest / name, records / name
        if os.path.lexists(receipt) and not receipt.is_symlink():
            raise ValueError(f"Unexpected development link record: {receipt}")
        if not os.path.lexists(link):
            continue
        if not owned(link, receipt):
            raise ValueError(f"Already occupied: {link}. Choose another scope or remove its installation first.")
        if link.readlink() != source:
            raise ValueError(f"Skill source moved: {link}. Run make dev-unlink before relinking.")

    dest.mkdir(exist_ok=True)
    records.mkdir(parents=True, exist_ok=True, mode=0o700)
    created = []
    try:
        for name, source in skills.items():
            link, receipt = dest / name, records / name
            if owned(link, receipt):
                print(f"linked   {link} -> {source} (already linked)")
                continue
            if receipt.is_symlink():
                receipt.unlink()  # Only the receipt survived an interrupted run.
            receipt.symlink_to(source, target_is_directory=True)
            created.append(name)
            # Publish without overwriting an entry created after the preflight.
            os.link(receipt, link, follow_symlinks=False)
            print(f"linked   {link} -> {source}")
    except BaseException:
        for name in created:
            release_link(dest / name, records / name)
        raise


def manage(action: str, root: Path, agents_dir: Path, skills: dict[str, Path]) -> None:
    dest = agents_dir / "skills"
    checkout = hashlib.sha256(os.fsencode(root)).hexdigest()
    records = agents_dir / ".dollce-dev-links" / checkout
    if action == "unlink" and not os.path.lexists(records):
        return
    for directory in (agents_dir, dest, records.parent, records):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(f"Expected a real directory: {directory}")

    if action == "status":
        names = set(skills)
        if records.is_dir():
            names.update(entry.name for entry in records.iterdir())
        for name in sorted(names):
            link = dest / name
            target = link.readlink() if link.is_symlink() else None
            if owned(link, records / name):
                state = "linked" if target == skills.get(name) and link.is_dir() else "stale"
            else:
                state = "occupied" if os.path.lexists(link) else "absent"
            print(f"{state:8} {link}" + (f" -> {target}" if target is not None else ""))
        return

    agents_dir.mkdir(parents=True, exist_ok=True)
    # Serialize link/unlink from this and other checkouts using the same scope.
    fd = os.open(agents_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if action == "link":
            link_skills(skills, dest, records)
        elif records.is_dir():
            for receipt in sorted(records.iterdir()):
                release_link(dest / receipt.name, receipt)
            records.rmdir()
            if not any(records.parent.iterdir()):
                records.parent.rmdir()
    finally:
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    linker = commands.add_parser("link", help="Link skills in this project")
    linker.add_argument("--global", dest="user_scope", action="store_true")
    commands.add_parser("status", help="Show project and user skill paths")
    commands.add_parser("unlink", help="Remove this checkout's development links in both scopes")
    args = parser.parse_args()
    # Cleanup also works after deleting a skill or changing the catalog.
    skills = {} if args.action == "unlink" else public_skills(ROOT)
    scopes = [ROOT / ".agents", Path.home() / ".agents"]
    if args.action == "link":
        scopes = [scopes[1] if args.user_scope else scopes[0]]
    for agents_dir in scopes:
        manage(args.action, ROOT, agents_dir, skills)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        sys.exit(f"error: {exc}")
