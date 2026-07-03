# CPU Runtime

OpenZero is designed to be useful on CPU-first machines. It does not require an expensive GPU to be valuable.

## Profiles

| Profile | Best For | Behavior |
| --- | --- | --- |
| `compact` | Small VPS, low-power boxes, shared machines | Caps local inference threads conservatively. |
| `balanced` | Default installs | Uses most cores but leaves breathing room for the OS. |
| `max` | Dedicated AI boxes | Uses all detected logical cores. |

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `OPENZERO_CPU_PROFILE` | `balanced` | CPU profile selector. |
| `OPENZERO_OLLAMA_THREADS` | `0` | `0` means automatic. Positive values override thread count. |
| `OPENZERO_OLLAMA_NUM_BATCH` | `512` | Batch size passed to Ollama. Clamped internally. |
| `OPENZERO_OLLAMA_KEEP_ALIVE` | `10m` | Keeps the local model warm for follow-up calls. |
| `BITNET_THREADS` | `0` | `0` means follow the OpenZero profile. |

## Where It Applies

The CPU profile is used by:

- normal local Ollama chat;
- `/v1/chat/completions`;
- BitNet runtime calls where enabled;
- the system prompt status line so the agent knows its node profile.

## Practical Guidance

Use `compact` when:

- the server has 1-4 vCPU;
- other websites run on the same machine;
- you want predictable responsiveness.

Use `balanced` when:

- OpenZero is on a normal VPS or desktop;
- you want good speed without starving the OS.

Use `max` when:

- the box is dedicated to inference;
- temporary CPU saturation is acceptable.

## Models And Size

Stay practical. CPU-first users should prefer smaller quantized models. Large models can install but may respond slowly or fail on low RAM.

OpenZero is opinionated toward working installs over impressive model names.

