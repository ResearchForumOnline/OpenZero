# Contributing

Contributions should improve the public OpenZero node, docs, installers, safety checks, local panel, or developer experience without adding secrets or private infrastructure assumptions.

Before opening a pull request:

1. Keep changes focused.
2. Do not commit generated keys, `.env` files, archives, model weights, backups, database dumps, or server logs.
3. Run:

```bash
cd openzero
python -m compileall brain hivemind
```

4. Explain the user impact and any security/privacy implications.

Private Hive HQ internals and production infrastructure should stay in private repositories or deployment systems.
