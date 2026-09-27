"""Request boundary shared by code and model improvement workspaces."""
from urllib.parse import urlsplit

from flask import request


def _origin(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        return (parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80))
    except ValueError:
        return None


def workbench_request_authorized(local_authorized, bearer_authorized):
    """Require existing admin authority and reject browser cross-origin writes.

    This is a request boundary, not a sandbox for operator-approved Python tests.
    A loopback TCP peer alone must not authorize DNS-rebinding hosts or proxies.
    """
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.mimetype != "application/json":
        return False
    origin = request.headers.get("Origin")
    if origin and (_origin(origin) is None or _origin(origin) != _origin(request.host_url)):
        return False
    if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        return False
    if bearer_authorized():
        return True
    host = _origin(request.host_url)
    return bool(host and host[1] in {"localhost", "127.0.0.1", "::1"} and local_authorized())
