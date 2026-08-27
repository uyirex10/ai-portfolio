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
