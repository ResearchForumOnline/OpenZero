---
name: files-code
description: "Inspect, change, and verify local files, source code, or OpenZero skill manifests with narrow scope and rollback awareness. Use for repository work, configuration edits, skill creation, log inspection, debugging, implementation, tests, refactors, or creating local artifacts."
---

# Files and code

## Contract

- Inspect the target and nearby conventions before writing.
- Preserve unrelated files and pre-existing changes.
- Keep every write within the user's requested scope.
- Prefer structured file tools; use shell commands for established build, test, and formatting workflows.
- Report the actual validation result, including failures.

## Workflow

1. Resolve the exact workspace and target files.
2. Inspect version control state and relevant code paths.
3. Form a small change plan and identify rollback needs.
4. Apply bounded edits without erasing unrelated content.
5. Inspect the final diff and run targeted tests, syntax checks, or a local smoke test.
6. Summarize changed files, proof, and remaining limitations.

Read [change safety](references/change-safety.md) before production configuration changes, destructive work, migrations, or changes in a dirty worktree.

Read [skill authoring](references/skill-authoring.md) only when creating or updating an OpenZero skill package.

## Boundaries

- Require fresh confirmation before deletion, broad overwrite, permission changes, or credential rotation.
- Treat generated output, build caches, and dependency trees as replaceable only when the task says so.
- Never report unrun tests as passing.
