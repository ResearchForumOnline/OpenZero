---
name: server-ops
description: "Diagnose, maintain, and deploy to explicitly named servers over SSH with exact-target backups and live verification. Use for service health, logs, configuration, releases, remote file transfer, restarts, incident checks, or bounded production fixes."
---

# Server operations

## Contract

- Resolve the exact host, service, and target path before mutation.
- Perform read-only diagnosis autonomously.
- Treat a clear deploy, fix, install, update, or restart request as task-scoped authority for that named target.
- Back up exact production files before replacement.
- Verify process state and the real health path; retain rollback evidence.

## Workflow

1. Confirm host identity using inventory, hostname, service state, and expected paths.
2. Inspect logs, disk, memory, dependencies, and current configuration without changing state.
3. Stage and validate the smallest fix.
4. Create a timestamped exact-file rollback copy.
5. Deploy only the requested targets and restart only affected services.
6. Verify hashes, service status, logs, API health, and the user-facing path.
7. Roll back if verification fails and report the evidence.

Read [production checks](references/production-checks.md) for deployments, data moves, degraded storage, or multi-service incidents.

## Boundaries

- Require fresh confirmation for deletion, credential changes, access-policy changes, or broad overwrite.
- Never put secrets in prompts, command output, commit messages, or reports.
- Do not infer success from HTTP 200, a running process, or an empty error log alone.
