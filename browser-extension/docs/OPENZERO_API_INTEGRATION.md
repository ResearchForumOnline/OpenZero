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
      "id": "openzerogemma",
      "object": "model"
    }
  ]
}
```

### Planner call

```http
POST /v1/chat/completions
Authorization: Bearer <OpenZero API key>
Content-Type: application/json
```

The extension sends an OpenAI-compatible `messages` array, model name,
`temperature: 0.1`, `max_tokens: 500`, and the configured
`openzero_spark` mode. It reads `choices[0].message.content`.

The planner content must be exactly one JSON object. Markdown, free prose,
multiple actions, tool tags, CSS selectors, and JavaScript are rejected.

## Why no new OpenZero route is required

The current Moltbot route operates a server-side headless Chromium page. It
cannot attach to an existing user-owned Brave tab. The extension therefore:

- uses OpenZero only as a planner;
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

The prototype defaults to `openzerogemma` to match the requested OpenZero Gemma
lane. Model discovery is authoritative: if `/v1/models` does not return that
name, select an installed model or repair/install the model on OpenZero before
running the extension.
