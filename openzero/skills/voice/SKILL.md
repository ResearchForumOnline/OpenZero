---
name: voice
description: "Produce local speech output through the configured OpenZero voice stack. Use when the user asks OpenZero to speak, read text aloud, produce a local voice reply, or test text-to-speech."
---

# Voice

1. Confirm the requested text is appropriate for local playback.
2. Keep spoken output concise unless the user asks for the full document.
3. Use the configured local voice engine once.
4. Report the engine result and output path when available.

Read [voice safety](references/voice-safety.md) before using a cloned profile, speaking personal data, or preparing audio for external distribution.

Do not claim a specific cloned voice was used unless the runtime reports that profile. Do not publish, upload, or send generated audio without separate task authority and fresh confirmation at the external action.
