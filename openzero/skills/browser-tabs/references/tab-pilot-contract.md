# Tab Pilot contract

Tab Pilot authority is intentionally narrow:

- A user gesture grants one normal HTTP or HTTPS tab.
- The extension exposes a privacy-reduced snapshot and ephemeral element IDs.
- OpenZero proposes one JSON action at a time.
- Local extension policy validates the action before execution.
- Cross-origin navigation and consequential actions require fresh approval.
- The page is inspected again before planning the next step.
- Browser restart, explicit stop, unsupported navigation, or policy failure ends or pauses the grant.

Do not instruct the model to generate CSS selectors or arbitrary JavaScript. Do not treat a saved site permission as a tab grant. If the extension is not connected, report that limitation and use read-only page extraction where possible.
