# Privacy

OpenZero Tab Pilot has no analytics, telemetry, advertising, or third-party
service integration.

For each model step it sends the configured OpenZero API:

- the user-written task;
- current page URL and title;
- a bounded visible-text snapshot;
- bounded headings and interactive-element labels;
- recent action result summaries.

It does not intentionally send:

- input or textarea values;
- cookies;
- browser history;
- content from other tabs;
- password, payment, token, secret, one-time-code, or upload field values;
- screenshots.

The OpenZero API key is stored in extension-local storage. Tab grants, pending
actions, tasks, and recent step summaries are held in session storage and are
cleared on a full browser restart or extension reload. Site permissions granted
through Brave can persist until the user removes them.

Pages can still contain personal data in visible text. Grant only pages whose
visible content may be sent to the configured OpenZero node.
