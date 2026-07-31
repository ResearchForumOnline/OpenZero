"""Create a reproducible Chrome Web Store ZIP without the self-hosted updater."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
VERSION = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
OUTPUT = DIST / f"OpenZero-Tab-Pilot-Web-Store-v{VERSION}.zip"
CHECKSUM = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
FILES = [
    *sorted(path.relative_to(ROOT) for path in (ROOT / "assets").rglob("*") if path.is_file()),
    *sorted(path.relative_to(ROOT) for path in (ROOT / "src").rglob("*") if path.is_file()),
]


def write_file(archive: ZipFile, relative: Path, payload: bytes) -> None:
    info = ZipInfo(relative.as_posix(), date_time=FIXED_TIME)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload, compress_type=ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("update_url", None)
    manifest_payload = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")

    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        write_file(archive, Path("manifest.json"), manifest_payload)
        for relative in sorted(set(FILES), key=lambda item: item.as_posix()):
            write_file(archive, relative, (ROOT / relative).read_bytes())

    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    CHECKSUM.write_text(f"{digest}  {OUTPUT.name}\n", encoding="ascii", newline="\n")
    print(OUTPUT)
    print(f"SHA256 {digest}")


if __name__ == "__main__":
    main()
