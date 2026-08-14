# Configuration Reference

OpenZero reads configuration from `.env`, with defaults defined in `brain/openzero_config.py`.

Never commit real `.env` files.

## Runtime

| Key | Default | Purpose |
| --- | --- | --- |
| `OPENZERO_VERSION` | `7.1.0` | Version label. |
| `OPENZERO_DOMAIN` | `https://openzero.talktoai.org` | Public download/domain reference. |
| `SERVER_PORT` | `1024` | Panel/API port when configured. |
| `ACTIVE_MODEL` | `hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M` | Verified local runtime default. |
| `LOCAL_ENGINE` | `ollama` | Local engine selector. |
| `COMP_MODE` | `hybrid` | Computation mode. |

## Autonomous Runs

| Key | Default | Purpose |
| --- | --- | --- |
| `OPENZERO_AUTONOMY_PROFILE` | `standard` | Default run profile. `ultra` doubles skill budgets inside the unchanged hard caps and safety policy. |
| `OPENZERO_AUTONOMOUS_MAX_WORKERS` | `2` | Concurrent root-run workers, clamped from 1 to 16. Ultra defaults to 16 when the value is absent. Local model inference is always serialized. |

The profile is immutable after a run is created. Neither profile permits a
model to create child runs or bypass tool permissions and confirmations.
Because server-side Moltbot currently owns one browser page, browser-tagged runs
are serialized for their full workflow. Other workers can still coordinate
non-browser tools concurrently. The browser lane is bound to one run ID and is
held briefly across a fresh-confirmation pause so approval can consume the
exact inspected action. It is released when that confirmation window expires,
or when the run completes, errors, stops, or is revoked.

## CPU

| Key | Default |
| --- | --- |
| `OPENZERO_CPU_PROFILE` | `balanced` |
| `OPENZERO_OLLAMA_THREADS` | `0` |
| `OPENZERO_OLLAMA_NUM_BATCH` | `512` |
| `OPENZERO_OLLAMA_KEEP_ALIVE` | `10m` |
| `OPENZERO_OLLAMA_CONTEXT_WINDOW` | `0` |
| `BITNET_THREADS` | `0` |

`OPENZERO_OLLAMA_CONTEXT_WINDOW=0` uses the hardware-derived context window.
Set an explicit value such as `4096` when a smaller local prompt budget improves
latency; values are clamped from 2048 to 32768.

## Z-Spark Draft-Verify

| Key | Default | Purpose |
| --- | --- | --- |
| `OPENZERO_SPARK_MODE` | `auto` | `off`, `auto`, or `force` for the custom DSpark-inspired draft-verify lane. |
| `OPENZERO_SPARK_DRAFT_MODEL` | `qwen2.5:0.5b` | Small Ollama model used to draft before target verification. |
| `OPENZERO_SPARK_CONFIDENCE_THRESHOLD` | `0.58` | Confidence gate used by the prefix scheduler. |
| `OPENZERO_SPARK_MAX_DRAFT_TOKENS` | `384` | Maximum draft size before target verification. |
| `OPENZERO_SPARK_SHOW_TRACE` | `false` | Adds a short visible trace to local panel replies when enabled. |

## API Bridge

| Key | Default | Purpose |
| --- | --- | --- |
| `OPENZERO_API_ENABLED` | `false` | Enables local OpenAI-compatible API key route. |
| `OPENZERO_API_KEY_HASH` | blank | Hash of generated key. |
| `OPENZERO_API_KEY_HINT` | blank | Safe hint shown in UI. |

## Voice

| Key | Default |
| --- | --- |
| `VOICE_ENABLED` | `false` |
| `VOICE_AUTO_LISTEN` | `false` |
| `VOICE_STT_MODEL` | `base` |
| `VOICE_TTS_ENABLED` | `false` |
| `VOICE_TTS_BACKEND` | `piper` |
| `VOICE_TTS_VOICE` | `en_GB-alan-medium` |
| `VOICE_OUTPUT_DIR` | `voice` |

## Voicebox

| Key | Default |
| --- | --- |
| `VOICEBOX_ENABLED` | `false` |
| `VOICEBOX_URL` | `http://127.0.0.1:17493` |
| `VOICEBOX_PROFILE` | blank |
| `VOICEBOX_ENGINE` | `auto` |
| `VOICEBOX_LANGUAGE` | `en` |
| `VOICEBOX_PERSONALITY` | `false` |
| `VOICEBOX_FALLBACK_PIPER` | `true` |
| `VOICEBOX_TIMEOUT_SECONDS` | `180` |

## Hive

| Key | Default |
| --- | --- |
| `HIVE_MIND_ENABLED` | `false` |
| `OPENZERO_HIVE_URL` | `https://openzero.talktoai.org/api/hive` |
| `OPENZERO_HIVE_MODE` | `standalone` |
| `OPENZERO_HIVE_SHARE_MODE` | `manual` |
| `OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED` | `false` |
| `OPENZERO_HIVE_BLOCK_RISKY_CONTENT` | `true` |

## Provider Keys

| Key | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Optional Groq cloud route. |
| `SERPER_API_KEY` | Optional web search route. |
| `TELEGRAM_BOT_TOKEN` | Optional Telegram integration. |

Keep these empty unless you intentionally use the feature.
