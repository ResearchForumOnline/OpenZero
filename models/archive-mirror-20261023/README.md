# Exact OpenZero model archive mirror

These two historical ZIP archives preserve the existing custom Gemma and Qwen GGUFs. The original OpenZero Community Source License remains in force, with base Apache notices supplied separately. Read [MODEL_CARD.md](MODEL_CARD.md), [PROVENANCE.json](PROVENANCE.json) and [SOURCE_NOTICES.md](SOURCE_NOTICES.md) before use.

The [model-archive-mirror-2026.10.23 release](https://github.com/ResearchForumOnline/OpenZero/releases/tag/model-archive-mirror-2026.10.23) stores each exact ZIP as four ordered parts, each below GitHub's individual asset size limit. `manifest.json` records every part and whole-file size/SHA-256, plus the contained GGUF digest. The SHA-256 manifest detects corruption or mismatch; it is not an independent publisher signature.

From a checked-out copy of this repository, using Python 3.10 or newer:

```sh
python tools/download_model_archive.py --list
python tools/download_model_archive.py --destination ./restored-model-archives
```

To select just one archive, add `--file` with its exact filename from `--list`. The downloader uses anonymous HTTPS requests to the pinned GitHub release, verifies each part and the reconstructed ZIP, refuses existing targets/partials, and removes only its own incomplete output on failure. It does not extract ZIPs, install a model, run inference or execute downloaded content. Allow about 11.8 GB for both reconstructed archives. A separate extractor and model runtime are optional later steps under your control.

The model card records the 2033-row historical training family and the limits of today's source/privacy review. These weights have not been retrained on the separately reviewed 1921-row dataset subset. No raw training rows or private login/customer material are included in the release metadata.
