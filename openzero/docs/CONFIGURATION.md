# Configuration Reference

OpenZero reads configuration from `.env`, with defaults defined in `brain/openzero_config.py`.

Never commit real `.env` files.

## Runtime

| Key | Default | Purpose |
| --- | --- | --- |
| `OPENZERO_VERSION` | `5.4.0` | Version label. |
| `OPENZERO_DOMAIN` | `https://openzero.talktoai.org` | Public download/domain reference. |
| `SERVER_PORT` | `1024` | Panel/API port when configured. |
| `ACTIVE_MODEL` | `gemma4:e4b` | Preferred local model. |
| `LOCAL_ENGINE` | `ollama` | Local engine selector. |
| `COMP_MODE` | `hybrid` | Computation mode. |

## CPU

| Key | Default |
| --- | --- |
| `OPENZERO_CPU_PROFILE` | `balanced` |
| `OPENZERO_OLLAMA_THREADS` | `0` |
| `OPENZERO_OLLAMA_NUM_BATCH` | `512` |
| `OPENZERO_OLLAMA_KEEP_ALIVE` | `10m` |
| `BITNET_THREADS` | `0` |

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
