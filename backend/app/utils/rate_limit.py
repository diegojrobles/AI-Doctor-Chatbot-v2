"""Shared rate limiter.

Lives in its own module so routes can import `limiter` without importing
app.main, which would be a circular import.

Why the custom key function
---------------------------
In production the app sits behind Caddy on a private Docker network, so
`request.client.host` is always the proxy's address. Keying on that would put
every caller in the world into a single shared bucket -- one busy client would
rate-limit everyone else.

Caddy sets X-Forwarded-For, and nothing but Caddy can reach the app (the api
container publishes no ports), so the left-most entry is trustworthy here.

Limits are per-process. gunicorn runs 2 workers, so the effective limit is
roughly double what each decorator says. That is fine for abuse protection; it
is not an accounting mechanism.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address


def client_identifier(request):
    """Best-effort caller identity: real client IP when proxied, else peer IP."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_identifier)
