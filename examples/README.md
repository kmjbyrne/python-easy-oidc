# Examples

A local setup for testing the SDK end-to-end without a real identity provider.

## What's Here

A single `combined.py` that runs both a fake OIDC provider and a resource server
on the same port, using Starlette subdomain routing:

- `auth.127.0.0.1.nip.io:8000` -- the IdP (discovery, JWKS, authorize, token)
- `api.127.0.0.1.nip.io:8000` -- the resource server (protected endpoints +
  login/callback)

Both subdomains resolve to `127.0.0.1` via `nip.io`. Browsers treat them as
separate origins, so cookies and SameSite policies work correctly.

## Running It

```bash
uv run uvicorn examples.combined:app --port 8000
```

## Browser Flow

Open http://api.127.0.0.1.nip.io:8000/auth/login in a browser. You'll be
redirected through the sample IdP and back to `/me` with a session cookie.

## Curl Flow

Mint a token with specific roles and permissions:

```bash
TOKEN=$(curl -s http://auth.127.0.0.1.nip.io:8000/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-1", "roles": ["admin"], "permissions": ["orders.read", "orders.write"]}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Use it against the resource server:

```bash
curl -s http://api.127.0.0.1.nip.io:8000/me \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

curl -s http://api.127.0.0.1.nip.io:8000/orders \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

curl -s http://api.127.0.0.1.nip.io:8000/admin \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Test denied access:

```bash
TOKEN_VIEWER=$(curl -s http://auth.127.0.0.1.nip.io:8000/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-2", "roles": ["viewer"]}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 403 -- no orders.write permission
curl -s http://api.127.0.0.1.nip.io:8000/orders -X POST \
  -H "Authorization: Bearer $TOKEN_VIEWER"

# 403 -- no admin role
curl -s http://api.127.0.0.1.nip.io:8000/admin \
  -H "Authorization: Bearer $TOKEN_VIEWER"
```

## Key Rotation

Restart the server to generate a new signing key. The SDK detects the unknown
`kid` and refreshes its JWKS cache automatically.
