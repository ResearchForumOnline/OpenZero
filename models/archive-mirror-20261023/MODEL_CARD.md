# OpenZero historical model archive mirror

This mirror preserves the two original custom model ZIP archives byte for byte. Each ZIP contains one standalone GGUF. The contained GGUFs match existing anonymous public Hugging Face LFS objects at the pinned revisions in `PROVENANCE.json`. Archive/member SHA-256, sizes, GGUF architecture and tensor counts were verified on 23 October 2026. No inference or training was run during the audit.

The model distribution remains under **OpenZero Community Source License v1.0**. It permits the stated personal, academic, research, evaluation and noncommercial uses; commercial uses require the separate permission specified in that license. This is a source-available model distribution with those existing restrictions. The Apache-2.0 licenses of the base models are included separately and do not replace the OpenZero distribution terms. Retain all applicable attribution and license notices.

| Archive | Actual model | Inner GGUF bytes | Tensors |
|---|---|---:|---:|
| `Zero-Gemma4-E4B-OpenZero-Q5_K_M-F16-Merged-kaggle.zip` | `gemma4` | 5,865,235,584 | 720 |
| `Zero-Qwen3-8B-OpenZero-Q5_K_M-kaggle.zip` | `qwen3` | 5,851,112,224 | 399 |

The Gemma archive is a real `gemma4` model, distinct from the Qwen `qwen3` model. Despite the historical `F16-Merged` filename and inherited GGUF file-type field, Gemma contains mixed quantized and floating-point tensor storage; it is not an all-F16 model. The filenames are retained for exact archival fidelity.

Both historical runs used the 2033-row Gemma-family training mixture identified by the preserved build/release receipts. That mixture includes public NVIDIA OpenCode examples, public CommitPackFT code edits, the named Apache-2.0 SmolTalk subsets, an earlier validated mixture, and original authored examples. The current source hashes and source revisions are recorded. A separate immutable input hash for each historical run was not located, so this is documented lineage rather than a claim that each run's exact input bytes were independently recovered.

The reviewed dataset published separately contains 1921 rows. These weights were not retrained on that filtered dataset. Its omitted rows include unresolved exact-source licensing and contact/path review cases. All seven email-bearing rows in the historical mixture were independently matched in already-public GitHub source code at recorded commits or their parents, including public code attribution and seed examples. The single path-bearing row traces to public NVIDIA provenance and appears in assistant code/command context; its exact original NVIDIA row was not independently re-fetched. No contact values, path values or training rows are included here. These checks identified no evidence tying those flagged contexts to private owner/customer data, and do not establish complete privacy, memorization resistance or universal copyright clearance.

The custom GGUFs were already public on Hugging Face. This archival mirror adds redundancy and explicit provenance; it does not add claims of benchmark quality, scientific validity, safety certification or support for consequential decisions. No optimizer state, private configuration, raw training rows or diagnostic adapters accompany this mirror.

Use the release's hash-checked restore instructions to reconstruct the original ZIPs. Verify the outer ZIP SHA-256 and inner GGUF SHA-256 before use. Reconstructing or inspecting an archive does not require executing its contents. See `PROVENANCE.json` for exact pinned download URLs and `SOURCE_NOTICES.md` for source/license links.
