# FastAPI Integration

Three patterns for wiring auth into FastAPI. See the comparison table below for
trade-offs.

!!! tip "Recommended: App State"
    The `app.state` pattern gives you the cleanest routes with built-in
    `require_permission` and `require_role` support.

## Pattern 1: App State

Store the auth instance on `app.state`. The SDK's dependency functions resolve it
from the request automatically.

```python
from fastapi import Depends, FastAPI
from oauth2.contrib.fastapi import FastAPIAuth, current_user, require_permission
from oauth2 import Principal


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.auth = FastAPIAuth(
        issuer=settings.OIDC_ISSUER,
        audience=settings.OIDC_AUDIENCE,
    )
    app.include_router(orders_router)
    return app
```

`from_settings` is the same thing driven from a settings object. Add
`OIDCSettings` to your own settings class to pick up the field names it reads:

```python
from oauth2.contrib.fastapi import OIDCSettings
from pydantic_settings import BaseSettings


class Settings(OIDCSettings, BaseSettings):
    pass


app.state.auth = FastAPIAuth.from_settings(settings)
```

It reads `OIDC_ISSUER` and `OIDC_AUDIENCE` off the object. Anything else, such
as `algorithms` or `claim_mapper`, passes through as a keyword argument.

Routes use the dependency functions:

```python
@router.get("/orders")
async def list_orders(user: Principal = Depends(current_user)):
    return {"user": user.subject}


@router.post("/orders")
async def create_order(
    user: Principal = Depends(require_permission("orders.write")),
):
    return {"created_by": user.subject}
```

## Pattern 2: Dependency Overrides

Define a stub dependency, override it in the factory:

```python
async def get_current_user() -> Principal:
    raise NotImplementedError


# In routes
@router.get("/orders")
async def list_orders(user: Principal = Depends(get_current_user)): ...


# In factory
app.dependency_overrides[get_current_user] = auth.get_principal
```

!!! note
    Building permission-specific dependencies requires more manual wiring with
    this pattern, since each permission check needs its own override.

## Pattern 3: Router Factories

Pass dependencies into a function that builds the router:

```python
def create_orders_router(current_user=Depends(current_user)) -> APIRouter:
    router = APIRouter()

    @router.get("/orders")
    async def list_orders(user: Principal = current_user):
        return {"user": user.subject}

    return router
```

## Comparison

| Concern                 | App state  | Overrides | Router factories |
| ----------------------- | ---------- | --------- | ---------------- |
| Route readability       | Clean      | Clean     | Clean            |
| Wiring boilerplate      | Low        | Medium    | High             |
| Test isolation          | Good       | Best      | Best             |
| Permission dependencies | Built-in   | Manual    | Manual           |

## Testing

Two approaches, depending on whether the test needs real token validation.

### Override the principal

The quickest option. Override `current_user` and the guards built on it follow,
because FastAPI resolves overrides by function identity through the whole
dependency tree. No token is minted and the validator never reaches the issuer.

```python
from oauth2 import Principal
from oauth2.contrib.fastapi import current_user

app.dependency_overrides[current_user] = lambda: Principal(
    subject="test-user",
    issuer="https://id.example.com",
    audience="my-api",
    roles=frozenset({"admin"}),
    permissions=frozenset({"orders.write"}),
)
```

This covers route and guard behaviour: a principal holding `admin` gets 200
from a `require_role("admin")` route, one holding something else gets 403.

An override always returns a principal, so it cannot produce a 401. Leave it
off to test that case, which exercises the real bearer scheme.

### Serve JWKS from a fake transport

Use this when the test should exercise signature and claim validation. Sign
tokens with a local key and answer discovery and JWKS from a transport, so
nothing leaves the process:

```python
import httpx
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "https://id.example.com"
AUDIENCE = "my-api"
SIGNING_KEY = RSAKey.generate_key(2048)


def public_jwks() -> dict:
    pub = SIGNING_KEY.as_dict(is_private=False)
    pub["kid"] = "test-key-1"
    return {"keys": [pub]}


class FakeTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={"issuer": ISSUER, "jwks_uri": f"{ISSUER}/.well-known/jwks.json"},
            )
        if url.endswith("/jwks.json"):
            return httpx.Response(200, json=public_jwks())
        return httpx.Response(404)


def create_test_app() -> FastAPI:
    app = create_app(test_settings)
    app.state.auth._validator._client = httpx.AsyncClient(transport=FakeTransport())
    return app
```

Mint tokens against the same key with a `kid` matching the JWKS:

```python
token = jwt.encode(
    {"alg": "RS256", "kid": "test-key-1"},
    {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "exp": int(time.time()) + 3600,
        "roles": ["admin"],
    },
    SIGNING_KEY,
)
```

`_validator._client` is private. It is the only injection point after
construction, and `tests/test_fastapi_contrib.py` in this repo uses the same
approach.
