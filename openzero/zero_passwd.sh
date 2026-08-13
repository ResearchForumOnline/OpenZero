#!/bin/bash
set -euo pipefail

cat <<'NOTICE'
OpenZero does not store or synchronize operating-system passwords.
Password changes are handled only by the operating system's interactive
credential utility and are never written to OpenZero configuration.
NOTICE

if ! command -v passwd >/dev/null 2>&1; then
    echo "The operating-system passwd utility is unavailable." >&2
    exit 1
fi

exec passwd
