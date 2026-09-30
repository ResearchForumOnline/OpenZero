# OpenZero 7.3: no required main node

Each installation owns its panel, models, private configuration, local knowledge,
tool authority and run checkpoints. No owner registration, company database or
TalkToAI backend is required for local operation.

## Fresh node defaults

```env
OPENZERO_DOMAIN=http://127.0.0.1:1024
OPENZERO_HIVE_URL=
OPENZERO_HIVE_MODE=local
HIVE_MIND_ENABLED=false
OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED=false
OPENZERO_HIVE_SHARE_MODE=manual
OPENZERO_BIND_HOST=127.0.0.1
OPENZERO_ALLOW_PUBLIC_BIND=false
```

Operators can select their own compatible remote endpoints. Optional federation
is an explicit client connection, not a built-in peer discovery, consensus,
distributed-training or pooled-inference network. A node does not require another
node, and private chats are not automatically shared.

## Upgrade existing installations

The 7.3 installer preserves `.env` values and backs up replaced managed source
files. Version metadata moves to 7.3.0. Only exact retired owner defaults are
cleared: the old owner Hive URL disables that obsolete route, the old domain
becomes loopback, and the old Tab Pilot setup URL becomes its GitHub guide.
Custom node addresses, model selections outside known former defaults, provider
keys and private runtime state remain operator-owned. A plaintext legacy
`SUDO_PASS` entry is removed as before; passwords are not copied into a release.

Review older mirror lists yourself and remove any retired endpoint. Do not
delete user-owned endpoints just because an owner service was retired.

## Distribution and mirrors

The v7.3.0 installer downloads its runtime and Tab Pilot assets from a pinned
GitHub release and verifies SHA-256 checksums. The updater downloads the latest
installer/checksum pair. GitHub hosts release files; it does not coordinate
model calls or local knowledge.

`OPENZERO_RELEASE_BASE_URL` overrides the runtime/extension asset base;
`OPENZERO_INSTALLER_BASE_URL` overrides the updater's installer base. A mirror
must serve matching filenames and checksums. Only use a mirror you trust:
checksums downloaded from the same origin detect damage, not a malicious
publisher. For disconnected use, build and review an offline bundle first.

## Tab Pilot migration

New helpers download the versioned ZIP, verify its checksum and manifest, and
prepare a folder for explicit browser Load unpacked approval. They do not write
managed policies or depend on a company-hosted CRX update server. They do not
silently remove an older administrator policy. If you used the old managed
install, review/remove its policy using your browser's policy tools before
adopting this path. Generate a scoped token locally; do not publish it.

## Optional services

Ollama/model downloads, Python and Node package feeds are installation
dependencies. Brave, Voicebox, BitNet, cloud model APIs and search providers are
optional. ZeroThink and Matrix bridge code can connect operator-owned services;
closed public websites are not login requirements for OpenZero.
