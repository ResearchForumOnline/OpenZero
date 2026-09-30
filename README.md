# OpenZero 7.3 â€” independent, self-hosted AI nodes

OpenZero combines local model chat, a browser workspace, an OpenAI-compatible
API, durable automation runs, local knowledge and learning, source-improvement
candidates, and optional adapter training. Your node runs on your own Linux
machine or server. **There is no required TalkToAI server, central registration,
main node, or company-hosted database.**

[Source](https://github.com/ResearchForumOnline/OpenZero) Â·
[Releases](https://github.com/ResearchForumOnline/OpenZero/releases) Â·
[Install guide](openzero/docs/INSTALL.md) Â·
[Workbench](openzero/docs/WORKBENCH.md) Â·
[Node independence](openzero/docs/DECENTRALISED.md)

## What changes in 7.3

- Fresh installations use a local endpoint, an empty remote Hive endpoint,
  local mode, and sharing disabled.
- Upgrades remove exact retired owner-service defaults, preserving explicit
  user-owned endpoints and existing private state.
- Installers, checksums and runtime ZIPs come from versioned GitHub release
  assets. Mirrors can be operator-selected; GitHub is a distribution host,
  not an inference or federation coordinator.
- Tab Pilot 0.3.1 is distributed as a verified GitHub ZIP. Linux and Windows
  helpers prepare it for explicit **Load unpacked** approval, without forcing
  a browser policy or depending on an owner-hosted extension update service.
- The 7.2 improvement workspace remains: editable candidates, diffs, recorded
  checks, digest-bound apply and rollback; small adapter fixtures and optional
  local PEFT training do not automatically replace inference weights.

## Run your own AI machine

| Capability | Local implementation |
| --- | --- |
| Chat and models | Ollama routing, Ministral 8B runtime-template default, Gemma fallback, CPU profiles |
| Coding and tools | Files, bounded commands, archives, web reading, configured search, SSH tools |
| Durable runs | Checkpoints, budgets, stop/revoke, restart recovery, exact-action confirmations |
| API | Local OpenAI-compatible `/v1/chat/completions` with hashed machine keys |
| Browser control | Optional per-tab Tab Pilot grants and visible approval/stop controls |
| Knowledge | Local learning and operator-selected sharing; no mandatory remote catalogue |
| Source improvement | Separate source candidates, checks, reviewed apply and rollback |
| Training | Synthetic CPU fixture and optional LoRA/PEFT jobs with held-out evaluation |
| Voice | Optional local Piper/Voicebox; optional transcription dependencies |
| Offline operation | Bundle code, dependencies and models before disconnecting |

Models and software dependencies require downloads during online installation.
Optional web search, cloud APIs, remote models and operator-selected federation
need their respective external services. Local inference is not distributed
training, peer-to-peer GPU pooling or a guarantee of AGI.

## Install with checksum verification

On a Linux machine you administer, review the script before running:

```bash
mkdir -p openzero-bootstrap && cd openzero-bootstrap
curl -fL https://github.com/ResearchForumOnline/OpenZero/releases/download/v7.3.0/install.sh -o install.sh
curl -fL https://github.com/ResearchForumOnline/OpenZero/releases/download/v7.3.0/install.sh.sha256 -o install.sh.sha256
sha256sum -c install.sh.sha256
less install.sh
bash install.sh --desktop
```

For a headless node use `--server --no-tab-pilot`; `--skip-model` avoids the
large default-model download. The runtime archive is separately verified before
unpacking. A checksum detects corrupt/mismatched assets; it is not a detached
publisher signature. The default runtime and extension assets are pinned to
v7.3.0 so newer release assets cannot silently change this installer.

Open the panel at **http://localhost:1024**. Keep it on loopback, or access your
own remote node through an SSH tunnel/VPN. Never put private tokens into GitHub.

For a pre-7.3 installation, use the verified installer above with `--dir` set
to its existing path. This replaces the updater that previously depended on
the retired owner host. Once updated, use the local updater:

```bash
cd ~/openzero
bash update.sh --server --no-tab-pilot
```

The updater retrieves the latest installer and its checksum from GitHub.
`OPENZERO_INSTALLER_BASE_URL` selects your own installer mirror;
`OPENZERO_RELEASE_BASE_URL` selects your own runtime/extension asset mirror.
The mirror must provide the same filenames and matching checksum files.
For source development, clone this repository, create a Python virtual
environment, install `openzero/requirements.txt`, and run `openzero/run_brain.sh`.

## Browser extension

[Tab Pilot source and setup](browser-extension/README.md) Â·
[Verified ZIP](https://github.com/ResearchForumOnline/OpenZero/releases/download/v7.3.0/OpenZero-Tab-Pilot-v0.3.1.zip) Â·
[ZIP checksum](https://github.com/ResearchForumOnline/OpenZero/releases/download/v7.3.0/OpenZero-Tab-Pilot-v0.3.1.zip.sha256) Â·
[Windows helper](openzero/install-tab-pilot.ps1) Â·
[Linux helper](openzero/install-tab-pilot.sh)

The extension plans through your own loopback node; a remote node needs your
own SSH tunnel. Generate a scoped token in the local panel and enter it in
extension Options. Browser approval remains required. Existing managed installs
are not automatically uninstalled; their old policy should be removed by their
administrator before moving to the unpacked package.

## Models and research

The default is
[OpenZero Ministral3 8B Runtime Agent](https://huggingface.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF)
through Ollama as
`hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M`.
It uses unchanged upstream weights with an OpenZero runtime template.
[Gemma — Compatibility fallback](https://huggingface.co/shafire/Zero-Gemma4-E4B-OpenZero-GGUF),
[model guide](openzero/docs/MODELS.md),
[research archive](https://github.com/ResearchForumOnline/research), and
[Agentic GGUF collection](https://huggingface.co/collections/shafire/agentic-gguf-models)
remain separate public resources.

## Documentation and preservation

- [Configuration](openzero/docs/CONFIGURATION.md)
- [Architecture](openzero/docs/ARCHITECTURE.md)
- [API](openzero/docs/API.md)
- [Autonomous runs](openzero/docs/AUTONOMOUS_RUNS.md)
- [Direct peer notes and review inbox](openzero/docs/DIRECT-PEERS.md)
- [Downloads and releases](openzero/docs/DOWNLOADS_AND_RELEASES.md)
- [Offline release](openzero/docs/OFFLINE_RELEASE.md)
- [ZeroMint archived ISO parts and checksums](openzero/docs/ZEROMINT_OS.md)
- [Security model](openzero/docs/SECURITY_MODEL.md)
- [Changelog](openzero/CHANGELOG.md)

ZeroThink and Matrix bridge code is optional integration code for an
operator-owned deployment, not a requirement to use a retired public website.
Old release notes describe historical services; current installation guidance
is this README and the 7.3 guides.

## License and privacy

Source is available under the [OpenZero Community Source License](LICENSE).
Inspection, personal use, internal business use and contributions are permitted
under its terms; commercial resale or managed hosting needs written permission.
This is not an unrestricted open-source licence.

Release archives exclude `.env`, credentials, generated keys, databases,
private uploads, model stores, runtime knowledge and backups. Do not expose the
operator panel publicly without strong authentication and network controls.
See [SECURITY.md](SECURITY.md).
