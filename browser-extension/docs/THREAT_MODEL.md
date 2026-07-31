# Threat model

## Assets

- OpenZero bearer key;
- page-visible data;
- authority to inspect and interact with one granted tab;
- user task text;
- persistent site permissions.

## Untrusted actors and inputs

- webpage text, attributes, links, and DOM mutations;
- prompt injection embedded in the page;
- model output;
- navigation redirects;
- misleading or dynamically changing controls;
- pages attempting to remove or spoof visual status.

## Defenses

### Page prompt injection

Snapshots are labeled untrusted in the system prompt. More importantly, model
instructions have no direct authority: only one strict action schema is parsed,
raw JavaScript and selectors are unavailable, and local policy executes the
decision.

### Model hallucination

The model can reference only ephemeral element IDs in the latest snapshot.
Unknown actions, malformed JSON, stale IDs, missing elements, unsupported URLs,
and overlong inputs fail closed.

### Cross-site privilege expansion

A grant is tied to tab ID plus origin. A new origin pauses before navigation and
requires Brave's native optional-origin consent. An unexpected cross-origin
navigation revokes the grant. Browser-internal and non-HTTP schemes are blocked.

### Consequential actions

Risky labels and descriptors pause for an exact one-time user decision. Sensitive
personal-data fields also pause. Password, payment, secret/token, one-time-code,
and file-upload fields are blocked, not merely paused.

### Credential theft

The API key remains in extension-local storage and is used only in extension
fetches to the configured origin. It is not included in planner messages,
content-script messages, page DOM, popup status, logs, or tests. Remote plain
HTTP endpoints are rejected.

### Hidden operation

An in-page status card and action badge remain visible while a tab grant exists.
Both popup and overlay expose stop. Extension/page restart fails closed because
the grant is session-only.

## Residual risks

- Visible page text itself may contain sensitive data and is sent to OpenZero.
- Button-label heuristics cannot understand every consequential UI.
- A same-origin application can perform large state changes behind an ordinary
  label.
- A compromised OpenZero node receives the task and snapshots.
- Other powerful extensions or host malware are outside this boundary.
- The page can visually imitate the overlay, though it cannot obtain the grant
  token or call extension APIs from ordinary page JavaScript.

Production use requires independent review and site-specific policy for any
high-value workflow.
