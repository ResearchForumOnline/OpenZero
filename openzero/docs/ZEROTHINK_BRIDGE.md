# ZeroThink Bridge

The ZeroThink bridge is one of OpenZero's most important ecosystem features.

ZeroThink is the browser-based AI workbench. OpenZero is the local/self-hosted AI node. Together, they let a user combine a polished web studio with their own private local compute.

## User Story

1. The user installs OpenZero on a local machine or server.
2. OpenZero runs local models through Ollama.
3. The user creates an OpenZero API key in the Super Panel.
4. The user opens ZeroThink Neural Vault.
5. The user saves the OpenZero Machine API Key.
6. ZeroThink can route suitable calls through the user's node.

## Why This Is Powerful

This creates a practical hybrid AI workflow:

- use ZeroThink for a polished interface;
- use OpenZero for private local model execution;
- use cloud providers only when needed;
- keep more control over cost and data;
- move from "using AI" to operating part of the AI stack.

## API Key Behavior

OpenZero stores an API key hash, not the raw key.

The key is shown once when created or rotated. Store it securely.

## Local API Endpoint

```text
POST /v1/chat/completions
```

Example:

```bash
curl http://YOUR-OPENZERO-HOST:1024/v1/chat/completions \
  -H "Authorization: Bearer ztapi_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e4b",
    "messages": [
      {"role": "user", "content": "Say OpenZero API OK"}
    ],
    "openzero_spark": "auto"
  }'
```

## Z-Spark From ZeroThink

ZeroThink can request OpenZero's custom Z-Spark draft-verify lane by sending `openzero_spark: "auto"` with the OpenAI-compatible request.

When the user's OpenZero node has the configured draft model installed, OpenZero drafts with the small model, confidence-gates the draft, and verifies through the active target model before returning the final answer to ZeroThink. If the draft model is missing, OpenZero continues with target-only inference.

## Security Rule

ZeroThink should not trust browser-supplied OpenZero URLs. Endpoint routing belongs server-side.

The public UI can show:

- connection status;
- saved key hint;
- plan/usage limits;
- whether a local OpenZero route is available.

The public UI should not show:

- raw API keys;
- private server URLs;
- prompt internals;
- admin-only routing logic.
