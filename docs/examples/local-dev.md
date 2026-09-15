# Local Development

A self-contained setup for testing the SDK without a real identity provider.

## What's Included

Two FastAPI services mounted on a single app:

- **`/idp`** -- a fake OIDC provider that mints JWT access tokens and serves
  discovery/JWKS
- **`/api`** -- an example resource server that validates tokens using the SDK

## Running It

```bash
uv run uvicorn examples.combined:app --port 8000
```

## Test the Flow

Mint a token:

```bash
TOKEN=$(curl -s http://localhost:8000/idp/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-1", "roles": ["admin"], "permissions": ["orders.read", "orders.write"]}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Use it:

```bash
curl -s http://localhost:8000/api/me -H "Authorization: Bearer $TOKEN" | python -m json.tool
curl -s http://localhost:8000/api/orders -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Test denied access:

```bash
TOKEN_VIEWER=$(curl -s http://localhost:8000/idp/token \
  -H 'Content-Type: application/json' \
  -d '{"subject": "user-2", "roles": ["viewer"]}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 403 -- no orders.write permission
curl -s http://localhost:8000/api/orders -X POST -H "Authorization: Bearer $TOKEN_VIEWER"

# 403 -- no admin role
curl -s http://localhost:8000/api/admin -H "Authorization: Bearer $TOKEN_VIEWER"
```

## Key Rotation

Restart the server to generate a new signing key. The SDK detects the unknown
`kid` and refreshes its JWKS cache automatically.
