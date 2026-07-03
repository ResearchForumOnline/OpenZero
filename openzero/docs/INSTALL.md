# Install Guide

This guide covers the normal OpenZero install path, update path, optional CPU/model features, and where to go after the first boot.

## Supported Targets

OpenZero is designed for Linux-first operation.

Recommended environments:

- Ubuntu or Debian VPS;
- AlmaLinux/RHEL-like servers;
- Linux Mint desktop machines;
- local lab servers;
- private Proxmox/VM environments.

Useful baseline:

- Python 3;
- Node.js and npm;
- curl, wget, unzip, git;
- ffmpeg for voice/media features;
- enough disk space for Ollama models;
- a local or server browser environment for Moltbot.

## Fresh Install

```bash
curl -sL https://openzero.talktoai.org/install | bash
```

The installer prepares:

- system packages;
- OpenZero release files;
- Python dependencies;
- Node/Moltbot dependencies;
- Ollama;
- default Gemma local model path where possible;
- PM2/system service helpers;
- `.env` defaults.

## Desktop Mode

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --desktop
```

Desktop mode is useful when the machine has a GUI and the operator wants to open the panel locally.

## Custom Directory

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --dir /opt/openzero
```

## Optional Voice Dependencies

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --voice
```

This enables `VOICE_ENABLED=true` and `VOICE_TTS_ENABLED=true` and attempts to install local voice dependencies. Voicebox itself is a separate optional app. See [VOICEBOX.md](VOICEBOX.md).

## Optional BitNet

```bash
curl -sL https://openzero.talktoai.org/install | bash -s -- --bitnet
```

BitNet is a separate optional CPU-efficient lane. OpenZero stays on Ollama/Gemma unless BitNet is installed and activated.

## Update

```bash
curl -sL https://openzero.talktoai.org/update.sh | bash
```

The update path is intended to refresh OpenZero code and runtime helpers without deleting private `.env` values.

## First Boot Checklist

1. Open the Super Panel.
2. Confirm Ollama status.
3. Install or repair a local model if needed.
4. Choose CPU profile: compact, balanced, or max.
5. Create an OpenZero API key if you want ZeroThink integration.
6. Enable Moltbot Vision only when you need browser/page inspection.
7. Enable voice only when a local voice backend is ready.
8. Review network exposure before using remote access.

## Common Ports

| Port | Purpose |
| --- | --- |
| `1024` | OpenZero panel/API by default. |
| `11434` | Ollama local API. |
| `17493` | Voicebox default local API when running. |

## Do Not Expose Blindly

OpenZero is operator software. If you expose it to the internet, put it behind a reverse proxy, VPN, firewall, or other strong access control. Do not rely on obscurity.

