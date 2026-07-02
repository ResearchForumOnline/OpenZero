# Public Release Checklist

Before publishing OpenZero changes:

- No `.env`, generated keys, vault files, database dumps, server logs, model weights, or backup archives.
- No live production credentials or private endpoint secrets.
- No oversized artifacts such as ISO files, model files, Chrome packages, or release ZIPs.
- Public wording describes real user value plainly.
- Install scripts are readable and point to reviewed public URLs.
- Hive defaults are local/manual.
- Python files compile.
- README explains what is public and what is intentionally private.
