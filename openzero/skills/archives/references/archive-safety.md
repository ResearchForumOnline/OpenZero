# Archive safety

Before extraction, reject members that:

- are absolute paths or contain `..` traversal;
- resolve outside the destination;
- are symbolic links, device nodes, or other special files;
- exceed the file-count, individual-size, total-size, or compression-ratio limit;
- collide case-insensitively on a case-insensitive destination.

For a release, make ordering, timestamps, permissions, and manifest generation deterministic. For a recovery backup, verify checksums and the application-specific integrity check before calling it usable.
