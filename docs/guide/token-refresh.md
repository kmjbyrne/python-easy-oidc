# Token Refresh

The SDK manages token lifecycle through `OIDCClient` and `TokenManager`.

## The Problem

Every resource provider that acts as an OAuth2 client needs the same refresh
logic: check if the access token is expired (or close to it), use the refresh
token to get a new one, store the result. Reimplementing this per service is
tedious and error-prone.

## OIDCClient

Handles the OAuth2/OIDC protocol flows:

```python
from oidcutils import OIDCClient

client = OIDCClient(
    issuer="https://id.example.com",
    client_id="my-app",
    client_secret="secret",
    redirect_uri="http://localhost:8000/auth/callback",
    scopes=["openid", "profile", "email"],  # defaults
)
```

### Authorization URL

```python
url, state = await client.authorization_url()
# Redirect the user to `url`
```

### Code Exchange

```python
token_set = await client.exchange_code(code)
# token_set.access_token, token_set.refresh_token, token_set.expires_at
```

### Manual Refresh

```python
new_token_set = await client.refresh(token_set.refresh_token)
```

## TokenManager

Wraps storage and auto-refresh so consumers never think about token lifecycle:

```python
from oidcutils import TokenManager

manager = TokenManager(client)

# After login
await manager.store_token(session_id, token_set)

# On every request -- returns a valid access token, refreshing if needed
access_token = await manager.get_access_token(session_id)
```

The manager refreshes proactively: by default, it refreshes 30 seconds before
expiry rather than waiting for the token to actually expire.

```python
manager = TokenManager(client, refresh_margin_seconds=60)
```

## Token Storage

The `TokenStore` protocol defines where tokens live between requests:

```python
from oidcutils import TokenStore, TokenSet


class RedisTokenStore:
    async def get(self, key: str) -> TokenSet | None: ...
    async def set(self, key: str, token_set: TokenSet) -> None: ...
    async def delete(self, key: str) -> None: ...
```

The SDK ships `InMemoryTokenStore` for scripts and tests. For web apps, write
the protocol with your preferred backend (Redis, database, encrypted session).

```python
manager = TokenManager(client, store=RedisTokenStore(redis))
```

## Refresh Token Rotation

Some IdPs rotate the refresh token on each use (returning a new one alongside
the new access token). The `TokenManager` handles this: if the IdP returns a new
refresh token, it stores it. If the IdP omits the refresh token from the
response, the manager preserves the original.
