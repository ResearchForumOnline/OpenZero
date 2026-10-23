# Changelog

## 7.3.1 - 2026-10-23

- Serve the required Socket.IO browser client from the node, retaining pinned
  upstream bytes, MIT license and verified npm integrity provenance.
- Choose local computation on fresh nodes and preserve explicit existing modes.
- Share exact model-route selection between CLI and panel. Local Llama, Qwen,
  GPT-family and namespaced Ollama aliases no longer imply cloud transmission.
- Honor disabled automatic runtime repair and report repair/cooldown state
  accurately instead of always claiming a repair started.
- Add a read-only node configuration report and owner-authorized API endpoint.
- Add an isolated actual production-entry boot check with HTTP disabled,
  local asset serving, owner authorization and Socket.IO handshake checks.
- Update ZERO ONE's separate hosted privacy notice for 8.5 provider profiles.

## 7.1.0 - 2026-07-31

- Added canonical 7.1.0 version migration for fresh installs and upgrades.
- Raised the bounded Ultra root-run worker ceiling to 16 while retaining
  serialized local-model inference.
- Added Brave installation from Brave's official Linux installer for desktop
  setups, plus explicit `--brave` and `--no-brave` controls.
- Kept Tab Pilot consent boundaries, managed policy, scoped tokens, and signed
  automatic extension updates.

## 2026-07-27

- Documented `openzerogemma:latest` and the public Zero-Gemma4-E4B-OpenZero GGUF release.
- Added the OpenZero Tab Pilot Manifest V3 extension for explicitly granted Brave tabs.
- Added per-tab and per-origin consent, visible stop/revoke controls, bounded action schemas, and confirmation gates for consequential actions and personal-data entry.
- Added a checksum-verifying Windows setup helper plus a public extension download and setup page.

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
