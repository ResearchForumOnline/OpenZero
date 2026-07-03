# Security Policy

OpenZero is local AI operator software. Depending on install mode and permissions, it may run local commands, inspect files, browse pages, and expose a local API.

## Supported Security Scope

Security issues may include:

- secret leakage;
- API key handling bugs;
- unauthenticated sensitive routes;
- command execution bugs outside intended operator flows;
- unsafe default exposure;
- path traversal;
- dependency risk;
- incorrect handling of uploaded files;
- accidental private data disclosure.

## Reporting

Please do not post sensitive exploit details in a public issue.

Use a private contact route through the TalkToAI project or open a minimal GitHub issue requesting a security contact path without publishing exploit detail.

## Operator Guidance

- Do not expose the Super Panel publicly without strong access control.
- Use a dedicated Linux user where possible.
- Rotate OpenZero API keys if exposed.
- Never commit `.env`.
- Keep provider keys out of prompts and screenshots.
- Use VPN, firewall, SSH tunnel, or reverse proxy authentication.

## Public Repository Boundary

This repository should not contain:

- live credentials;
- customer data;
- private prompts;
- premium/private module source;
- server-specific secrets.

