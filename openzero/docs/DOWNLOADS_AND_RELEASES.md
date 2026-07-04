# Downloads And Releases

This page explains the public download paths for OpenZero.

## Fast Paths

| Need | Link |
| --- | --- |
| Public source repository | <https://github.com/ResearchForumOnline/OpenZero> |
| Latest public updates | [UPDATES.md](UPDATES.md) |
| Source ZIP for current main branch | <https://github.com/ResearchForumOnline/OpenZero/archive/refs/heads/main.zip> |
| GitHub releases | <https://github.com/ResearchForumOnline/OpenZero/releases> |
| ZeroMint OS GitHub release | <https://github.com/ResearchForumOnline/OpenZero/releases/tag/zeromint-os-v1.0> |
| Hosted installer | <https://openzero.talktoai.org/install.sh> |
| Hosted update script | <https://openzero.talktoai.org/update.sh> |
| ZeroMint OS v1.0 ISO | <https://openzero.talktoai.org/ZeroMint_OS_v1.0.iso> |
| ZeroMint OS torrent | <https://openzero.talktoai.org/ZeroMint_OS_v1.0.torrent> |
| ZeroMint OS guide | [ZEROMINT_OS.md](ZEROMINT_OS.md) |
| Online manual | <https://docs.talktoai.org/openzero-user-manual/> |

## Standard Install

Review first:

```bash
curl -fsSL https://openzero.talktoai.org/install.sh -o openzero-install.sh
less openzero-install.sh
bash openzero-install.sh
```

Fast install on a machine you control:

```bash
curl -fsSL https://openzero.talktoai.org/install.sh | bash
```

GitHub raw fallback:

```bash
curl -fsSL https://raw.githubusercontent.com/ResearchForumOnline/OpenZero/main/openzero/install.sh | bash
```

## Updates

```bash
curl -fsSL https://openzero.talktoai.org/update.sh | bash
```

or from a cloned repository:

```bash
cd OpenZero/openzero
bash update.sh
```

## Offline Release

For offline or low-connectivity targets, build a release bundle from a connected OpenZero node:

```bash
cd ~/openzero
chmod +x build_offline_release.sh
./build_offline_release.sh
```

Read the full guide: [OFFLINE_RELEASE.md](OFFLINE_RELEASE.md).

## ZeroMint OS v1.0

ZeroMint OS v1.0 is the OpenZero-focused ISO route for users who want a bootable operating-system-style download for testing, labs, or a local AI workstation.

The ISO is too large for a normal GitHub repository commit. It is hosted on the OpenZero server, with a torrent and SHA256 checksums tracked here for verification:

- GitHub split release: <https://github.com/ResearchForumOnline/OpenZero/releases/tag/zeromint-os-v1.0>
- ISO: <https://openzero.talktoai.org/ZeroMint_OS_v1.0.iso>
- Torrent: <https://openzero.talktoai.org/ZeroMint_OS_v1.0.torrent>
- Guide: [ZEROMINT_OS.md](ZEROMINT_OS.md)
- Checksums: [../../docs/downloads/SHA256SUMS.txt](../../docs/downloads/SHA256SUMS.txt)
- Split asset checksums: [../../docs/downloads/SHA256SUMS.parts.txt](../../docs/downloads/SHA256SUMS.parts.txt)

Verified ISO SHA256:

```text
52f2d62f7f286484b28f7c5128b398c1ddb87ca354efa997965f5eef98263668
```

## What A Good Public Release Should Include

- version tag and short release title;
- source ZIP and tarball from GitHub;
- installer checksum when a hosted installer changes;
- changelog summary;
- compatibility notes for Ubuntu/Debian/RHEL-family systems;
- model/runtime notes for Ollama, BitNet, Moltbot, Voicebox, and Z-Spark;
- security notes if any API, key, auth, or network behavior changed.

## Release Safety

OpenZero releases should not include real `.env` files, generated API keys, private Hive HQ internals, customer data, database credentials, model weights that cannot be redistributed, backups, or local runtime vaults.
