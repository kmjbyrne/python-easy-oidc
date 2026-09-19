# Token Validation

The `TokenValidator` validates JWT access tokens against an OIDC provider.

## How It Works

```text
Token string
    |
    v
OIDC Discovery  -->  GET /.well-known/openid-configuration
    |
    v
JWKS Fetch      -->  GET {jwks_uri}
    |
    v
JWT Verify      -->  signature, exp, iss, aud, sub
    |
    v
Claim Mapping   -->  Principal
```

## Configuration

```python
from oidcutils import TokenValidator

validator = TokenValidator(
    issuer="https://id.example.com",
    audience="my-api",
    algorithms=["RS256", "ES256"],  # defaults
)
```

| Parameter      | Type          | Default              |
| -------------- | ------------- | -------------------- |
| `issuer`       | `str`         | required             |
| `audience`     | `str`         | required             |
| `algorithms`   | `list[str]`   | `["RS256", "ES256"]` |
| `claim_mapper` | `ClaimMapper` | `DefaultClaimMapper` |
| `http_client`  | `AsyncClient` | creates its own      |

## JWKS Caching

The validator caches the JWKS after the first fetch. It only re-fetches when it
encounters a token signed by an unknown key ID. This handles key rotation: when
the IdP starts signing with a new key, the first token with the new `kid`
triggers a single JWKS refresh.

## Issuer Validation

The validator checks that the `issuer` in the OIDC discovery document matches
the configured issuer. This prevents a DNS hijack from serving a valid discovery
document with a different issuer claim.

## Custom HTTP Client

Pass your own `httpx.AsyncClient` for connection pooling, timeouts, or proxy
configuration:

```python
import httpx

client = httpx.AsyncClient(timeout=10.0)
validator = TokenValidator(
    issuer="https://id.example.com",
    audience="my-api",
    http_client=client,
)
```
