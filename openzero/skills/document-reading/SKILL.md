---
name: document-reading
description: "Extract and analyze local TXT, DOCX, PDF, or legacy DOC documents without interpreting binary bytes as text. Use for uploaded documents, Word files, PDF reading, summaries, content checks, or diagnosing document-conversion failures."
---

# Document reading

## Contract

- Detect the format from its signature and structure, not only its filename.
- Enforce file-size, archive-size, converter-time, and output limits.
- Extract DOCX through bounded ZIP/XML parsing without executing macros.
- Extract PDF with local `pdftotext` when available.
- Extract legacy DOC with local `antiword`, then isolated LibreOffice as a fallback.
- Return a clear converter or OCR requirement instead of binary garbage.

## Workflow

1. Record the filename, byte size, and detected format.
2. Reject oversized, malformed, encrypted, or unsupported input.
3. Use the narrow local extractor for that format.
4. Record method, warnings, and truncation.
5. Analyze only extracted text and distinguish missing content from empty content.
6. Clear document context when the user asks.

Read [formats and converters](references/formats-and-converters.md) when extraction fails, a file is scanned, or the extension disagrees with the content.

## Boundaries

- Do not upload a private document to a third party without fresh confirmation.
- Do not execute document macros or embedded objects.
- Do not claim images, handwriting, or scans were read without successful OCR or vision output.
