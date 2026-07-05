# OpenZero

OpenZero is a local-first AI node for people who want more than a hosted chatbot tab. It combines a web Super Panel, local LLM routing, CPU-friendly model controls, an OpenAI-compatible local API, Moltbot browser tooling, optional Voicebox speech, optional CallChat Matrix bot support, optional BitNet, private local learning, and a ZeroThink bridge.

OpenZero is designed for normal Linux servers first. GPU acceleration is welcome when available, but the default path is practical CPU operation through Ollama, compact model choices, and a panel that exposes the important controls without forcing every user into command-line tuning.

## Why This Exists

Most AI products give users a remote chat window. OpenZero gives users a node.

That matters because a node can:

- run local models through Ollama;
- expose a local OpenAI-compatible API;
- create an API key that can be pasted into ZeroThink Neural Vault;
- route ZeroThink work through a user's own machine;
- browse and inspect pages through Moltbot;
- speak through Piper or Voicebox;
- power a CallChat Matrix room agent through the local API;
- work in normal server environments;
- be packaged for offline or air-gapped installs;
- keep private state local unless the operator explicitly enables sharing.

The result is a hybrid workflow: use ZeroThink as the polished web workbench, then connect OpenZero when you want your own CPU/server/local-model lane.

## Quick Links

- Main site: https://talktoai.org/
- OpenZero download host: https://openzero.talktoai.org/
- ZeroThink: https://zerothink.talktoai.org/
- Docs: https://docs.talktoai.org/
- OpenZero manual: https://docs.talktoai.org/openzero-user-manual/
- Voicebox upstream: https://github.com/jamiepine/voicebox
- Ecosystem video: https://www.youtube.com/watch?v=R52hsRdCmSM

## Featured Ecosystem Video

