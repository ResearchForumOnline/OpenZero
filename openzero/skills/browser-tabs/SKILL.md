---
name: browser-tabs
description: "Inspect public pages or perform bounded work in one explicitly granted Brave tab using OpenZero Tab Pilot. Use for browsing, dynamic UI inspection, navigation, form assistance, tab work, screenshots, or multi-step website tasks."
---

# Browser and tabs

## Choose the lane

- Use `fetch_url` for fast public text extraction.
- Use `moltbot_browse` for a dynamic page or headless-browser inspection.
- Use OpenZero Tab Pilot only when the person has granted one normal Brave tab through the extension.

Moltbot returns a fresh `snapshot_id` and ephemeral element IDs. Use `moltbot_click`
or `moltbot_type` only with IDs from that exact snapshot. Moltbot clears the
snapshot after every action and returns a newly inspected state.

The autonomous server does not yet have a job/evidence bridge into an existing
Brave tab. Explicit Brave or current-tab objectives must pause rather than use
Moltbot as substitute proof.

## Tab workflow

1. Restate the bounded objective and important limits.
2. Inspect the current URL, origin, page text, and element snapshot.
3. Take one schema-checked action using only inspected element identifiers.
4. Re-inspect after every action.
5. Pause for a new origin, personal-data entry, or consequential action.
6. Verify the requested state change and release the tab grant when done.

Read the [Tab Pilot contract](references/tab-pilot-contract.md) before any interactive website task.

## Boundaries

- Never claim Tab Pilot is connected when only Moltbot is available.
- Never type passwords, payment details, secrets, one-time codes, or file uploads.
- Never silently send, submit, publish, buy, delete, sign in, install, or change an account.
- Stop on CAPTCHA, unsupported pages, stale snapshots, or lost grants.
