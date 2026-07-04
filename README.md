# OpenZero

<p align="center">
  <img src="docs/images/openzero-5-4-terminal-ui.png" alt="OpenZero 5.4 terminal-style local AI node interface" width="960">
</p>

<p align="center">
  <a href="https://openzero.talktoai.org/"><img alt="Website" src="https://img.shields.io/badge/website-openzero.talktoai.org-19f2b4?style=for-the-badge"></a>
  <a href="https://docs.talktoai.org/openzero-user-manual/"><img alt="Manual" src="https://img.shields.io/badge/manual-read_online-24d3ff?style=for-the-badge"></a>
  <a href="https://github.com/ResearchForumOnline/OpenZero/releases"><img alt="GitHub releases" src="https://img.shields.io/github/v/release/ResearchForumOnline/OpenZero?include_prereleases&label=release&style=for-the-badge"></a>
  <a href="openzero/docs/INSTALL.md"><img alt="Install" src="https://img.shields.io/badge/install-Linux_CPU_first-f6d365?style=for-the-badge"></a>
  <a href="openzero/docs/API.md"><img alt="API" src="https://img.shields.io/badge/API-OpenAI_compatible-8b5cf6?style=for-the-badge"></a>
</p>

**OpenZero** is a local-first AI node, operator Super Panel, OpenAI-compatible local API, and self-hosted automation runtime for people who want their own AI machine instead of only a hosted chatbot tab.

It is built for ordinary Linux servers first. GPU acceleration is welcome, but the default route is practical CPU operation through Ollama, compact model choices, CPU profiles, local browser tooling, optional voice, offline release packaging, and a bridge into ZeroThink.

