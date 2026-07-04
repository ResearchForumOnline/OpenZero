# OpenZero Updates

Public-safe changelog for user-visible OpenZero changes. This file avoids API keys, private server paths, internal deployment notes, customer data, live logs, private Hive internals, and attacker-useful security detail.

## 2026-07-04 - Public Docs And Runtime Visibility

### Added

- Expanded the root GitHub README so visitors can see the real OpenZero capability surface from the repository front page.
- Added stronger documentation links for install, downloads, releases, CPU runtime, API, architecture, ZeroThink bridge, Z-Spark, Voicebox, security model, configuration, troubleshooting, and roadmap.
- Added Z-Spark documentation for OpenZero's custom CPU-first draft/verify lane.
- Added optional Voicebox documentation for users who install a local Voicebox service separately.
- Added clearer release-discovery guidance so users know where to download source, install scripts, update scripts, and offline bundles.

### Changed

- Public OpenZero presentation now focuses on local AI node ownership, Super Panel, OpenAI-compatible API keys, CPU-first operation, Moltbot, offline bundles, ZeroThink bridge, Z-Spark, Voicebox, and security boundaries.
- Public crypto/token wording was removed from OpenZero-facing pages and docs so new users see the AI node product clearly.
- ZeroThink bridge language now explains the intended ladder: limited shared gateway trial where enabled, then user-owned OpenZero node keys for sustained compute.
- Model guidance now keeps the current local model file boundary visible: stay under 15 GB unless the operator knows the hardware can handle more.

### Security And Privacy Notes

- ZeroThink should not trust arbitrary browser-supplied OpenZero upstream URLs.
- Public docs should not include raw keys, secrets, customer material, private server paths, runtime logs, database credentials, local vaults, or private implementation notes.
- OpenZero admin surfaces should be treated like operator tools and protected before any public exposure.

## 2026-07-03 - Voice And CPU Runtime

- Added optional Voicebox integration direction.
- Added CPU runtime tuning documentation and clearer guidance for RAM/CPU-aware local model choices.
- Improved OpenZero docs around Super Panel, local model policy, API keys, and ZeroThink bridge positioning.

## 2026-07-02 - Public Landing Page Polish

- Improved the public OpenZero site and GitHub-oriented language.
- Clarified OpenZero as a local-first AI node rather than only a chatbot.
- Improved discovery paths into the manual, docs, source, and TalkToAI ecosystem pages.

## Earlier 2026 - Foundation Work

- Built the public OpenZero release direction around local AI, Ollama model routing, Super Panel operation, OpenAI-compatible API keys, Moltbot/browser tooling, Hive boundary concepts, offline bundle paths, and integration with ZeroThink.