[![TalkToAI: Sovereignty Through ZeroThink and OpenZero Infrastructure](https://i.ytimg.com/vi/R52hsRdCmSM/hqdefault.jpg)](https://www.youtube.com/watch?v=R52hsRdCmSM)

This video is the broad overview for the TalkToAI stack: ZeroThink as the web workbench, OpenZero as the user-owned CPU/server node, and the wider infrastructure path for local-first AI.

## What Is Included

| Area | What OpenZero Provides |
| --- | --- |
| Super Panel | Browser UI for models, Hive controls, voice, API key management, local runtime status, and settings. |
| Local LLM lane | Ollama-backed Gemma defaults with model repair, install buttons, custom GGUF URL support, and CPU profile tuning. |
| CPU profiles | Compact, balanced, and max CPU modes with thread, batch, and keep-warm controls. |
| Z-Spark | Optional OpenZero draft-verify layer inspired by DSpark: a small local drafter proposes a candidate, then the active target model verifies and writes the final answer. |
| OpenAI-compatible API | `/v1/chat/completions` for local Ollama model calls with an OpenZero API key. |
| ZeroThink bridge | Create an OpenZero API key and paste it into ZeroThink Neural Vault to let ZeroThink use your own node. |
| Moltbot | Local browser/text extraction path for page inspection, research, and web-aware agent actions. |
| Voice | Piper offline speech by default; optional Voicebox backend for richer local voice studio workflows. |
| CallChat bot | Matrix room agent bridge using OpenZero as the local brain and Voicebox for optional command-triggered audio. |
| BitNet | Optional Microsoft BitNet 1-bit CPU lane for lower-power nodes. |
| Offline release | Builder path for packaging code, wheels, Node runtime, PM2, Ollama binary, Moltbot deps, and model store. |
| Security posture | Local-first defaults, API key hashing, explicit sharing controls, and no browser-supplied OpenZero endpoint trust. |

## Install

Fresh Linux install:

```bash
curl -sL https://openzero.talktoai.org/install | bash
```

Desktop install:

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --desktop
```

Install with optional BitNet lane:

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --bitnet
```

Install with optional local voice dependencies:

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --voice
```

Update an existing node:

```bash
curl -sL https://openzero.talktoai.org/update.sh | bash
```

See [docs/INSTALL.md](docs/INSTALL.md) for the full install guide.

## Connect OpenZero To ZeroThink

1. Install and open OpenZero.
2. Go to the Super Panel.
3. Create or rotate the local OpenZero API key.
4. Copy the key once.
5. Open ZeroThink Neural Vault.
6. Paste the key as your OpenZero Machine API Key.
7. Use ZeroThink with your own local/self-hosted OpenZero node.

This is one of the most important features in the ecosystem: a polished web AI workbench can route suitable work through a user-owned local AI machine.

Read more in [docs/ZEROTHINK_BRIDGE.md](docs/ZEROTHINK_BRIDGE.md).

## CPU-First Runtime

OpenZero does not assume an expensive GPU. The current runtime exposes:

- `OPENZERO_CPU_PROFILE=balanced|compact|max`
- `OPENZERO_OLLAMA_THREADS=0`
- `OPENZERO_OLLAMA_NUM_BATCH=512`
- `OPENZERO_OLLAMA_KEEP_ALIVE=10m`
- `OPENZERO_SPARK_MODE=auto`
- `OPENZERO_SPARK_DRAFT_MODEL=qwen2.5:0.5b`
- `BITNET_THREADS=0`

The same profile logic is used by normal chat, the local `/v1` route, and BitNet where relevant.

Read more in [docs/CPU_RUNTIME.md](docs/CPU_RUNTIME.md).

## Z-Spark Draft-Verify

OpenZero now includes a custom Z-Spark runtime inspired by DSpark-style speculative decoding. It is not the official DeepSeek DSpark checkpoint path. Instead, it is an open-core CPU-first implementation: a lightweight local model drafts, OpenZero estimates confidence, and the active model verifies or rewrites the result.

ZeroThink can request the lane through the OpenAI-compatible bridge with `openzero_spark: "auto"`.

Read more in [docs/ZSPARK.md](docs/ZSPARK.md).

## Optional Voicebox Integration

OpenZero can route text-to-speech through Voicebox when Voicebox is running locally, while keeping Piper as the offline fallback.

Default Voicebox URL:

```text
http://127.0.0.1:17493
```

OpenZero exposes:

- `GET /api/voice/voicebox/status`
- `GET /api/voice/voicebox/profiles`
- `POST /api/voice/speak`

Read more in [docs/VOICEBOX.md](docs/VOICEBOX.md).

## CallChat Zero Bot Bridge

OpenZero can power `@zero:callchat.org`, a CallChat Matrix bot that answers approved rooms through the local `/v1/chat/completions` endpoint and can use Voicebox for audio replies.

Read more in [docs/CALLCHAT_ZERO_BOT.md](docs/CALLCHAT_ZERO_BOT.md).

## API Example

After creating an OpenZero API key in the Super Panel:

```bash
curl http://YOUR-OPENZERO-HOST:1024/v1/chat/completions \
  -H "Authorization: Bearer ztapi_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e4b",
    "messages": [
      {"role": "user", "content": "Say OpenZero API OK"}
    ]
  }'
```

See [docs/API.md](docs/API.md).

## Open Core And Premium Boundary

This public repository contains the installable open-core code. Any premium/private code should not be committed here if the goal is to stop people viewing or copying it. Code published to GitHub is viewable by design.

The recommended professional pattern is:

- keep open-core node logic in this repository;
- keep premium modules in private repositories, private package feeds, hosted APIs, or compiled/signed extension bundles;
- expose stable extension hooks and configuration in the open core;
- verify private extensions with checksums/signatures and license tokens;
- document what is open and what is commercial.

See [docs/PREMIUM_EXTENSIONS.md](docs/PREMIUM_EXTENSIONS.md).

## Documentation Map

- [Install Guide](docs/INSTALL.md)
- [Downloads And Releases](docs/DOWNLOADS_AND_RELEASES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [CPU Runtime](docs/CPU_RUNTIME.md)
- [Z-Spark Draft-Verify](docs/ZSPARK.md)
- [ZeroThink Bridge](docs/ZEROTHINK_BRIDGE.md)
- [API Reference](docs/API.md)
- [Voicebox Integration](docs/VOICEBOX.md)
- [CallChat Zero Bot Bridge](docs/CALLCHAT_ZERO_BOT.md)
- [Offline Release](docs/OFFLINE_RELEASE.md)
- [Security Model](docs/SECURITY_MODEL.md)
- [Premium Extensions](docs/PREMIUM_EXTENSIONS.md)
- [Configuration Reference](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [FAQ](docs/FAQ.md)
- [Roadmap](docs/ROADMAP.md)

## Project Status

OpenZero is evolving quickly. Expect frequent improvements around:

- easier CPU model setup;
- stronger docs and onboarding;
- ZeroThink bridge behavior;
- optional local voice workflows;
- offline packaging;
- panel UI polish;
- security hardening and diagnostics.

## Security

OpenZero can run tools and local commands depending on how it is installed and configured. Treat it as operator software, not a toy widget.

- Do not expose the Super Panel publicly without strong network controls.
- Do not commit `.env`.
- Rotate OpenZero API keys if exposed.
- Prefer local-only or VPN access for admin surfaces.
- Review [SECURITY.md](SECURITY.md) and [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Contributing

Contributions are welcome when they improve install reliability, docs, CPU performance, UI clarity, security posture, tests, or compatibility. Start with [CONTRIBUTING.md](CONTRIBUTING.md).
