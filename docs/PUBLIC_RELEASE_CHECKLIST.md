# Public Release Checklist

Before publishing OpenZero changes:

- No `.env`, generated keys, vault files, database dumps, server logs, model weights, or backup archives.
- No live production credentials or private endpoint secrets.
- No oversized artifacts such as ISO files, model files, Chrome packages, or release ZIPs.
- No private CallChat Shield, ZMath, premium entitlement, policy, or deployment-specific security source.
- No customer data, room exports, transcripts, Matrix account files, API keys, SSH keys, payment secrets, or server snapshots.
- Public Shield/CallChat wording stays at behaviour, licensing, and safety-boundary level only.
- Public wording describes real user value plainly and avoids unverifiable cryptography claims.
- Install scripts are readable and point to reviewed public URLs.
- Hive defaults are local/manual.
- Python files compile.
- README explains what is public and what is intentionally private.
