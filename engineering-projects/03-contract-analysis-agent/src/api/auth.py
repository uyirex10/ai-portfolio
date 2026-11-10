"""API-key authentication. Pattern taken from the sibling
engineering-projects/02-document-intelligence-api/auth.py: a header
check against known keys, constant-time comparison, no key material in
error responses, client name attached to the request without storing
the secret.
"""

import os
import secrets

from fastapi import Header, HTTPException, status

# Configured as name:secret pairs, comma separated:
#     CONTRACT_AGENT_API_KEYS=acme:sk_live_abc123,internal:sk_test_def456
ENV_VAR = "CONTRACT_AGENT_API_KEYS"


def load_keys() -> dict[str, str]:
    """Map secret -> client name. Read per call so a key can be revoked
    without a restart, and so tests can set the variable and be believed."""
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
    """FastAPI dependency. Returns the client name, or raises 401."""
    known = load_keys()
    if not known:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "detail": "The service has no API keys configured."},
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if x_api_key:
        for secret, name in known.items():
            if secrets.compare_digest(x_api_key, secret):
                return name

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "detail": "Missing or invalid API key. Send it in the X-API-Key header."},
        headers={"WWW-Authenticate": "ApiKey"},
    )
