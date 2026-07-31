# OpenZero Models

OpenZero installs one verified default model and exposes two optional Qwen
experiments. A normal installation or update selects only OpenZero Gemma. The
Qwen files are never pulled or activated unless the operator explicitly asks
for one through the Super Panel or API.

## Verified Release Matrix

| Model | GGUF file | Size | SHA-256 | OpenZero runtime name | Policy |
| --- | --- | ---: | --- | --- | --- |
| [Zero-Gemma4 E4B OpenZero](https://huggingface.co/shafire/Zero-Gemma4-E4B-OpenZero-GGUF) | `Zero-Gemma4-E4B-OpenZero-Q5_K_M-F16-Merged.gguf` | 5,865,235,584 bytes (5.46 GiB) | `84fd62ff6c5f0abe14dd2c6135e56800df4bc4a0b9d4cd8d9f26c36b28aa190b` | `openzerogemma:latest` | Default |
| [Zero-Qwen3 8B OpenZero Q5_K_M](https://huggingface.co/shafire/Zero-Qwen3-8B-OpenZero-GGUF/blob/main/Zero-Qwen3-8B-OpenZero-Q5_K_M.gguf) | `Zero-Qwen3-8B-OpenZero-Q5_K_M.gguf` | 5,851,112,224 bytes (5.45 GiB) | `390464f750b5cb53da298848adc05839c1fd40404a74cd5f800cad9612d17d59` | `zero-qwen3-q5:latest` | Optional |
| [Zero-Qwen3 8B OpenZero F16](https://huggingface.co/shafire/Zero-Qwen3-8B-OpenZero-GGUF/blob/main/Zero-Qwen3-8B-OpenZero-FUSED-F16.gguf) | `Zero-Qwen3-8B-OpenZero-FUSED-F16.gguf` | 14,837,080,864 bytes (13.82 GiB) | `c69cdbe2c3be4a08efb7d56c115abad2b83cfcf398f80a246ae374131ca58232` | `zero-qwen3-f16:latest` | Optional |

The releases are grouped in the
[Agentic GGUF Models collection](https://huggingface.co/collections/shafire/agentic-gguf-models).
Sizes and digests above identify the exact files expected by the current
OpenZero release. The installer rejects an unexpected size, checksum, or GGUF
header before model creation.

## Normal OpenZero Install

Review and run the hosted installer:

```bash
curl -fsSL https://openzero.talktoai.org/install.sh -o openzero-install.sh
less openzero-install.sh
bash openzero-install.sh
```

This creates `openzerogemma:latest` and selects it as the default runtime. Use
the Super Panel model controls if you deliberately want one of the optional
Qwen releases.

## Direct Ollama Test

Hugging Face GGUF integration can run the published repositories directly:

```bash
ollama run hf.co/shafire/Zero-Gemma4-E4B-OpenZero-GGUF
ollama run hf.co/shafire/Zero-Qwen3-8B-OpenZero-GGUF:Q5_K_M
```

Those commands use Hugging Face/Ollama names. The OpenZero aliases in the table
are created by OpenZero's verified model injection flow and are the names used
by its API, autonomous runtime, and Tab Pilot.

## Selection Boundary

- `openzerogemma:latest` is the install, update, API, autonomous-run, and Tab
  Pilot default.
- Qwen Q5 and Qwen F16 are visible operator choices, not hidden downloads.
- Installing an optional model does not silently make it the default.
- Deleting or switching models remains an explicit operator action.
- No benchmark or quality claim is implied by the file size or quantization.
