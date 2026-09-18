# Local Development

A self-contained setup for testing the SDK without a real identity provider.
See `examples/combined.py`.

## What's Included

Two FastAPI applications behind subdomain routing on a single port:

- **`auth.127.0.0.1.nip.io:8000`** -- a fake OIDC provider that mints JWT access
  tokens and serves discovery/JWKS
- **`api.127.0.0.1.nip.io:8000`** -- an example resource server that validates
  tokens using the SDK

Both names resolve to `127.0.0.1` through [nip.io](https://nip.io), so no hosts
file is needed. Browsers treat them as separate origins, which is what makes
`SameSite=Strict` cookies behave as they would in production.

## Running It

```bash
uv run uvicorn examples.combined:app --port 8000
```

!!! warning "Use port 8000"
    The issuer URL is built from a `PORT` constant in the example, and the token
    `iss` claim and discovery document are pinned to it. Serving on another port
    makes the API validate tokens against an issuer that is not listening, and
    every authenticated request fails with a connection error.

## Test the Flow

Mint a token:

```bash
TOKEN=$(curl -s http://auth.127.0.0.1.nip.io:8000/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-1", "roles": ["admin"], "permissions": ["orders.read", "orders.write"]}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Use it:

```bash
curl -s http://api.127.0.0.1.nip.io:8000/me -H "Authorization: Bearer $TOKEN" | python -m json.tool
curl -s http://api.127.0.0.1.nip.io:8000/orders -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Test denied access:

```bash
TOKEN_VIEWER=$(curl -s http://auth.127.0.0.1.nip.io:8000/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-2", "roles": ["viewer"]}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 403 -- no orders.write permission
curl -s http://api.127.0.0.1.nip.io:8000/orders -X POST -H "Authorization: Bearer $TOKEN_VIEWER"

# 403 -- no admin role
curl -s http://api.127.0.0.1.nip.io:8000/admin -H "Authorization: Bearer $TOKEN_VIEWER"
```

Missing and malformed tokens are rejected before any role check:

```bash
# 401 -- no credentials
curl -s -o /dev/null -w '%{http_code}\n' http://api.127.0.0.1.nip.io:8000/me

# 401 -- not a valid token
curl -s -o /dev/null -w '%{http_code}\n' http://api.127.0.0.1.nip.io:8000/me \
  -H 'Authorization: Bearer garbage'
```

## Browser Flow

Open <http://api.127.0.0.1.nip.io:8000/auth/login> to exercise the
authorization code flow. It redirects through the IdP, exchanges the code, and
sets an httponly `session_id` cookie.

Form parsing at the token endpoint needs `python-multipart`, which the browser
flow uses and the curl flow above does not:

```bash
uv add --dev python-multipart
```

!!! note "The landing page returns 401"
    `post_login_redirect` sends the browser to `/me`, which depends on
    `current_user` and therefore reads a bearer header, not the session cookie.
    The cookie is set correctly; nothing in the example exchanges it for a
    principal. Resolving the session into an access token is the application's
    job -- see [Token Refresh](../guide/token-refresh.md) for `TokenManager`,
    which is what `create_auth_router` stores the token set in.

## Without The Example App

`examples/combined.py` is a full IdP: an authorization endpoint, a code flow,
subdomain routing. When all you need is tokens with particular roles, the SDK
can mount a minimal dev provider into your own app instead.

Set `OIDC_BYPASS` and call `configure`:

```python
from oauth2.contrib.fastapi import OIDCSettings, configure


class Settings(OIDCSettings, BaseSettings):
    OIDC_ISSUER: str = "http://localhost:8000"
    OIDC_AUDIENCE: str = "dev"
    OIDC_BYPASS: bool = False


configure(app, settings)
```

With `OIDC_BYPASS` true, `configure` mounts discovery, JWKS and a
`POST /dev/token` endpoint on the app, then points the validator at them. It
sets `app.state.auth` either way, so routes and guards are unchanged. With it
false you get the ordinary `FastAPIAuth` against your real provider.

Mint a token with whatever claims the test needs:

```bash
curl -s -X POST http://localhost:8000/dev/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-1", "roles": ["admin"], "permissions": ["orders.write"]}'
```

The endpoint fills in the issuer and audience from settings. Passing either in
the body raises a `TypeError`, because they are already bound.

!!! danger "Development only"
    The dev provider issues a signed token to any unauthenticated caller, with
    any roles they ask for. Guard `OIDC_BYPASS` so it can never be true outside
    development, for example by rejecting it in a settings validator.

## Key Rotation

Restart the server to generate a new signing key. The SDK detects the unknown
`kid` and refreshes its JWKS cache automatically.
