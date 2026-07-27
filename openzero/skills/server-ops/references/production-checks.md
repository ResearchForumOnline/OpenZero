# Production checks

Use the checks that apply:

- Identity: hostname, IP, service name, release path, and environment.
- Rollback: exact files, database transaction or backup integrity, and restart command.
- Capacity: free disk, inode use, memory, load, and model/runtime footprint.
- Syntax: configuration parser, unit test, package check, or dry run.
- Deployment: source and destination hashes, ownership, and mode.
- Runtime: process manager state, restart count, recent logs, listening port, and dependency reachability.
- Health: authenticated API response when required and the actual public click path.
- Recovery: restore the narrow backup when post-deploy checks fail.

Avoid whole-server backups when an exact-file rollback is sufficient, but never make an irreversible schema or data change without a tested recovery method.
