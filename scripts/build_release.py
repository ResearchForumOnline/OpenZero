#!/usr/bin/env python3
"""Build a deterministic, runtime-safe OpenZero release archive."""

from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "openzero"
DIST = ROOT / "dist"
ARCHIVE = DIST / "openzero_release.zip"
CHECKSUM = DIST / "openzero_release.zip.sha256"
INSTALLER_CHECKSUM = DIST / "install.sh.sha256"
HOSTED_INSTALLER = DIST / "install.sh"
HOSTED_UPDATER = DIST / "update.sh"
FIXED_DATE = (2026, 1, 1, 0, 0, 0)

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".runtime",
    "__pycache__",
    "backups",
    "build",
    "dist",
    "downloads",
    "knowledge",
    "models",
    "node_modules",
    "security",
    "uploads",
    "voice",
}
EXCLUDED_NAMES = {
    ".env",
    "node_private.pem",
    "openzero_master.key",
    "openzero_release.zip",
    "openzero_release.zip.sha256",
    "RELEASE_MANIFEST.txt",
}
EXCLUDED_SUFFIXES = {
    ".bak",
    ".crt",
    ".db",
    ".key",
    ".log",
    ".pem",
    ".pid",
    ".p12",
    ".pyc",
    ".sqlite",
}


def is_excluded(path: Path) -> bool:
    relative = path.relative_to(SOURCE)
    if any(part in EXCLUDED_DIRS for part in relative.parts[:-1]):
        return True
    if path.name in EXCLUDED_NAMES or path.name.startswith(".env."):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name.startswith(("id_rsa", "id_ed25519")):
        return True
    return False


def release_files() -> list[Path]:
    files = [
        path
        for path in SOURCE.rglob("*")
        if path.is_file() and not is_excluded(path)
    ]
    return sorted(files, key=lambda path: path.relative_to(SOURCE).as_posix())


def entry_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_DATE)
    info.create_system = 3
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def packaged_bytes(path: Path) -> bytes:
    content = path.read_bytes()
    if path.suffix == ".sh":
        return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return content


def main() -> None:
    required = [SOURCE / "brain" / "app.py", SOURCE / "install.sh"]
    if not all(path.is_file() for path in required):
        raise SystemExit("OpenZero release source is incomplete.")

    files = release_files()
    manifest_lines = []
    for path in files:
        relative = PurePosixPath(path.relative_to(SOURCE))
        digest = hashlib.sha256(packaged_bytes(path)).hexdigest()
        manifest_lines.append(f"{digest}  {relative.as_posix()}")

    manifest = (
        "# OpenZero deterministic release manifest\n"
        "# Runtime state, credentials, models, uploads, and local knowledge are excluded.\n"
        + "\n".join(manifest_lines)
        + "\n"
    ).encode("utf-8")

    DIST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compresslevel=9) as package:
        for path in files:
            relative = path.relative_to(SOURCE).as_posix()
            executable = path.suffix == ".sh" or path.name in {
                "ignite.sh",
                "janitor.sh",
                "setup_service.sh",
                "update.sh",
            }
            package.writestr(entry_info(relative, executable), packaged_bytes(path))
        package.writestr(entry_info("RELEASE_MANIFEST.txt"), manifest)

    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    CHECKSUM.write_text(f"{digest}  {ARCHIVE.name}\n", encoding="ascii", newline="\n")
    installer_bytes = packaged_bytes(SOURCE / "install.sh")
    updater_bytes = packaged_bytes(SOURCE / "update.sh")
    HOSTED_INSTALLER.write_bytes(installer_bytes)
    HOSTED_UPDATER.write_bytes(updater_bytes)
    installer_digest = hashlib.sha256(installer_bytes).hexdigest()
    INSTALLER_CHECKSUM.write_text(
        f"{installer_digest}  install.sh\n",
        encoding="ascii",
        newline="\n",
    )
    print(f"Built {ARCHIVE} ({ARCHIVE.stat().st_size} bytes)")
    print(f"SHA-256 {digest}")
    print(f"Installer SHA-256 {installer_digest}")


if __name__ == "__main__":
    main()
