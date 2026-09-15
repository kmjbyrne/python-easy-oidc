# OAuth2

A Python SDK for OAuth2/OIDC token validation with optional FastAPI integration.

Wraps [Authlib](https://authlib.org/) and [joserfc](https://jose.authlib.org/),
so service builds get auth in two lines, not fifty.

## What It Does

- Validates JWT access tokens against any OIDC provider
- Maps claims into a typed `Principal` model with roles and permissions
- Handles JWKS caching and automatic key rotation
- Manages token lifecycle (storage, expiry, refresh)
- Provides FastAPI dependency functions (`current_user`, `require_permission`,
  `require_role`)

## Quick Example

```python
from fastapi import Depends, FastAPI
from oauth2.contrib.fastapi import FastAPIAuth, current_user, require_permission
from oauth2 import Principal

app = FastAPI()
app.state.auth = FastAPIAuth.from_settings(
    issuer="https://id.example.com",
    audience="my-api",
)


@app.get("/orders")
async def list_orders(user: Principal = Depends(current_user)):
    return {"user": user.subject}


@app.post("/orders")
async def create_order(
    user: Principal = Depends(require_permission("orders.write")),
):
    return {"created_by": user.subject}
```

Routes never see tokens, JWKS, or Authlib. They receive a typed `Principal`.

## Next Steps

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [FastAPI Integration](guide/fastapi-integration.md)
