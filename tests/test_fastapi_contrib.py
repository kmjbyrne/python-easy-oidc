import time
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from joserfc import jwt as jose_jwt
from joserfc.jwk import RSAKey

from oidcutils import Principal
from oidcutils.contrib.fastapi import (
    FastAPIAuth,
    current_user,
    require_permission,
    require_role,
)

ISSUER = "https://id.example.com"
AUDIENCE = "my-api"

SIGNING_KEY = RSAKey.generate_key(2048)


def _public_jwks() -> dict[str, Any]:
    pub = SIGNING_KEY.as_dict(is_private=False)
    pub["kid"] = "test-key-1"
    return {"keys": [pub]}


def _make_token(claims: dict[str, Any] | None = None) -> str:
    header = {"alg": "RS256", "kid": "test-key-1"}
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "email": "user@example.com",
        "roles": ["admin"],
        "permissions": ["orders.read", "orders.write"],
        **(claims or {}),
    }
    return jose_jwt.encode(header, payload, SIGNING_KEY)


class FakeTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
                },
            )
        if url.endswith("/jwks.json"):
            return httpx.Response(200, json=_public_jwks())
        return httpx.Response(404)


def _create_app() -> FastAPI:
    app = FastAPI()

    app.state.auth = FastAPIAuth(
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    app.state.auth._validator._client = httpx.AsyncClient(transport=FakeTransport())

    @app.get("/me")
    async def me(user=Depends(current_user)):
        return {"sub": user.subject, "email": user.email}

    @app.get("/admin")
    async def admin(user=Depends(require_role("admin"))):
        return {"sub": user.subject}

    @app.get("/orders")
    async def orders(user=Depends(require_permission("orders.read"))):
        return {"sub": user.subject}

    @app.get("/secret")
    async def secret(user=Depends(require_permission("secret.access"))):
        return {"sub": user.subject}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_create_app())


def _auth_header(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or _make_token()}"}


def test_current_user(client: TestClient):
    resp = client.get("/me", headers=_auth_header())
    assert resp.status_code == 200
    assert resp.json()["sub"] == "user-123"
    assert resp.json()["email"] == "user@example.com"


def test_no_token(client: TestClient):
    resp = client.get("/me")
    assert resp.status_code == 401


def test_invalid_token(client: TestClient):
    resp = client.get("/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_require_role_allowed(client: TestClient):
    resp = client.get("/admin", headers=_auth_header())
    assert resp.status_code == 200


def test_require_role_denied(client: TestClient):
    token = _make_token({"roles": ["viewer"]})
    resp = client.get("/admin", headers=_auth_header(token))
    assert resp.status_code == 403


def test_require_permission_allowed(client: TestClient):
    resp = client.get("/orders", headers=_auth_header())
    assert resp.status_code == 200


def test_require_permission_denied(client: TestClient):
    resp = client.get("/secret", headers=_auth_header())
    assert resp.status_code == 403


def test_expired_token(client: TestClient):
    token = _make_token({"exp": int(time.time()) - 100})
    resp = client.get("/me", headers=_auth_header(token))
    assert resp.status_code == 401


def test_unconfigured_auth_raises():
    """An app with no auth wired must fail loudly, not serve an anonymous principal."""
    app = FastAPI()

    @app.get("/me")
    async def me(user=Depends(current_user)):
        return {"sub": user.subject}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/me", headers=_auth_header())
    assert resp.status_code == 500


def test_unconfigured_auth_message():
    app = FastAPI()

    @app.get("/me")
    async def me(user=Depends(current_user)):
        return {"sub": user.subject}

    with pytest.raises(RuntimeError, match="No FastAPIAuth configured"):
        TestClient(app).get("/me", headers=_auth_header())


def _override_app() -> FastAPI:
    """An app supplying its own principal, without touching app.state."""

    async def app_current_user() -> Principal:
        raise NotImplementedError

    app = FastAPI()

    @app.get("/admin")
    async def admin(
        user=Depends(require_role("admin", user_dependency=app_current_user)),
    ):
        return {"sub": user.subject}

    @app.get("/orders")
    async def orders(
        user=Depends(require_permission("orders.read", user_dependency=app_current_user)),
    ):
        return {"sub": user.subject}

    app.state._current_user = app_current_user
    return app


def _sign_in(app: FastAPI, **kwargs) -> None:
    principal = Principal(subject="u-1", issuer=ISSUER, audience=AUDIENCE, **kwargs)
    app.dependency_overrides[app.state._current_user] = lambda: principal


def test_guard_uses_supplied_dependency_allowed():
    app = _override_app()
    _sign_in(app, roles=frozenset({"admin"}), permissions=frozenset({"orders.read"}))
    client = TestClient(app)
    assert client.get("/admin").status_code == 200
    assert client.get("/orders").status_code == 200


def test_guard_uses_supplied_dependency_denied():
    app = _override_app()
    _sign_in(app, roles=frozenset({"viewer"}), permissions=frozenset({"orders.write"}))
    client = TestClient(app)
    assert client.get("/admin").status_code == 403
    assert client.get("/orders").status_code == 403


def test_guard_defaults_to_current_user():
    """Omitting user_dependency keeps the app.state behaviour."""
    import inspect

    assert inspect.signature(require_role).parameters["user_dependency"].default is current_user
    assert (
        inspect.signature(require_permission).parameters["user_dependency"].default is current_user
    )


class TestSuppliedHttpClient:
    """``http_client`` reaching an issuer that is not on the network.

    An in-process provider is mounted rather than listening on a port, so the
    validator cannot fetch its keys over a socket. Passing a client is what
    makes that reachable, and it is the supported way to do it: a caller
    reaching into the validator to swap its client is one rename from breaking.
    """

    async def test_keys_are_fetched_through_the_supplied_client(self):
        keys = FastAPI()

        @keys.get("/.well-known/openid-configuration")
        async def discovery() -> dict[str, Any]:
            return {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/.well-known/jwks.json"}

        @keys.get("/.well-known/jwks.json")
        async def jwks() -> dict[str, Any]:
            return _public_jwks()

        auth = FastAPIAuth(
            issuer=ISSUER,
            audience=AUDIENCE,
            http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=keys), base_url=ISSUER),
        )
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_make_token())

        principal = await auth.get_principal(credentials)

        assert principal.subject == "user-123"
