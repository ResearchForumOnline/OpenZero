---
name: archives
description: "Inspect, create, or safely extract local ZIP archives with traversal checks and bounded output. Use for backups, release bundles, package inspection, ZIP validation, extraction, or deterministic handoff artifacts."
---

# Archives

1. Resolve the exact source, destination, and intended exclusions.
2. Inspect archive members before extraction.
3. Reject absolute paths, parent traversal, links, device files, and excessive expansion.
4. Extract into a new bounded directory unless overwrite was freshly confirmed.
5. For creation, exclude secrets, caches, runtime data, and replaceable artifacts as required.
6. List the result and verify expected files, exclusions, readability, and checksum.

Read [archive safety](references/archive-safety.md) for backups, untrusted archives, or release packages.

Do not present a ZIP as a usable backup until its listing and representative contents have been verified. Use application-aware database backup procedures when consistency matters.
