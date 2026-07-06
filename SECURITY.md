# Security Policy

## Supported Scope

This public repository covers the OpenZero local node and public release tooling. Private production services and live infrastructure are outside the public support scope.

## Reporting Issues

Report security issues privately before opening a public issue when possible. Include the affected file, setup details, expected impact, and a minimal reproduction.

Contact: security@talktoai.org or shaf@talktoai.org

## Operator Guidance

- Review install scripts before running them.
- Use a VM or spare machine first.
- Keep `.env`, SSH keys, API keys, model credentials, database config, generated node keys, and vault files out of Git.
- Do not expose local panels, Ollama, Jupyter, Gradio, Open WebUI, XRDP, or development ports to the public internet without firewall rules and authentication.
- Treat OpenZero as local automation with operator responsibility, not as a magic security boundary.

## Public Release Boundary

No production database credentials, private Hive HQ server config, generated private keys, local vaults, backup archives, model weights, live server snapshots, Matrix account files, customer data, or room exports should be committed to this repository.

Private CallChat Shield, ZMath, premium entitlement, policy, and deployment-specific security source must stay outside public repositories. Public docs may describe product behaviour, licensing, and safety boundaries, but should not publish private implementation details or unverifiable cryptography claims.
