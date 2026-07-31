"""Bounded local text extraction for OpenZero document uploads."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Sequence
from xml.etree import ElementTree


DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_CHARS = 200_000
MAX_DOCX_FILES = 2_000
MAX_DOCX_UNCOMPRESSED = 64 * 1024 * 1024
MAX_DOCX_MEMBER = 24 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
PDF_MAGIC = b"%PDF-"
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".csv",
    ".env",
    ".ini",
    ".json",
    ".log",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


class DocumentExtractionError(ValueError):
    """A document could not be safely converted to text."""


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    cleaned = str(text or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned).strip()
    if len(cleaned) > max_chars:
        return cleaned[:max_chars].rstrip(), True
    return cleaned, False


def _text_decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as error:
            raise DocumentExtractionError("The UTF-16 text is malformed.") from error
    if b"\x00" in data[:8192]:
        raise DocumentExtractionError("The upload is binary, not a supported plain-text document.")
    sample = data[:8192]
    control_count = sum(byte < 32 and byte not in (9, 10, 12, 13) for byte in sample)
    if sample and control_count / len(sample) > 0.03:
        raise DocumentExtractionError("The upload contains binary control data and cannot be indexed as text.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentExtractionError("The text encoding is not supported.")


def detect_document_format(path: Path | str) -> str:
    target = Path(path)
    try:
        with target.open("rb") as handle:
            prefix = handle.read(8192)
    except OSError as error:
        raise DocumentExtractionError(f"Could not read the upload: {error}") from error

    if prefix.startswith(PDF_MAGIC):
        return "pdf"
    if prefix.startswith(OLE_MAGIC):
        return "doc"
    if zipfile.is_zipfile(target):
        try:
            with zipfile.ZipFile(target, "r") as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except (OSError, zipfile.BadZipFile) as error:
            raise DocumentExtractionError(f"The Office archive is invalid: {error}") from error
        raise DocumentExtractionError("The ZIP upload is not a DOCX document.")

    suffix = target.suffix.lower()
    if suffix in {".pdf", ".doc", ".docx"}:
        raise DocumentExtractionError(f"The file extension is {suffix}, but its document signature is invalid.")
    if suffix in TEXT_EXTENSIONS or prefix:
        if not prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
            _text_decode(prefix)
        return "text"
    return "text"


def _validate_docx(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_DOCX_FILES:
        raise DocumentExtractionError(f"DOCX contains too many members ({len(infos)} > {MAX_DOCX_FILES}).")
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise DocumentExtractionError("Encrypted DOCX files are not supported.")
        if info.file_size > MAX_DOCX_MEMBER:
            raise DocumentExtractionError(f"DOCX member is too large: {info.filename}")
        total += info.file_size
        compressed = max(info.compress_size, 1)
        if info.file_size / compressed > MAX_COMPRESSION_RATIO:
            raise DocumentExtractionError(f"DOCX member has an unsafe compression ratio: {info.filename}")
    if total > MAX_DOCX_UNCOMPRESSED:
        raise DocumentExtractionError(
            f"DOCX expands to {total} bytes, above the {MAX_DOCX_UNCOMPRESSED}-byte limit."
        )


def _xml_paragraphs(xml_bytes: bytes, source_name: str) -> List[str]:
    if b"<!DOCTYPE" in xml_bytes.upper() or b"<!ENTITY" in xml_bytes.upper():
        raise DocumentExtractionError(f"Unsupported XML declaration in {source_name}.")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as error:
        raise DocumentExtractionError(f"Malformed DOCX XML in {source_name}: {error}") from error

    paragraphs: List[str] = []
    for paragraph in (element for element in root.iter() if element.tag.endswith("}p")):
        pieces: List[str] = []
        for node in paragraph.iter():
            if node.tag.endswith("}t") and node.text:
                pieces.append(node.text)
            elif node.tag.endswith("}tab"):
                pieces.append("\t")
            elif node.tag.endswith("}br") or node.tag.endswith("}cr"):
                pieces.append("\n")
        value = "".join(pieces).strip()
        if value:
            paragraphs.append(value)
    if not paragraphs:
        fallback = "".join(node.text or "" for node in root.iter() if node.tag.endswith("}t")).strip()
        if fallback:
            paragraphs.append(fallback)
    return paragraphs


def _docx_part_names(names: Sequence[str]) -> List[str]:
    wanted = ["word/document.xml"]
    for prefix in ("word/header", "word/footer"):
        wanted.extend(sorted(name for name in names if name.startswith(prefix) and name.endswith(".xml")))
    for fixed in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"):
        if fixed in names:
            wanted.append(fixed)
    return wanted


def _extract_docx(path: Path) -> tuple[str, str, List[str]]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            _validate_docx(archive)
            names = archive.namelist()
            sections: List[str] = []
            for part_name in _docx_part_names(names):
                paragraphs = _xml_paragraphs(archive.read(part_name), part_name)
                if not paragraphs:
                    continue
                if part_name != "word/document.xml":
                    label = Path(part_name).stem.replace("_", " ").title()
                    sections.append(f"[{label}]\n" + "\n".join(paragraphs))
                else:
                    sections.append("\n".join(paragraphs))
    except zipfile.BadZipFile as error:
        raise DocumentExtractionError(f"The DOCX archive is invalid: {error}") from error
    return "\n\n".join(sections), "stdlib-zip-xml", []


def _run_converter(command: Sequence[str], timeout: int, label: str) -> bytes:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise DocumentExtractionError(f"{label} timed out after {timeout} seconds.") from error
    except OSError as error:
        raise DocumentExtractionError(f"{label} could not start: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
        raise DocumentExtractionError(f"{label} failed: {detail[:500] or f'exit code {result.returncode}'}")
    return result.stdout


def _extract_pdf(path: Path) -> tuple[str, str, List[str]]:
    executable = shutil.which("pdftotext")
    if not executable:
        raise DocumentExtractionError(
            "PDF extraction requires the local `pdftotext` executable (Poppler), which is not installed."
        )
    output = _run_converter([executable, "-layout", "-nopgbrk", str(path), "-"], 60, "pdftotext")
    text = output.decode("utf-8", errors="replace")
    warnings: List[str] = []
    if not text.strip():
        warnings.append("No embedded text was found; this PDF may be scanned and require OCR.")
    return text, "pdftotext", warnings


def _extract_doc(path: Path) -> tuple[str, str, List[str]]:
    antiword = shutil.which("antiword")
    if antiword:
        output = _run_converter([antiword, str(path)], 60, "antiword")
        return output.decode("utf-8", errors="replace"), "antiword", []

    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice:
        raise DocumentExtractionError(
            "Legacy DOC extraction requires local `antiword` or LibreOffice, but neither converter is installed."
        )
    with tempfile.TemporaryDirectory(prefix="openzero-doc-") as temp_dir:
        temp_root = Path(temp_dir)
        profile = temp_root / "profile"
        output_dir = temp_root / "output"
        output_dir.mkdir()
        command = [
            libreoffice,
            "--headless",
            "--safe-mode",
            "--nologo",
            "--nodefault",
            "--norestore",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(output_dir),
            str(path),
        ]
        _run_converter(command, 90, "LibreOffice")
        candidates = sorted(output_dir.glob("*.txt"))
        if not candidates:
            raise DocumentExtractionError("LibreOffice did not produce a text file for the DOC upload.")
        try:
            text = _text_decode(candidates[0].read_bytes())
        except OSError as error:
            raise DocumentExtractionError(f"Could not read LibreOffice output: {error}") from error
    return text, "libreoffice-headless-isolated", ["Macros and embedded objects were not executed."]


def extract_document(
    path: Path | str,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Dict[str, object]:
    target = Path(path).resolve()
    if not target.is_file():
        raise DocumentExtractionError("The uploaded document does not exist.")
    size = target.stat().st_size
    if size > max_bytes:
        raise DocumentExtractionError(f"Document is {size} bytes, above the {max_bytes}-byte upload limit.")
    if size == 0:
        raise DocumentExtractionError("The uploaded document is empty.")

    detected = detect_document_format(target)
    if detected == "docx":
        text, method, warnings = _extract_docx(target)
    elif detected == "pdf":
        text, method, warnings = _extract_pdf(target)
    elif detected == "doc":
        text, method, warnings = _extract_doc(target)
    else:
        text = _text_decode(target.read_bytes())
        method = "bounded-text-decode"
        warnings = []

    bounded, truncated = _bounded_text(text, max_chars)
    if not bounded and detected != "pdf":
        warnings.append("The document was valid but contained no readable text.")
    if truncated:
        warnings.append(f"Extracted text was truncated at {max_chars} characters.")
    return {
        "text": bounded,
        "format": detected,
        "method": method,
        "byte_size": size,
        "truncated": truncated,
        "warnings": warnings,
    }
