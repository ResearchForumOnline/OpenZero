# API Reference

OpenZero exposes local API routes for panel actions, local model calls, voice, model management, and diagnostics.

## Authentication

The OpenAI-compatible API requires an OpenZero API key.

Create or rotate it from a direct session on the OpenZero host. Key rotation is
intentionally rejected when the request arrives through a proxy or remote client.
The key is displayed once.

```http
Authorization: Bearer oz_your_key_here
```

## OpenAI-Compatible Chat

```http
POST /v1/chat/completions
```

Example:

```bash
curl http://YOUR-OPENZERO-HOST:1024/v1/chat/completions \
  -H "Authorization: Bearer oz_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openzerogemma:latest",
    "messages": [
      {"role": "user", "content": "Say OpenZero API OK"}
    ],
    "temperature": 0.6,
    "max_tokens": 512,
    "openzero_spark": "auto"
  }'
```

`openzero_spark` is optional. Accepted values are `off`, `auto`, and `force`. In `auto` mode, OpenZero uses the Z-Spark draft-verify layer only when the configured small draft model is installed. The response includes an `openzero_spark` metadata object so ZeroThink or another client can see whether the path was used.

## OpenAI-Compatible Models

```http
GET /v1/models
```

This authenticated route returns the local Ollama models currently available to
OpenAI-compatible clients. It uses the same bearer key as chat completions.

## Brave Tab Pilot

Tab Pilot uses a separate scoped bearer token. It can list models and call the
browser planner, but it cannot call general chat completions.

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/tab-pilot/key` | POST | Direct-loopback create/rotate/revoke of a scoped Tab Pilot token. |
| `/v1/browser/plan` | POST | Return one validated browser action from a bounded task and untrusted page snapshot. |

The Linux `install-tab-pilot.sh` helper rotates this scoped token and delivers
it through Brave managed storage. The planner uses a browser-only prompt and
performs at most one repair attempt when model output is malformed.

## Config

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/config` | GET | Read safe config/status values for the panel. |
| `/api/config/bulk` | POST | Save multiple settings. |
| `/update_config` | POST | Legacy config update path. |

## Models

| Route | Method | Purpose |
| --- | --- | --- |
| `/v1/models` | GET | List installed local models for authenticated OpenAI-compatible clients. |
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

## Bounded Autonomous Runs

These routes require either a direct loopback request without proxy forwarding
headers or a valid OpenZero bearer key.

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/agent/runs` | POST | Create a durable, budgeted autonomous run. |
| `/api/agent/runs` | GET | List redacted autonomous run states for the Super Panel. |
| `/api/agent/runs/<run-id>` | GET | Read one run, its bounded trace tail, pending action, budgets, and control links. |
| `/api/agent/runs/<run-id>/stop` | POST | Request a safe-boundary stop. |
| `/api/agent/runs/<run-id>/resume` | POST | Resume an eligible run, optionally with new explicit budgets. |
| `/api/agent/runs/<run-id>/revoke` | POST | Permanently revoke this run's authority. |
| `/api/agent/runs/<run-id>/approve` | POST | Confirm one exact pending-action fingerprint for a short time. |

See [AUTONOMOUS_RUNS.md](AUTONOMOUS_RUNS.md) for restart recovery, budget caps,
confirmation behavior, run states, and examples.

## Uploads And Memory

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/upload` | POST | Upload a file for local context. |
| `/api/clear_memory` | POST | Clear short-term uploaded context. |

## Operational Warning

Treat local endpoints as admin/operator endpoints unless specifically designed for public use. Protect them with network controls.
