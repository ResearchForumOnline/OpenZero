# OpenZero Hive Boundary

OpenZero supports optional federation, but the public node is designed to run locally without depending on any central service.

## Public In This Repository

- Local Hive client configuration.
- Node registration payload shape.
- Local spool/replay behavior.
- Manual chat sharing controls.
- Public-sharing privacy filters.
- Signed node contributions generated from keys created on the operator machine.

## Not Public In This Repository

- Production Hive HQ server internals.
- Production database credentials.
- Private moderation/review operations.
- Live server backups or database exports.
- Runtime keys and vault material.

## Default Behavior

OpenZero should be safe to run without any remote Hive:

```env
HIVE_MIND_ENABLED=false
OPENZERO_HIVE_MODE=local
OPENZERO_HIVE_SHARE_MODE=manual
OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED=false
```

When the operator enables Hive, private chats still stay local unless the operator intentionally shares filtered knowledge. The public/federated path should never require committing secrets to GitHub.
