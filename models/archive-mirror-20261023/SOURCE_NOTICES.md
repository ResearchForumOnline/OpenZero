# Source and license notices

OpenZero custom model distribution: copyright 2026 Shaf Brady; OpenZero Community Source License v1.0, reproduced unchanged in `LICENSE.OpenZero-Community-Source-v1.0.txt`. The mirror preserves those terms and does not relicense the custom models.

Base models:

- Qwen Team / Alibaba Cloud: [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), Apache-2.0. Exact upstream license reproduced in `LICENSE.Qwen3-base.txt`.
- Google: [Gemma 4 E4B instruction model](https://huggingface.co/google/gemma-4-E4B-it), with quantized base distributed by [Unsloth](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF). Google's current [Gemma 4 license page](https://ai.google.dev/gemma/apache_2) specifies Apache-2.0. Full Apache-2.0 text is supplied in `LICENSE.Apache-2.0.txt`. This notice concerns Gemma 4 and does not generalize the terms of older Gemma generations.

Training-source provenance (training rows are not mirrored here):

- NVIDIA [Nemotron-SFT-OpenCode-v1](https://huggingface.co/datasets/nvidia/Nemotron-SFT-OpenCode-v1), CC-BY-4.0 according to its official dataset card. Historical transformations replace the source persona, keep question/final answer and remove raw tool traces.
- BigCode [CommitPackFT](https://huggingface.co/datasets/bigcode/commitpackft), MIT dataset preparation; underlying code retains its individual repository licenses. Historical before/after code edits were converted to instruction examples. Some exact-source license evidence remained unresolved in the later dataset release review; no universal clearance claim is made here.
- HuggingFaceTB [SmolTalk](https://huggingface.co/datasets/HuggingFaceTB/smoltalk): only the named new subsets smol-constraints, smol-magpie-ultra, smol-rewrite and smol-summarize were selected under their Apache-2.0 terms. Other component terms are not generalized.
- Earlier local validated mixture and original curated OpenZero examples: source identifiers, revisions, counts and transformations are described in `PROVENANCE.json`; no private source content or local filesystem locations are included.

Source-code licensing, dataset licensing and model-weight licensing are distinct questions. The existing model terms are retained; this notice does not override any upstream rights or purport to resolve all training-data legal questions. Preserve original notices when redistributing upstream material separately. Public source citations are provided for provenance, not as a claim of endorsement by NVIDIA, Google, Alibaba, BigCode, Hugging Face or Unsloth.
