# ZeroMint OS v1.0

ZeroMint OS v1.0 is the large OpenZero-focused ISO image for users who want a downloadable operating-system-style route into a local AI node, development workstation, or lab machine.

The ISO is intentionally not committed into Git. GitHub blocks normal repository files larger than 100 MiB, Git LFS has per-plan object limits, and GitHub release assets must be under 2 GiB each. The public repository tracks the documentation, torrent metadata, and checksums while the large ISO stays on the OpenZero download server.

## Downloads

| File | Link | Notes |
| --- | --- | --- |
| GitHub split release | <https://github.com/ResearchForumOnline/OpenZero/releases/tag/zeromint-os-v1.0> | Three ISO parts, README, torrent, and checksums. |
| ZeroMint OS ISO | <https://openzero.talktoai.org/ZeroMint_OS_v1.0.iso> | 5,945,425,920 bytes, about 5.54 GiB. |
| Torrent | <https://openzero.talktoai.org/ZeroMint_OS_v1.0.torrent> | Small metadata file for distributed download clients. |
| Torrent in GitHub | [docs/downloads/ZeroMint_OS_v1.0.torrent](../../docs/downloads/ZeroMint_OS_v1.0.torrent) | Tracked in this repository for discovery. |
| Checksums | [docs/downloads/SHA256SUMS.txt](../../docs/downloads/SHA256SUMS.txt) | Verify before installing or sharing. |
| Split asset checksums | [docs/downloads/SHA256SUMS.parts.txt](../../docs/downloads/SHA256SUMS.parts.txt) | Verify the GitHub release parts before reassembly. |

## Verified Checksums

```text
52f2d62f7f286484b28f7c5128b398c1ddb87ca354efa997965f5eef98263668  ZeroMint_OS_v1.0.iso
04c02071a827b9af0a5b8883b2627edfb26b6f98e6907b5bc737fabdf66185e7  ZeroMint_OS_v1.0.torrent
```

The local Windows download copy and the OpenZero server copy were checked and matched exactly for the ISO hash above.

## GitHub Split Release

The GitHub Release uses three files because each release asset must be under 2 GiB:

```text
95cbb9afd3841b6c2c0dcfca107fe05b389c5345dbbfc757d58e153482f51308  ZeroMint_OS_v1.0.iso.part001
d3fcad548bec2ea3c844e2e73cfba7ac83a4502778bce5b204d7c14f963567f3  ZeroMint_OS_v1.0.iso.part002
c76d919b7f3b186c3310bfd50d1f9ad194ed5a541723ca46ab4dc25f844e6a3c  ZeroMint_OS_v1.0.iso.part003
```

Reassemble on Linux or macOS:

```bash
cat ZeroMint_OS_v1.0.iso.part001 ZeroMint_OS_v1.0.iso.part002 ZeroMint_OS_v1.0.iso.part003 > ZeroMint_OS_v1.0.iso
sha256sum ZeroMint_OS_v1.0.iso
```

Reassemble on Windows Command Prompt:

```bat
copy /b ZeroMint_OS_v1.0.iso.part001+ZeroMint_OS_v1.0.iso.part002+ZeroMint_OS_v1.0.iso.part003 ZeroMint_OS_v1.0.iso
certutil -hashfile ZeroMint_OS_v1.0.iso SHA256
```

## Verify The ISO

Windows PowerShell:

```powershell
Get-FileHash .\ZeroMint_OS_v1.0.iso -Algorithm SHA256
```

Linux:

```bash
sha256sum ZeroMint_OS_v1.0.iso
```

The hash should match:

```text
52f2d62f7f286484b28f7c5128b398c1ddb87ca354efa997965f5eef98263668
```

## Suggested First Run

Use a VM or spare machine first, especially if the target system has important files on it.

1. Download the ISO.
2. Verify the SHA256 hash.
3. Boot it in a virtual machine or write it to a USB drive with a trusted imaging tool.
4. Install or test OpenZero from the included or hosted route.
5. Open the OpenZero panel locally and create any API keys from the panel rather than hard-coding secrets into scripts.

## Public Release Notes

- GitHub is the source and documentation hub.
- The ISO is distributed from the OpenZero server because it is too large for a normal Git commit.
- The GitHub Release provides the ISO as split assets under the 2 GiB release asset limit.
- Do not publish private keys, `.env` files, logs, vault data, customer data, or private server snapshots inside any ISO.
- Review redistribution and branding requirements for all upstream operating-system components before wide public promotion.

## Related Docs

- [Install Guide](INSTALL.md)
- [Downloads And Releases](DOWNLOADS_AND_RELEASES.md)
- [Offline Release](OFFLINE_RELEASE.md)
- [Security Model](SECURITY_MODEL.md)
- [OpenZero Updates](UPDATES.md)
