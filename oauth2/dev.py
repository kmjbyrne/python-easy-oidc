"""Local development helpers for minting tokens without an external IdP.

Generates an ephemeral ES256 signing key at import time. The key lives only in
memory and changes on every restart.
"""

import secrets
import time

from joserfc import jwt
from joserfc.jwk import ECKey

_signing_key = ECKey.generate_key("P-256")
KID = "dev-key"
ALG = "ES256"
DEFAULT_LIFETIME = 3600


def public_jwks() -> dict:
    """Return the public JWKS containing the dev signing key."""
    pub = _signing_key.as_dict(is_private=False)
    pub["kid"] = KID
    pub["use"] = "sig"
    pub["alg"] = ALG
    return {"keys": [pub]}


def mint_token(
    *,
    issuer: str,
    audience: str,
    subject: str = "dev-user",
    email: str = "dev@localhost",
    name: str = "Dev User",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    lifetime: int = DEFAULT_LIFETIME,
    extra_claims: dict | None = None,
) -> dict:
    """Mint a signed JWT and return a token response dict."""
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + lifetime,
        "roles": roles or [],
        "permissions": permissions or [],
    }
    if extra_claims:
        claims.update(extra_claims)

    header = {"alg": ALG, "kid": KID}
    token = jwt.encode(header, claims, _signing_key)

    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": lifetime,
        "refresh_token": secrets.token_urlsafe(32),
    }


def discovery_document(issuer: str) -> dict:
    """Return a minimal OIDC discovery document for local dev."""
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/dev/token",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [ALG],
    }
