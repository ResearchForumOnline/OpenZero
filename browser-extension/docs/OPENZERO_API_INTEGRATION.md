# OpenZero API integration

## Current contract used

### Model discovery

```http
GET /v1/models
Authorization: Bearer <OpenZero API key>
```

Expected response:

```json
{
  "object": "list",
  "data": [
    {
      "id": "hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M",
      "object": "model"
    }
  ]
}
```

### Planner call

```http
POST /v1/browser/plan
Authorization: Bearer <OpenZero API key>
Content-Type: application/json
```

The extension sends a bounded task, step number, short action history, and
privacy-reduced page snapshot. OpenZero uses a browser-only prompt, validates
one JSON action, and performs one bounded repair attempt if the local model
returns malformed output.

The planner content must be exactly one JSON object. Markdown, free prose,
multiple actions, tool tags, CSS selectors, and JavaScript are rejected.

## Why the planner has its own route

The current Moltbot route operates a server-side headless Chromium page. It
cannot attach to an existing user-owned Brave tab. The extension therefore:

- uses OpenZero only as a planner through a prompt that excludes general
  operator/root-tool instructions;
- keeps inspection and actuation in the browser;
- enforces consent locally, after model output;
- avoids a public browser-command queue.

This separation is compatible with the current OpenZero warning not to trust
browser-supplied backend endpoints: the API origin is an operator setting in
extension-local storage, and Brave grants only that exact origin. The page
cannot supply or modify it.

## Network recommendations

- loopback;
- SSH tunnel;
- authenticated private VPN;
- HTTPS with a valid certificate and host firewall policy.

The extension rejects plain HTTP to non-loopback hosts so the bearer key is not
sent cleartext across a network.

## Default model

The extension defaults to
`hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M` to match the
verified OpenZero runtime. Model discovery is authoritative: if `/v1/models`
does not return that name, select an installed model or repair/install the model
on OpenZero before running the extension. `openzerogemma:latest` remains a
compatibility fallback.
