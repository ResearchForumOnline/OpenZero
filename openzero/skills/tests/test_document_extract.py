from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SKILLS_ROOT = Path(__file__).resolve().parents[1]
OPENZERO_ROOT = SKILLS_ROOT.parent
if str(OPENZERO_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENZERO_ROOT))

from skills.document_extract import (  # noqa: E402
    DocumentExtractionError,
    detect_document_format,
    extract_document,
)


DOCX_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Hello OpenZero</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell value</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:p><w:r><w:t>Line</w:t><w:tab/><w:t>two</w:t></w:r></w:p>
  </w:body>
</w:document>"""


def write_docx(path: Path, xml: bytes = DOCX_XML) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)


class DocumentExtractTests(unittest.TestCase):
    def test_extracts_docx_with_stdlib(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.docx"
            write_docx(path)
            result = extract_document(path)
        self.assertEqual(result["format"], "docx")
        self.assertEqual(result["method"], "stdlib-zip-xml")
        self.assertIn("Hello OpenZero", result["text"])
        self.assertIn("Cell value", result["text"])
        self.assertIn("Line\ttwo", result["text"])
        self.assertFalse(result["truncated"])

    def test_format_detection_rejects_fake_docx(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fake.docx"
            path.write_text("not really a docx", encoding="utf-8")
            with self.assertRaisesRegex(DocumentExtractionError, "signature is invalid"):
                detect_document_format(path)

    def test_binary_data_is_not_decoded_as_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "binary.bin"
            path.write_bytes(b"abc\x00def\x01ghi")
            with self.assertRaisesRegex(DocumentExtractionError, "binary"):
                extract_document(path)

    def test_utf16_text_is_supported_without_weakening_binary_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "utf16.txt"
            path.write_bytes("Hello UTF-16".encode("utf-16"))
            result = extract_document(path)
        self.assertEqual(result["format"], "text")
        self.assertEqual(result["text"], "Hello UTF-16")

    def test_pdf_reports_missing_converter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.pdf"
            path.write_bytes(b"%PDF-1.4\nminimal")
            with mock.patch("skills.document_extract.shutil.which", return_value=None):
                with self.assertRaisesRegex(DocumentExtractionError, "pdftotext"):
                    extract_document(path)

    def test_doc_reports_missing_converter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.doc"
            path.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"rest")
            with mock.patch("skills.document_extract.shutil.which", return_value=None):
                with self.assertRaisesRegex(DocumentExtractionError, "antiword"):
                    extract_document(path)

    def test_size_and_output_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text("0123456789" * 5, encoding="utf-8")
            with self.assertRaisesRegex(DocumentExtractionError, "upload limit"):
                extract_document(path, max_bytes=10)
            result = extract_document(path, max_chars=12)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), 12)

    def test_docx_rejects_entity_declarations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "entity.docx"
            write_docx(path, b'<!DOCTYPE x [<!ENTITY boom "bad">]><x>&boom;</x>')
            with self.assertRaisesRegex(DocumentExtractionError, "Unsupported XML declaration"):
                extract_document(path)


if __name__ == "__main__":
    unittest.main()
