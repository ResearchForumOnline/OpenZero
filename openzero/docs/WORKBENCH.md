# OpenZero improvement workbench

The workbench brings reviewed source improvements and explicit model-training
jobs into the same local operator interface. It keeps the currently installed
model separate from training candidates.

## Code improvements

Choose a small set of source files and describe the change you want. Create a
candidate, generate or edit its proposed source, inspect the diff, run checks,
and review the result before applying it. Applying a candidate requires its
current digest; changes to either the original files or the candidate invalidate
the previous review. Originals are retained for rollback.

Syntax checks establish parseability only. A passing syntax check does not
establish that the application works. Run unchanged acceptance tests and inspect
the behavior before accepting a functional change. Tests execute code with the
service account's permissions; a candidate directory is not an OS sandbox.

The policy and integrity implementation are excluded from candidate edits.
Integrity verification does not silently sign changed policies. Local hashes are
tamper evidence, not protection against an administrator with full disk access.

## Weight training

The small CPU fixture performs real numerical adapter updates against a frozen
synthetic base and evaluates separate held-out examples. It exports candidate
weights with before/after metrics and hashes. It demonstrates the training
workflow; it is not an LLM or evidence that your assistant became more capable.

The optional local LoRA backend requires a compatible locally available model,
reviewed dataset, and installed PyTorch, Transformers, PEFT and Safetensors.
Preflight checks must pass before a training job starts. Training produces a
separate adapter; it does not overwrite a running GGUF, replace the selected
Ollama model, or publish your data.

A generated adapter must be evaluated on your actual coding/research tasks.
Base/adapter architecture and export compatibility must be checked before
deployment. Ollama imports and model-setting changes are not training.

The inspected server has six logical CPUs, approximately 21.5 GiB RAM and no
detected compute GPU. A 30-billion-parameter BF16 base alone occupies roughly
60 GB before training overhead. The workbench does not make that training job
fit on this server. Use a smaller compatible base or a separately provisioned
training machine; no cloud purchase or large model download is automatic.

## Access and privacy

Use the local panel (including an SSH port forward) or a valid OpenZero API
bearer key. New workbench APIs reject cross-origin browser requests and require
JSON for mutations. They do not accept the browser planner-only token. Keep
keys out of URLs, screenshots, source control and published examples.

Review every dataset before training. Do not include credentials, recovery
material or private correspondence without appropriate rights and consent.
Candidate source selection excludes runtime configuration and credentials.

## Technical references

- [PEFT training and adapter export](https://huggingface.co/docs/peft/main/quicktour)
- [Transformers GGUF behavior](https://huggingface.co/docs/transformers/en/quantization/gguf)
- [Ollama model import](https://docs.ollama.com/import)
- [llama.cpp LoRA converter](https://github.com/ggml-org/llama.cpp/blob/master/convert_lora_to_gguf.py)

These describe mechanisms and compatibility requirements; they do not establish
quality gains for a particular training run.
