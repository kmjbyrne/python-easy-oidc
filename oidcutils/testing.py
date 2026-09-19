"""Test helpers for apps using the SDK.

Provides token minting, header helpers, and a reusable test generator that
verifies auth protection on any endpoint.

Usage in conftest.py:

    from oidcutils.testing import dev_token, auth_header

Usage for endpoint protection tests:

    from oidcutils.testing import assert_protected

    def test_orders_requires_auth(client):
        assert_protected(client, "/orders")

    def test_orders_requires_role(client):
        assert_protected(client, "/orders", required_role="admin")

    def test_orders_requires_permission(client):
        assert_protected(client, "/orders", required_permission="orders.read")
"""

from typing import Any

from fastapi.testclient import TestClient

from oidcutils.dev import mint_token

DEFAULT_ISSUER = "http://localhost:8000"
DEFAULT_AUDIENCE = "dev"


def dev_token(
    *,
    subject: str = "test-user",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    issuer: str = DEFAULT_ISSUER,
    audience: str = DEFAULT_AUDIENCE,
    **kwargs: Any,
) -> str:
    """Mint a dev JWT and return just the access_token string."""
    result = mint_token(
        issuer=issuer,
        audience=audience,
        subject=subject,
        roles=roles,
        permissions=permissions,
        **kwargs,
    )
    return str(result["access_token"])


def auth_header(
    token: str | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Return an Authorization header dict. Mints a token if none provided."""
    if token is None:
        token = dev_token(**kwargs)
    return {"Authorization": f"Bearer {token}"}


def assert_protected(
    client: TestClient,
    path: str,
    *,
    method: str = "get",
    required_role: str | None = None,
    required_permission: str | None = None,
) -> None:
    """Verify that an endpoint enforces auth, roles, and permissions.

    Runs up to five assertions depending on which kwargs are provided:
    - Always: 401 without token, 401 with garbage token, 200 with valid token
    - If required_role: 403 without that role
    - If required_permission: 403 without that permission
    """
    fn = getattr(client, method)

    # No token -> 401
    resp = fn(path)
    assert resp.status_code == 401, f"no token: expected 401, got {resp.status_code}"

    # Garbage token -> 401
    resp = fn(path, headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401, f"bad token: expected 401, got {resp.status_code}"

    # Valid token with all required claims -> 200
    roles = [required_role] if required_role else []
    permissions = [required_permission] if required_permission else []
    token = dev_token(roles=roles, permissions=permissions)
    resp = fn(path, headers=auth_header(token))
    assert resp.status_code == 200, (
        f"valid token: expected 200, got {resp.status_code}: {resp.text}"
    )

    # Wrong role -> 403
    if required_role:
        token = dev_token(roles=["wrong-role"], permissions=permissions)
        resp = fn(path, headers=auth_header(token))
        assert resp.status_code == 403, f"wrong role: expected 403, got {resp.status_code}"

    # Wrong permission -> 403
    if required_permission:
        token = dev_token(roles=roles, permissions=["wrong.perm"])
        resp = fn(path, headers=auth_header(token))
        assert resp.status_code == 403, f"wrong permission: expected 403, got {resp.status_code}"
