"""Create a reproducible Brave unpacked-extension handoff ZIP."""

from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUTPUT = DIST / "OpenZero-Tab-Pilot-Brave-v0.2.0.zip"
CHECKSUM = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
FILES = [
    Path("manifest.json"),
    Path("README.md"),
    Path("SECURITY.md"),
    Path("PRIVACY.md"),
    *sorted(path.relative_to(ROOT) for path in (ROOT / "src").rglob("*") if path.is_file()),
    *sorted(path.relative_to(ROOT) for path in (ROOT / "docs").rglob("*") if path.is_file()),
]


def main() -> None:
    DIST.mkdir(exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(set(FILES), key=lambda item: item.as_posix()):
            source = ROOT / relative
            info = ZipInfo(relative.as_posix(), date_time=FIXED_TIME)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    CHECKSUM.write_text(f"{digest}  {OUTPUT.name}\n", encoding="ascii", newline="\n")
    print(OUTPUT)
    print(f"SHA256 {digest}")


if __name__ == "__main__":
    main()
