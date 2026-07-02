# Security Model

OpenZero is an operator-controlled local automation system. It can help inspect files, run selected commands, read webpages, build archives, and manage local services, but it runs on infrastructure owned by the operator and must be treated with the same care as any admin tool.

## Trust Boundaries

- The operator controls the machine.
- `.env` controls local behavior and must stay private.
- Generated node keys remain on the node.
- Public Hive sharing is opt-in and filtered.
- Private hosted services are separate from this public repository.

## Practical Controls

- Keep Hive disabled for first-run testing.
- Use VMs before production machines.
- Review shell scripts before executing them.
- Restrict panels and model services to localhost or trusted networks.
- Prefer SSH keys, firewalls, and fail2ban-style lockout protection.
- Do not paste secrets into prompts or public issue reports.

## Private Extensions

Private extensions should use explicit interfaces, environment flags, and separate repositories. Avoid hiding behavior in public code; clear boundaries build more trust than obfuscation.
