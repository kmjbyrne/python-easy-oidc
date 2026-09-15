# Quick Start

This guide walks through validating a JWT access token and extracting user
identity. No framework required.

## Validate a Token

```python
from oauth2 import TokenValidator, Principal

validator = TokenValidator(
    issuer="https://id.example.com",
    audience="my-api",
)

principal: Principal = await validator.validate_token(token)
```

The validator:

1. Fetches the OIDC discovery document from
   `{issuer}/.well-known/openid-configuration`
2. Downloads the JWKS from the discovered `jwks_uri`
3. Verifies the token signature, expiry, issuer, and audience
4. Maps claims into a `Principal`

JWKS are cached. Subsequent calls skip the HTTP requests unless the token was
signed by an unknown key (which triggers a single JWKS refresh for key
rotation).

## Use The Principal

```python
principal.subject  # "user-123"
principal.email  # "user@example.com"
principal.roles  # frozenset({"admin", "viewer"})
principal.permissions  # frozenset({"orders.read", "orders.write"})

principal.has_role("admin")  # True
principal.has_permission("orders.write")  # True
principal.has_any_role("admin", "editor")  # True
principal.has_all_permissions("orders.read", "orders.write")  # True
```

## Handle Errors

```python
from oauth2 import TokenError

try:
    principal = await validator.validate_token(token)
except TokenError as e:
    # "Token has expired", "Invalid token signature: ...", "Invalid claim: ..."
    print(e)
```

`TokenError` is raised for any validation failure: expired tokens, bad
signatures, wrong issuer/audience, or missing required claims.

## Next Steps

- [FastAPI Integration](../guide/fastapi-integration.md) -- wire auth into
  routes
- [Token Refresh](../guide/token-refresh.md) -- manage token lifecycle
- [Claim Mapping](../guide/claim-mapping.md) -- customize how claims become a
  Principal
