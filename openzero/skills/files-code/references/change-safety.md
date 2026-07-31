# Change safety

Before a consequential file change:

1. Resolve the absolute target and verify it is not a workspace root, home directory, or unresolved variable.
2. Check for unrelated local modifications.
3. Back up the exact production file or create a narrow version-control checkpoint.
4. Keep secrets and user data out of diffs, logs, and durable reports.
5. Validate syntax before restart or deployment.
6. Verify the live behavior separately from the local edit.
7. Record a precise rollback path.

Never substitute a broad recursive operation for a small, known target.
