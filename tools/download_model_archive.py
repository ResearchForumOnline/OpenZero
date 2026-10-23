"""Restore the OpenZero model archive mirror; verify, never unpack or execute.

This tool is covered by the repository OpenZero Community Source License.
Archive contents and model weights retain their original separate license terms.

The repository manifest names every source file and release part. Each part is
streamed into one exclusively created .partial file. Its length and SHA-256,
then the complete file length and SHA-256, must match before publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Callable
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "models" / "archive-mirror-20261023" / "manifest.json"
RELEASE_PREFIX = (
    "https://github.com/ResearchForumOnline/OpenZero/releases/download/"
    "model-archive-mirror-2026.10.23/"
)
CHUNK_BYTES = 1024 * 1024
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def safe_name(value: object) -> str:
    """Accept portable plain basenames, including on Windows."""
    if (not isinstance(value, str) or not NAME.fullmatch(value)
            or value.endswith((".", " ")) or value.split(".", 1)[0].upper() in RESERVED):
        raise ValueError("Manifest contains an unsafe file or asset name")
    return value


def positive_size(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("Manifest sizes must be positive integers")
    return value


def checksum(value: object) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ValueError("Manifest requires lowercase SHA-256 values")
    return value


def validate_manifest(document: object) -> list[dict]:
    if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1
            or document.get("id") != "openzero-model-archive-mirror"
            or not isinstance(document.get("files"), list) or not document["files"]):
        raise ValueError("Unsupported model archive manifest")
    files, names, assets = [], set(), set()
    for entry in document["files"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid file record")
        name = safe_name(entry.get("name"))
        size, digest = positive_size(entry.get("bytes")), checksum(entry.get("sha256"))
        if name.casefold() in names:
            raise ValueError("Duplicate file name in manifest")
        names.add(name.casefold())
        if not isinstance(entry.get("parts"), list) or not entry["parts"]:
            raise ValueError("Every source file needs at least one part")
        parts = []
        for part in entry["parts"]:
            if not isinstance(part, dict):
                raise ValueError("Invalid part record")
            part_name = safe_name(part.get("name"))
            if part_name.casefold() in assets:
                raise ValueError("Duplicate release asset name")
            assets.add(part_name.casefold())
            url = RELEASE_PREFIX + part_name
            if part.get("url") != url:
                raise ValueError("Part URL is outside the exact approved GitHub release")
            parts.append({"name": part_name, "url": url,
                          "bytes": positive_size(part.get("bytes")),
                          "sha256": checksum(part.get("sha256"))})
        if sum(part["bytes"] for part in parts) != size:
            raise ValueError("Part lengths do not sum to the complete file length")
        files.append({"name": name, "bytes": size, "sha256": digest, "parts": parts})
    # Prevent a final file from colliding with another file's temporary name.
    if names & {name + ".partial" for name in names}:
        raise ValueError("Manifest contains conflicting final and partial names")
    return files


def read_manifest(path: Path = MANIFEST) -> list[dict]:
    with path.open("r", encoding="utf-8") as source:
        return validate_manifest(json.load(source))


def approved_transport_url(url: str) -> bool:
    """GitHub releases redirect to signed HTTPS GitHub asset storage."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment):
        return False
    if parsed.hostname == "github.com":
        return url.startswith(RELEASE_PREFIX) and not parsed.query
    return parsed.hostname in {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}


class ReleaseRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not approved_transport_url(newurl):
            raise ValueError("Release redirect left approved HTTPS GitHub asset storage")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_release_part(url: str):
    # Initial URLs always come from validated manifest entries, never user input.
    if not approved_transport_url(url) or not url.startswith(RELEASE_PREFIX):
        raise ValueError("Unexpected initial release URL")
    opener = urllib.request.build_opener(ReleaseRedirectHandler())
    return opener.open(urllib.request.Request(url, headers={
        "User-Agent": "ResearchForumOnline-OpenZero-model-archive-restore/1",
        "Accept-Encoding": "identity",
    }), timeout=60)


def is_link_or_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def prepare_destination(destination: Path) -> Path:
    """Reject links/junctions in every existing directory component."""
    path = Path(os.path.abspath(destination.expanduser()))
    chain = list(reversed(path.parents)) + [path]
    for component in chain:
        try:
            info = component.lstat()
        except FileNotFoundError:
            component.mkdir()
            info = component.lstat()
        if is_link_or_reparse(component) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("Destination and its parents must be ordinary directories")
    return path


