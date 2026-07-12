# Changelog

## 2026-07-12

- Added authenticated OpenAI-compatible local model discovery at `GET /v1/models`.
- Restricted API-key rotation to direct loopback administrator requests.
- Documented the model discovery and local-only key-management contract.

## 2026-07-04

- Added professional public README and documentation suite.
- Added explicit open-core / premium-extension boundary documentation.
- Added security policy and contribution guide.
- Updated `.env.example` to match current configuration surface.
- Added Z-Spark draft-verify runtime for CPU-first draft, confidence gate, and target verification.
- Added OpenAI-compatible API metadata for `openzero_spark` requests from ZeroThink or other clients.
- Expanded the GitHub landing page with install, download, release, capability, API, ZeroThink bridge, Moltbot, Voicebox, BitNet, and offline release sections.
- Added the OpenZero 5.4 terminal-style screenshot to the public GitHub homepage.

## 2026-07-03

- Added CPU runtime tuning controls.
- Added Super Panel CPU profile selection.
- Applied CPU profile to local chat, BitNet, and OpenAI-compatible `/v1` route.
- Added optional Voicebox voice backend.
- Added Voicebox health/profile endpoints.
- Updated OpenZero release zip and live checksum.
