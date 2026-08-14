# OpenZero Models

OpenZero promotes one verified default and one explicit compatibility fallback.
Research artifacts may remain available in the wider model collection, but they
are not advertised by the installer, API catalog, Super Agent panel, or Tab Pilot.

## Verified Runtime Matrix

| Model | GGUF file | Size | SHA-256 | OpenZero runtime name | Policy |
| --- | --- | ---: | --- | --- | --- |
| [OpenZero Ministral3 8B Runtime Agent](https://huggingface.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF) | `OpenZero-Ministral3-8B-Runtime-Agent-Q5_K_M.gguf` | 6,058,748,288 bytes (5.64 GiB) | `e9aba29e5465164933d334215c2e8d5d9edddfd5caf71ecce6c5f811ceb11d9e` | `hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M` | Default |
| [Zero-Gemma4 E4B OpenZero](https://huggingface.co/shafire/Zero-Gemma4-E4B-OpenZero-GGUF) | `Zero-Gemma4-E4B-OpenZero-Q5_K_M-F16-Merged.gguf` | 5,865,235,584 bytes (5.46 GiB) | `84fd62ff6c5f0abe14dd2c6135e56800df4bc4a0b9d4cd8d9f26c36b28aa190b` | `openzerogemma:latest` | Compatibility fallback |

The Ministral release uses unchanged upstream weights with an OpenZero runtime
chat template. It is a runtime-template edition, not a weight fine-tune. Sizes
and hashes identify the exact validated files.

## Normal OpenZero Install

Review and run the hosted installer:

```bash
curl -fsSL https://openzero.talktoai.org/install.sh -o openzero-install.sh
curl -fsSL https://openzero.talktoai.org/install.sh.sha256 -o install.sh.sha256
sha256sum -c install.sh.sha256
less openzero-install.sh
bash openzero-install.sh
```

The installer pulls the verified Ministral Q5 runtime through Ollama and selects
it as both `ACTIVE_MODEL` and `NODE_RECOMMENDED_MODEL`. If the verified default
cannot be installed, OpenZero may offer the Gemma E4B compatibility path; it is
never promoted over an already working Ministral runtime.

## Direct Ollama Test

```bash
ollama run hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M
```

That command uses the same Hugging Face/Ollama name used by the OpenZero API,
autonomous runtime, ZERO ONE server integration, and Tab Pilot.

## Selection Boundary

- Ministral Q5 is the install, update, API, autonomous-run, and Tab Pilot default.
- Gemma E4B is retained only for compatibility with existing deployments.
- Existing operator-installed models are not deleted, but unverified/rejected
  research models are not promoted in default selectors or public copy.
- Deleting or switching models remains an explicit operator action.
- No benchmark or quality claim is implied by file size or quantization alone.