Public site: [openzero.talktoai.org](https://openzero.talktoai.org/)

Docs: [docs.talktoai.org/openzero-user-manual](https://docs.talktoai.org/openzero-user-manual/)

ZeroThink bridge: [zerothink.talktoai.org](https://zerothink.talktoai.org/)

## What You Can Build With It

OpenZero lets a user or business install a private AI node on a server, VPS, desktop Linux box, lab machine, or local network host, then use it for:

- local LLM chat through Ollama, Gemma, Qwen, GGUF-style routes, and CPU-friendly profiles;
- OpenAI-compatible `/v1/chat/completions` calls from apps, scripts, tools, and ZeroThink;
- a web Super Panel for model controls, runtime health, API keys, voice, settings, and local status;
- ZeroThink Neural Vault integration so ZeroThink can use a user-owned OpenZero machine;
- Moltbot page reading and browser-style web inspection for agent workflows;
- optional Voicebox or Piper speech routes for local voice output;
- optional BitNet 1-bit CPU lane for lower-power model experiments;
- Z-Spark draft-verify routing inspired by DSpark-style speculative decoding;
- offline release bundles for air-gapped or low-connectivity installs;
- privacy-aware Hive/federation client controls where sharing is explicit, not silent.

## Quick Install

Review the installer before running it:

```bash
curl -fsSL https://openzero.talktoai.org/install.sh -o openzero-install.sh
less openzero-install.sh
bash openzero-install.sh
```

Fast install on a machine you control:

```bash
curl -fsSL https://openzero.talktoai.org/install.sh | bash
```

Alternative GitHub raw install:

```bash
curl -fsSL https://raw.githubusercontent.com/ResearchForumOnline/OpenZero/main/openzero/install.sh | bash
```

Open the Super Panel after install:

```text
http://localhost:1024
```

## Download And Release Links

| Need | Link |
| --- | --- |
| Latest GitHub source archive | [Download ZIP](https://github.com/ResearchForumOnline/OpenZero/archive/refs/heads/main.zip) |
| GitHub releases | [OpenZero releases](https://github.com/ResearchForumOnline/OpenZero/releases) |
| Hosted installer | [openzero.talktoai.org/install.sh](https://openzero.talktoai.org/install.sh) |
| Update script | [openzero/update.sh](openzero/update.sh) |
| Download guide | [openzero/docs/DOWNLOADS_AND_RELEASES.md](openzero/docs/DOWNLOADS_AND_RELEASES.md) |
| Offline release guide | [openzero/docs/OFFLINE_RELEASE.md](openzero/docs/OFFLINE_RELEASE.md) |
| Public release checklist | [docs/PUBLIC_RELEASE_CHECKLIST.md](docs/PUBLIC_RELEASE_CHECKLIST.md) |
| Changelog | [openzero/CHANGELOG.md](openzero/CHANGELOG.md) |

## Capability Map

| Area | What OpenZero Provides |
| --- | --- |
| Super Panel | Browser UI for models, Hive controls, voice, OpenZero API key management, local runtime status, and settings. |
| Local LLM lane | Ollama-backed model routing with Gemma defaults, custom model names, repair actions, install buttons, and model status checks. |
| CPU profiles | Compact, balanced, and max CPU modes with thread, batch, context, and keep-warm controls. |
| Z-Spark | Custom draft-verify layer: a small local model drafts, OpenZero estimates confidence, and the active model verifies or rewrites. |
| OpenAI-compatible API | `/v1/chat/completions` for local model calls with OpenZero API keys. |
| ZeroThink bridge | Create a machine API key in OpenZero and paste it into ZeroThink Neural Vault to route suitable work through your own node. |
| Moltbot | Local page inspection and text extraction path for research, webpage reading, and agent actions. |
| Voice | Piper offline speech by default; optional Voicebox backend for richer local voice workflows. |
| BitNet | Optional Microsoft BitNet-style 1-bit CPU lane for low-power experiments. |
| Offline release | Builder path for source, Python wheels, Node runtime, PM2, Moltbot dependencies, Ollama binary, and optional model stores. |
| Security posture | Local-first defaults, hashed API keys, explicit sharing controls, no browser-supplied OpenZero endpoint trust. |
| Docs | Install, API, CPU runtime, security model, configuration, troubleshooting, premium extension boundary, and roadmap. |

## New Runtime Highlights

### Z-Spark Draft-Verify

OpenZero now includes **Z-Spark**, a custom CPU-first draft-verify layer inspired by DSpark-style speculative decoding. It is not the official DeepSeek DSpark checkpoint path. Instead:

1. a small local draft model proposes a compact candidate;
2. OpenZero extracts or estimates a confidence score;
3. the target model verifies, corrects, and writes the final answer;
4. the request falls back safely when the draft model is missing or too weak.

ZeroThink can request this path through the OpenAI-compatible bridge using:

```json
{
  "openzero_spark": "auto"
}
```

Read more: [openzero/docs/ZSPARK.md](openzero/docs/ZSPARK.md)

### OpenZero Inside ZeroThink

One of the strongest ecosystem features is the bridge between ZeroThink and OpenZero:

1. install OpenZero on your own machine or server;
2. create an OpenZero API key in the Super Panel;
3. add it to ZeroThink Neural Vault;
4. use ZeroThink as the polished web workbench while routing suitable work through your own local/self-hosted node.

Read more: [openzero/docs/ZEROTHINK_BRIDGE.md](openzero/docs/ZEROTHINK_BRIDGE.md)

### Moltbot Web Reading

OpenZero includes Moltbot integration for controlled page reading and website inspection. This gives the node a practical web-aware lane without turning every request into a cloud dependency.

### Voicebox And Piper Voice

OpenZero keeps Piper as the offline fallback and can connect to a local Voicebox service when richer voice workflows are installed.

Read more: [openzero/docs/VOICEBOX.md](openzero/docs/VOICEBOX.md)

## API Example

After creating an OpenZero API key in the Super Panel:

```bash
curl http://YOUR-OPENZERO-HOST:1024/v1/chat/completions \
  -H "Authorization: Bearer ztapi_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e4b",
    "openzero_spark": "auto",
    "messages": [
      {"role": "user", "content": "Say OpenZero API OK"}
    ]
  }'
```

Read more: [openzero/docs/API.md](openzero/docs/API.md)

## Install Options

| Install lane | Command or guide |
| --- | --- |
| Standard Linux node | `curl -fsSL https://openzero.talktoai.org/install.sh \| bash` |
| Desktop-friendly install | `curl -fsSL https://openzero.talktoai.org/install.sh \| bash -s -- --desktop` |
| Optional BitNet lane | `curl -fsSL https://openzero.talktoai.org/install.sh \| bash -s -- --bitnet` |
| Optional voice dependencies | `curl -fsSL https://openzero.talktoai.org/install.sh \| bash -s -- --voice` |
| Update existing node | `curl -fsSL https://openzero.talktoai.org/update.sh \| bash` |
| Offline install | [openzero/docs/OFFLINE_RELEASE.md](openzero/docs/OFFLINE_RELEASE.md) |
| Developer setup | [Local Development](#local-development) |

## Local Development

```bash
git clone https://github.com/ResearchForumOnline/OpenZero.git
cd OpenZero/openzero
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m compileall brain hivemind
python brain/app.py
```

Start from `openzero/.env.example` and keep real `.env` files out of Git.

## Repository Map

- `openzero/` - installable OpenZero node, panel, API, scripts, Moltbot, Hive client code, and docs.
- `openzero/brain/` - Flask app, local API, model routing, runtime checks, security helpers, and Z-Spark logic.
- `openzero/templates/` - Super Panel UI.
- `openzero/moltbot/` - local browser/page-reading support.
- `openzero/hivemind/` - public local federation/client-side boundary code.
- `openzero/docs/` - install, API, architecture, CPU runtime, bridge, voice, security, troubleshooting, and roadmap docs.
- `docs/` - public release, security model, and private Hive boundary notes for this GitHub repo.

## Documentation

- [Install Guide](openzero/docs/INSTALL.md)
- [Downloads And Releases](openzero/docs/DOWNLOADS_AND_RELEASES.md)
- [Architecture](openzero/docs/ARCHITECTURE.md)
- [CPU Runtime](openzero/docs/CPU_RUNTIME.md)
- [Z-Spark Draft-Verify](openzero/docs/ZSPARK.md)
- [ZeroThink Bridge](openzero/docs/ZEROTHINK_BRIDGE.md)
- [API Reference](openzero/docs/API.md)
- [Voicebox Integration](openzero/docs/VOICEBOX.md)
- [Offline Release](openzero/docs/OFFLINE_RELEASE.md)
- [Security Model](openzero/docs/SECURITY_MODEL.md)
- [Premium Extensions](openzero/docs/PREMIUM_EXTENSIONS.md)
- [Configuration Reference](openzero/docs/CONFIGURATION.md)
- [Troubleshooting](openzero/docs/TROUBLESHOOTING.md)
- [FAQ](openzero/docs/FAQ.md)
- [Roadmap](openzero/docs/ROADMAP.md)

## Featured Ecosystem Video

[![TalkToAI: Sovereignty Through ZeroThink and OpenZero Infrastructure](https://i.ytimg.com/vi/R52hsRdCmSM/hqdefault.jpg)](https://www.youtube.com/watch?v=R52hsRdCmSM)

Watch the ecosystem overview: [TalkToAI: Sovereignty Through ZeroThink and OpenZero Infrastructure](https://www.youtube.com/watch?v=R52hsRdCmSM). It shows how ZeroThink, OpenZero, local-first infrastructure, and the wider TalkToAI product stack fit together.

## Search-Friendly Topics

OpenZero is for people searching for:

- self-hosted AI agent
- local AI node
- CPU-first LLM server
- Ollama web panel
- OpenAI-compatible local API
- private AI assistant server
- ZeroThink local machine bridge
- local-first AI infrastructure
- AI agent with web reading
- offline AI release bundle
- Linux AI operator panel
- local voice AI server

## Related TalkToAI Projects

- [ZeroThink](https://zerothink.talktoai.org/) - web AI workbench and Neural Vault.
- [TalkToAI Docs](https://docs.talktoai.org/) - ecosystem manuals, guides, PDFs, and project map.
- [FreeWebPanel](https://github.com/ResearchForumOnline/FreeWebPanel) - free-core Linux hosting control panel.
- [ZSEC](https://github.com/ResearchForumOnline/ZSEC) - security-only Linux update utility.
- [FrontDeskAgent](https://github.com/ResearchForumOnline/FrontDeskAgent) - self-hosted AI receptionist.

## Open Core And Premium Boundary

This public repository contains installable open-core code. Production-only Hive HQ server internals, database credentials, private infrastructure settings, model weights, generated keys, runtime vaults, backups, and release archives are not committed here.

Code published to GitHub is viewable by design. The professional pattern for private or commercial extensions is:

- keep open-core node logic public here;
- keep premium modules in private repositories, hosted APIs, private package feeds, or compiled/signed extension bundles;
- expose stable extension hooks and configuration in the open core;
- verify private extensions with checksums, signatures, and license tokens;
- document what is open and what is commercial.

Read more: [openzero/docs/PREMIUM_EXTENSIONS.md](openzero/docs/PREMIUM_EXTENSIONS.md)

## Safety And Privacy Defaults

OpenZero is operator software. Treat it like a local admin tool:

- do not expose the Super Panel publicly without strong network controls;
- do not commit `.env` files or API keys;
- rotate OpenZero API keys if exposed;
- prefer local-only, private LAN, SSH tunnel, or VPN access for admin surfaces;
- review [SECURITY.md](SECURITY.md) and [openzero/docs/SECURITY_MODEL.md](openzero/docs/SECURITY_MODEL.md).

## License

This repository is source-available under the OpenZero Community Source License in [LICENSE](LICENSE). It is intended for inspection, learning, personal use, internal business use, and contributions. Commercial resale, managed hosting, or claiming the project as your own product requires written permission.
