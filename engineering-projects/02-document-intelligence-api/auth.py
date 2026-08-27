"""API-key authentication.

A header check against known keys, which is the right amount of machinery at this
scale. What it must get right is small but non-negotiable: constant-time comparison, no
key material in logs or error messages, and a client label attached to the request so
the log can answer "who spent this" without storing the secret.
"""

import os
import secrets

from fastapi import Header, HTTPException, status

# Configured as name:secret pairs, comma separated, so the request log can record which
# client called without ever storing the key itself:
#
#     DOCINTEL_API_KEYS=procurement:sk_live_abc123,internal:sk_test_def456
#
# Names are for the log. Secrets are what the caller sends in X-API-Key.
ENV_VAR = "DOCINTEL_API_KEYS"


def load_keys() -> dict[str, str]:
    """Map secret -> client name. Read per call so a key can be revoked without a
    restart, and so tests can set the variable and be believed."""
    keys: dict[str, str] = {}
    for entry in os.environ.get(ENV_VAR, "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, _, secret = entry.partition(":")
        name, secret = name.strip(), secret.strip()
        if name and secret:
            keys[secret] = name
    return keys


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency. Returns the client name, or raises 401.

    401 rather than 403: the caller has not proved who they are. The body says only
    that the key was missing or invalid - which of the two, and which keys exist, are
    not the caller's business.
    """
    known = load_keys()
    if not known:
        # Refusing everything is the safe failure. An unconfigured service that
        # accepted all callers would be an open, billable endpoint.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "detail": "The service has no API keys configured.",
            },
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if x_api_key:
        # compare_digest against every known key: a plain dict lookup would leak, via
        # timing, how much of a guessed prefix was right.
        for secret, name in known.items():
            if secrets.compare_digest(x_api_key, secret):
                return name

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "unauthorized",
            "detail": "Missing or invalid API key. Send it in the X-API-Key header.",
        },
        headers={"WWW-Authenticate": "ApiKey"},
    )


# The admin page is a different privilege from extraction: it shows every client's
# spend and every filename processed. An integrator's extract key must not open it, so
# it has its own secret and is simply unavailable until one is configured.
ADMIN_ENV_VAR = "DOCINTEL_ADMIN_KEY"


def require_admin_key(
    x_api_key: str | None = Header(default=None),
    key: str | None = None,
) -> str:
    """Guard the admin page.

    Accepts the secret from the X-API-Key header or a ?key= query parameter. The query
    parameter exists because this page is opened in a browser, which cannot set a
    header - it is a real trade-off, since query strings land in browser history and
    proxy logs, and it is why this is a separate low-value secret rather than a
    key that can also spend money.
    """
    expected = os.environ.get(ADMIN_ENV_VAR, "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "detail": "The admin page is not enabled on this deployment.",
            },
        )
    for candidate in (x_api_key, key):
        if candidate and secrets.compare_digest(candidate, expected):
            return "admin"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "detail": "Missing or invalid admin key."},
        headers={"WWW-Authenticate": "ApiKey"},
    )
