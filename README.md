# oidcutils

A Python SDK that wraps [Authlib](https://authlib.org/) and
[joserfc](https://jose.authlib.org/) to handle OAuth2/OIDC token validation, and
builds a `Principal` identity model from JWT claims. Optional
[FastAPI](https://fastapi.tiangolo.com/) integration exposes `current_user` and
`require_permission` as dependency functions, so service teams add auth to
routes without touching JWTs directly.

## Install

Not on PyPI at the moment. Install directly from GitHub:

```bash
uv pip install git+https://github.com/kmjbyrne/python-oidcutils.git
```

For FastAPI support:

```bash
uv pip install "oidcutils[fastapi] @ git+https://github.com/kmjbyrne/python-oidcutils.git"
```

Pin to a version tag:

```bash
uv pip install git+https://github.com/kmjbyrne/python-oidcutils.git@v0.1.0
```

## How It Works

The SDK does two things:

1. Validates a JWT access token against an OIDC provider (signature, expiry,
   issuer, audience).
2. Maps the validated claims into a `Principal` object with roles and
   permissions.

Token validation uses OIDC discovery to find the JWKS endpoint, fetches the
signing keys, and caches them. When the SDK encounters an unknown key ID, it
refreshes the JWKS automatically to handle key rotation.

RBAC adds no extra verification. Roles and permissions live inside the JWT
claims. After the single token validation, the SDK checks the `Principal` fields
in memory.

## Core Usage

```python
from oidcutils import TokenValidator, Principal

validator = TokenValidator(
    issuer="https://id.example.com",
    audience="my-api",
)

principal: Principal = await validator.validate_token(token)
principal.subject  # "user-123"
principal.has_role("admin")
principal.has_permission("orders.write")
```

## Token Refresh

The SDK handles token lifecycle through `OIDCClient` and `TokenManager`.
Consumers call `get_access_token()` and get back a valid token string. The
manager refreshes transparently when the access token is near expiry.

```python
from oidcutils import OIDCClient, TokenManager

client = OIDCClient(
    issuer="https://id.example.com",
    client_id="my-app",
    client_secret="secret",
    redirect_uri="http://localhost:8000/auth/callback",
)

manager = TokenManager(client)

# After login, store the token set
token_set = await client.exchange_code(code)
await manager.store_token(session_id, token_set)

# On subsequent requests, get a valid access token (auto-refreshes)
access_token = await manager.get_access_token(session_id)
```

Implement the `TokenStore` protocol to plug in your own storage backend (Redis,
database, encrypted cookies).

## FastAPI Integration

See [docs/fastapi-integration.md](docs/fastapi-integration.md) for a full guide
covering three wiring patterns: `app.state`, dependency overrides, and router
factories.

Quick start with `app.state`:

```python
from fastapi import Depends, FastAPI
from oidcutils.contrib.fastapi import FastAPIAuth, current_user, require_permission
from oidcutils import Principal

app = FastAPI()
app.state.auth = FastAPIAuth(
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

## Local Development

Run a development identity provider with no external provider and nothing to
configure:

```bash
uv run python -m oidcutils.idp --port 9000 --audience my-api
```

It serves discovery, JWKS and `POST /dev/token`, signing with an ES256 key
generated in memory. Point your app at it:

```bash
OIDC_ISSUER=http://127.0.0.1:9000
OIDC_AUDIENCE=my-api
```

Mint a token with whatever claims a test needs:

```bash
curl -s -XPOST http://127.0.0.1:9000/dev/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-1", "roles": ["admin"]}'
```

Built on `http.server`, so it needs nothing beyond this package. Supply
`--signing-key` or `OIDC_DEV_SIGNING_KEY` where tokens have to survive a
restart. For a single-process loop, `create_dev_idp` returns the same provider
as a mountable app.

It issues a signed token to anyone who asks, so it belongs on a developer's
machine and nowhere else. See [Local Development](docs/examples/local-dev.md).

## Custom Claim Mapping

If your IdP uses non-standard claim names, configure the mapper:

```python
from oidcutils.claims import DefaultClaimMapper

mapper = DefaultClaimMapper(
    roles_claim="realm_roles",
    permissions_claim="scope_perms",
    tenant_claim="org_id",
)
```

Or implement the `ClaimMapper` protocol for full control over how JWT claims
become a `Principal`.

## The Principal Model

| Field         | Type               | Source claim |
| ------------- | ------------------ | ------------ |
| `subject`     | `str`              | `sub`        |
| `issuer`      | `str`              | `iss`        |
| `audience`    | `str \| list[str]` | `aud`        |
| `email`       | `str \| None`      | `email`      |
| `name`        | `str \| None`      | `name`       |
| `tenant_id`   | `str \| None`      | configurable |
| `roles`       | `frozenset[str]`   | configurable |
| `permissions` | `frozenset[str]`   | configurable |
| `raw_claims`  | `dict`             | full JWT     |

Helper methods: `has_role()`, `has_permission()`, `has_any_role()`,
`has_all_permissions()`.

## Architecture

```text
oidcutils/
├── principal.py          # Identity model
├── claims.py             # Claim-to-Principal mapping
├── resource.py           # Token validation (joserfc)
├── client.py             # OIDC client (Authlib)
├── tokens.py             # Token storage and auto-refresh
├── dev.py                # Dev signing key, minting, JWKS, discovery
├── idp.py                # Standalone dev provider (http.server)
├── mint.py               # Mint a dev token from the command line
├── testing.py            # Test helpers for apps using the SDK
└── contrib/
    └── fastapi.py        # FastAPI dependency functions
```

The core package depends on [Authlib](https://authlib.org/) (OAuth2 client),
[joserfc](https://jose.authlib.org/) (JWT/JWKS validation), and
[httpx](https://www.python-httpx.org/) (async HTTP). The FastAPI adapter is an
optional extra. Swapping out the JWT library later changes `resource.py` only;
the `Principal` model and contrib layer stay stable.

## Development

```bash
uv sync --dev
uv run pytest tests/ -v
bin/lint
```