def exists_without_following(path: Path) -> bool:
    return os.path.lexists(path)


def identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def same_owned_file(path: Path, owned: tuple[int, int]) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and identity(info) == owned
    except FileNotFoundError:
        return False


def publish_without_overwrite(partial: Path, target: Path) -> None:
    if os.name == "nt":
        # Windows rename fails atomically when the destination already exists.
        os.rename(partial, target)
    else:
        # POSIX rename replaces files. A hard-link publication instead provides
        # atomic exclusive creation on the same filesystem, followed by unlink.
        os.link(partial, target, follow_symlinks=False)
        partial.unlink()


def restore_file(entry: dict, destination: Path,
                 transport: Callable = open_release_part) -> Path:
    """Restore one validated entry; transport injection is only for offline tests."""
    # Validate even library callers; never trust a caller-supplied URL directly.
    entry = validate_manifest({"schema_version": 1, "id": "openzero-model-archive-mirror",
                               "files": [entry]})[0]
    directory = prepare_destination(destination)
    directory_identity = identity(directory.stat())
    target = directory / entry["name"]
    partial = directory / (entry["name"] + ".partial")
    if exists_without_following(target) or exists_without_following(partial):
        raise FileExistsError("Refusing an existing target or partial file: " + entry["name"])
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(partial, flags, 0o600)
    owned = identity(os.fstat(fd))
    whole_hash, whole_size = hashlib.sha256(), 0
    try:
        with os.fdopen(fd, "wb") as output:
            for part in entry["parts"]:
                part_hash, part_size = hashlib.sha256(), 0
                try:
                    response = transport(part["url"])
                except Exception as error:
                    raise OSError("Transport failed for release part " + part["name"]) from error
                with response:
                    geturl = getattr(response, "geturl", None)
                    if geturl is not None and not approved_transport_url(geturl()):
                        raise ValueError("Response URL left approved GitHub asset storage")
                    while True:
                        block = response.read(CHUNK_BYTES)
                        if not block:
                            break
                        if not isinstance(block, bytes):
                            raise ValueError("Transport returned non-byte data")
                        part_size += len(block)
                        if part_size > part["bytes"]:
                            raise ValueError("Release part exceeds its recorded length")
                        if output.write(block) != len(block):
                            raise OSError("Incomplete write to partial model archive")
                        part_hash.update(block)
                        whole_hash.update(block)
                        whole_size += len(block)
                if part_size != part["bytes"] or part_hash.hexdigest() != part["sha256"]:
                    raise ValueError("Release part length or SHA-256 does not match: " + part["name"])
            if whole_size != entry["bytes"] or whole_hash.hexdigest() != entry["sha256"]:
                raise ValueError("Complete model archive length or SHA-256 does not match")
            output.flush()
            os.fsync(output.fileno())
        if (identity(directory.stat()) != directory_identity or is_link_or_reparse(directory)
                or not same_owned_file(partial, owned)):
            raise ValueError("Destination or owned partial file changed during download")
        publish_without_overwrite(partial, target)
        return target
    except BaseException:
        # Only remove the exact regular file exclusively created by this call.
        if same_owned_file(partial, owned):
            partial.unlink()
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="List source files and required download parts")
    mode.add_argument("--destination", type=Path, help="Directory for reconstructed original files")
    parser.add_argument("--file", help="Select one exact original filename from the repository manifest")
    args = parser.parse_args(argv)
    try:
        files = read_manifest()
        if args.file:
            files = [entry for entry in files if entry["name"] == args.file]
            if not files:
                raise ValueError("Requested filename is not in the model archive manifest")
        if args.list:
            for entry in files:
                print(f"{entry['name']}\t{entry['bytes']} bytes\t{len(entry['parts'])} part(s)")
            return 0
        destination = prepare_destination(args.destination)
        # Preflight all selected names before starting any download.
        for entry in files:
            if any(exists_without_following(destination / (entry["name"] + suffix))
                   for suffix in ("", ".partial")):
                raise FileExistsError("Refusing existing target or partial: " + entry["name"])
        for entry in files:
            result = restore_file(entry, destination)
            print("Verified:", result)
            print("SHA256:", entry["sha256"])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Model archive restore failed:", str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Model archive restore cancelled; owned partial cleaned up.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
