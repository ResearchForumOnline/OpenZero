# API Reference

OpenZero exposes local API routes for panel actions, local model calls, voice, model management, and diagnostics.

## Authentication

The OpenAI-compatible API requires an OpenZero API key.

Create or rotate it in the Super Panel. The key is displayed once.

```http
Authorization: Bearer ztapi_your_key_here
```

## OpenAI-Compatible Chat

```http
POST /v1/chat/completions
```

Example:

```bash
curl http://YOUR-OPENZERO-HOST:1024/v1/chat/completions \
  -H "Authorization: Bearer ztapi_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e4b",
    "messages": [
      {"role": "user", "content": "Say OpenZero API OK"}
    ],
    "temperature": 0.6,
    "max_tokens": 512
  }'
```

## Config

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/config` | GET | Read safe config/status values for the panel. |
| `/api/config/bulk` | POST | Save multiple settings. |
| `/update_config` | POST | Legacy config update path. |

## Models

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/models` | GET | List local/cloud/custom model status. |
| `/api/install_local_model` | POST | Pull a supported local Ollama model. |
| `/api/delete_model` | POST | Delete a local model/package. |
| `/api/pull_weights` | POST | Pull a direct GGUF/custom model package. |
| `/api/ollama/status` | GET | Check Ollama status. |
| `/api/ollama/upgrade` | POST | Refresh Ollama runtime. |
| `/api/repair_local_brain` | POST | Attempt local model/runtime repair. |

## BitNet

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/bitnet/status` | GET | Check BitNet add-on state. |
| `/api/bitnet/install` | POST | Install/activate BitNet lane. |
| `/api/bitnet/repair` | POST | Repair BitNet lane. |
| `/api/bitnet/remove` | POST | Remove/deactivate BitNet lane. |

## Voice

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/voice/status` | GET | Read voice stack status. |
| `/api/voice/speak` | POST | Speak text through Piper or Voicebox. |
| `/api/voice/transcribe` | POST | Transcribe uploaded audio when faster-whisper is installed. |
| `/api/voice/voicebox/status` | GET | Check Voicebox health. |
| `/api/voice/voicebox/profiles` | GET | Read available Voicebox profiles. |

## Hive And Local Learning

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/hive/status` | GET | Read Hive/local spool status. |
| `/api/hive/replay` | POST | Replay queued federation events. |
| `/api/hive/clear_queue` | POST | Clear unsent queue. |
| `/api/hive/clear_local_events` | POST | Clear local continuity events. |
| `/api/hive/share_last` | POST | Share last chat when enabled. |
| `/api/hive/pause` | POST | Pause Hive. |
| `/api/hive/resume` | POST | Resume Hive. |

## Uploads And Memory

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/upload` | POST | Upload a file for local context. |
| `/api/clear_memory` | POST | Clear short-term uploaded context. |

## Operational Warning

Treat local endpoints as admin/operator endpoints unless specifically designed for public use. Protect them with network controls.

