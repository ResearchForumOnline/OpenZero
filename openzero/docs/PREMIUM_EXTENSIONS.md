# Premium Extensions And Private Code Boundary

This repository is public. Anything committed here can be read, copied, forked, archived, and inspected.

If a feature must be usable but not publicly viewable, do not commit its source code to this repository.

## Recommended Open-Core Pattern

Use OpenZero as the open core:

- panel;
- local model runtime;
- OpenAI-compatible API;
- ZeroThink bridge;
- docs;
- install scripts;
- public extension points.

Put premium/private capabilities in one of these places:

- private GitHub repository;
- private package registry;
- encrypted/signed bundle distributed outside public GitHub;
- compiled Python wheel or service binary;
- hosted API controlled by the operator;
- license-gated plugin downloaded after activation.

## What To Avoid

Avoid claiming that public GitHub code is locked, uncopyable, or impossible to inspect. That is not how GitHub works.

Avoid committing:

- commercial source code;
- private model weights;
- secret prompts;
- private keys;
- paid provider credentials;
- customer data;
- server credentials;
- admin-only endpoint lists.

## Practical Extension Boundary

The open core should define:

- stable configuration keys;
- documented API routes;
- plugin/service integration points;
- signed checksum expectations;
- local logs and diagnostics;
- clear feature availability states.

Premium modules should provide:

- version number;
- module ID;
- license state;
- signature/checksum;
- public capability summary;
- no secrets in client-side HTML.

## Suggested Module Manifest

```json
{
  "module_id": "openzero-premium-example",
  "version": "1.0.0",
  "entrypoint": "premium_example:register",
  "sha256": "expected-bundle-hash",
  "requires_license": true,
  "public_capabilities": [
    "advanced scheduling",
    "private hosted model route"
  ]
}
```

## User-Facing Language

Good:

> OpenZero is open core. Optional premium modules may be delivered separately for commercial deployments.

Avoid:

> The code is on GitHub but cannot be copied.

## Security Note

Obfuscation can slow casual copying, but it is not a security boundary. Real control comes from keeping sensitive code server-side, private, signed, or licensed outside the public repository.

