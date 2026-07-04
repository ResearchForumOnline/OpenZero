# Z-Spark Draft-Verify Runtime

Z-Spark is OpenZero's custom draft-verify layer inspired by DSpark-style speculative decoding.
It is designed for CPU-first OpenZero nodes and the ZeroThink bridge.

## What DSpark Contributes

DeepSeek's DSpark paper describes speculative decoding with three important ideas:

- a lightweight draft path proposes candidate tokens;
- the larger target model verifies the candidates before final output;
- a confidence scheduler trims low-value verification work when the serving engine is under load.

The official DSpark implementation depends on trained draft checkpoints and target-model internals.
OpenZero does not claim to ship those private internals or DeepSeek checkpoints.

## What OpenZero Implements

OpenZero implements a practical, custom version at the agent/runtime level:

1. A small local Ollama model drafts a compact candidate answer.
2. OpenZero extracts or estimates a confidence score from the draft.
3. A confidence gate decides whether the draft should be treated as likely useful or weak context.
4. The active target model verifies, corrects, and writes the final answer.
5. If the draft model is missing, the node silently continues with target-only inference.

This is useful for ZeroThink because the web workbench can call a user-owned OpenZero node while still receiving a verified final answer from the selected local target model.

## Configuration

```env
OPENZERO_SPARK_MODE=auto
OPENZERO_SPARK_DRAFT_MODEL=qwen2.5:0.5b
OPENZERO_SPARK_CONFIDENCE_THRESHOLD=0.58
OPENZERO_SPARK_MAX_DRAFT_TOKENS=384
OPENZERO_SPARK_SHOW_TRACE=false
```

Modes:

| Mode | Behavior |
| --- | --- |
| `off` | Use only the target model. |
| `auto` | Use Z-Spark only when the draft model is installed and different from the target model. |
| `force` | Try Z-Spark whenever possible, but fall back safely if the draft call fails. |

Recommended draft models are small and CPU-friendly, such as `qwen2.5:0.5b`, a compact Gemma preset, or another installed local model that is clearly smaller than the active target model.

## ZeroThink Bridge

ZeroThink can request this path through the OpenAI-compatible endpoint by adding:

```json
{
  "openzero_spark": "auto"
}
```

The response includes an `openzero_spark` metadata object with the mode, draft model, readiness, confidence, and scheduler result.

## Limits

Z-Spark is not guaranteed to make every CPU request faster. On very small machines, running both a draft and target model can be slower than target-only inference. The default `auto` mode prevents that cost unless the draft model is actually present.

For true token-level speculative decoding speedups, OpenZero would need model-runtime support for logits, acceptance sampling, and trained draft checkpoints. Z-Spark is the practical open-core bridge until those local runtimes expose the needed low-level hooks.
