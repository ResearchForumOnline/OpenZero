# Security Model

OpenZero is operator software. It can run local models, expose local APIs, inspect files, use browser tooling, and execute actions depending on configuration and install permissions.

Security starts with the assumption that the node should be protected like an admin tool.

## Key Principles

1. Keep admin surfaces private.
2. Do not expose the Super Panel directly to the public internet.
3. Store secrets in `.env`, not in Git.
4. Hash OpenZero API keys.
5. Keep provider keys out of prompts.
6. Prefer local-first operation by default.
7. Make sharing explicit.
8. Do not trust browser-supplied backend endpoints.

## API Keys

OpenZero API keys are shown once. The app stores a hash and a short hint.

If a key is exposed:

1. Rotate the key in the Super Panel.
2. Update ZeroThink Neural Vault or any client using it.
3. Review access logs where available.

## Network Exposure

Recommended:

- local-only access;
- VPN access;
- SSH tunnel;
- reverse proxy with authentication;
- firewall allowlist.

Avoid:

- public unauthenticated panel exposure;
- using root without need;
- putting OpenZero behind a weak shared password;
- storing secrets in docs, screenshots, or issues.

## Browser And Tool Use

Moltbot and terminal/operator paths can inspect pages and local environment. Treat tool-enabled modes with care.

If you install OpenZero as root, the local agent has root-level potential. Prefer a dedicated Linux user where possible.

## Hive And Sharing

Hive/federation paths should be opt-in. Local learning and private node data should not be treated as public data.

## Premium/Private Code

Premium code should not be placed in this public repo. Use private package delivery, signed bundles, hosted APIs, or private plugins.

See [PREMIUM_EXTENSIONS.md](PREMIUM_EXTENSIONS.md).

