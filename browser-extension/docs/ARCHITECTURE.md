# Architecture

## Components

```text
User
  |
  | explicit popup gestures
  v
Popup / Options
  |
  | extension-only messages
  v
Manifest V3 service worker
  |             |
  |             +--> OpenZero /v1/models
  |             +--> OpenZero /v1/chat/completions
  |
  | chrome.scripting + tab-scoped grant token
  v
Isolated-world content controller
  |
  v
Granted HTTP(S) page
```

The page never receives the OpenZero URL, API key, task state, or model
response. The content controller runs in Chromium's isolated world and accepts
only extension messages carrying the current random tab grant ID.

## Control loop

1. The popup's **Grant this tab** gesture creates a random session grant tied to
   the tab ID and exact origin.
2. The controller returns a bounded snapshot and ephemeral element registry.
3. The service worker asks OpenZero for exactly one JSON action.
4. Shared policy validates the action and checks settings, origin, target
   descriptor, sensitive-field class, and risk.
5. A new origin or risky action becomes a paused session record.
6. If allowed, the controller requires the same grant and snapshot ID before
   resolving the ephemeral element and acting.
7. The next step always begins with a new snapshot.

## Permission model

Required permissions:

- `activeTab`: a user gesture grants temporary access to the chosen tab;
- `scripting`: inject the isolated controller only after that grant;
- `storage`: local connection settings and session-only grants/runs;
- `tabs`: observe URL changes, update navigation, and bind state to a tab ID.

There are no install-time host permissions. `http://*/*` and `https://*/*` are
optional templates only. The options page requests the exact OpenZero API
origin; cross-site work requests the exact destination origin using Brave's
native permission prompt.

Persistent origin access never grants a tab automatically. The extension still
requires a separate tab grant for every tab.

## State

`chrome.storage.local`:

- OpenZero API origin;
- API key;
- model and safety settings.

`chrome.storage.session`:

- exact tab grants;
- current run and bounded history;
- pending destination or one-time action approval.

No task state is synced through a browser account.

## Failure behavior

Unexpected site changes revoke the grant. Browser restart clears the session.
Stale snapshots fail. Model parse failures fail. Missing API origin permission
fails. Timeouts abort the model request. The user can stop from either the popup
or a high-z-index, closed-shadow-root status card in the page.
