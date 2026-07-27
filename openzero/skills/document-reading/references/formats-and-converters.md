# Formats and converters

- TXT and source files: decode only when the sample is text-like; reject NUL-heavy or binary data.
- DOCX: require a valid ZIP containing `word/document.xml`; parse text, paragraph breaks, tabs, tables, headers, footers, notes, and comments without extracting executables.
- PDF: use `pdftotext -layout -nopgbrk`. If it returns no useful text, report that the PDF may be scanned and requires OCR.
- DOC: prefer `antiword`. If unavailable, use LibreOffice headlessly with an isolated temporary user profile. Never enable macros.

Converters are local capabilities, not guaranteed features. Report the missing executable by name and retain the original upload. Never fall back to decoding arbitrary binary bytes with UTF-8 error suppression.
