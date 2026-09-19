from collections.abc import Callable
from typing import Any

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from oidcutils.claims import ClaimMapper
from oidcutils.client import OIDCClient
from oidcutils.principal import Principal
from oidcutils.resource import TokenError, TokenValidator
from oidcutils.tokens import InMemoryTokenStore, TokenManager


class OIDCSettings:
    """Mixin for pydantic-settings classes. Add to your Settings to get OIDC fields."""

    OIDC_ISSUER: str = ""
    OIDC_AUDIENCE: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_BYPASS: bool = False


_bearer_scheme = HTTPBearer(auto_error=True)


class FastAPIAuth:
    def __init__(
        self,
        issuer: str,
        audience: str,
        *,
        algorithms: list[str] | None = None,
        claim_mapper: ClaimMapper | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Build auth against ``issuer``.

        ``http_client`` is the client used to fetch discovery and JWKS. Pass one
        to reach an issuer that is not on the network: an in-process dev IdP is
        mounted rather than listening on a port, so it is reached with an
        ``httpx.ASGITransport`` rather than a socket.
        """
        self._validator = TokenValidator(
            issuer=issuer,
            audience=audience,
            algorithms=algorithms,
            claim_mapper=claim_mapper,
            http_client=http_client,
        )

    @classmethod
    def from_settings(cls, settings: OIDCSettings, **kwargs: Any) -> "FastAPIAuth":
        return cls(
            issuer=settings.OIDC_ISSUER,
            audience=settings.OIDC_AUDIENCE,
            **kwargs,
        )

    async def get_principal(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    ) -> Principal:
        try:
            return await self._validator.validate_token(credentials.credentials)
        except TokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc


def configure(app: FastAPI, settings: OIDCSettings, **kwargs: Any) -> FastAPIAuth | None:
    """Wire OIDC auth into a FastAPI app from settings.

    When OIDC_BYPASS is True, mounts a built-in dev IdP with discovery, JWKS,
    and a POST /dev/token endpoint. No external provider needed.
    """
    if settings.OIDC_BYPASS:
        configure_dev(app, settings)
        return app.state.auth  # type: ignore[no-any-return]
    auth = FastAPIAuth.from_settings(settings, **kwargs)
    app.state.auth = auth
    return auth


def _get_auth(request: Request) -> FastAPIAuth | None:
    return getattr(request.app.state, "auth", None)


async def current_user(
    auth: FastAPIAuth | None = Depends(_get_auth),
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> Principal:
    """Resolve the caller's Principal from the bearer token.

    Raises RuntimeError when no auth is configured. Returning an anonymous
    principal instead would let an unwired app serve protected routes.
    """
    if auth is None:
        raise RuntimeError(
            "No FastAPIAuth configured. Set app.state.auth in your application "
            "factory, or override the current_user dependency."
        )
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await auth.get_principal(credentials)


def require_role(
    role: str,
    user_dependency: Callable[..., Any] = current_user,
) -> Callable[..., Any]:
    """Build a dependency admitting only callers holding ``role``.

    ``user_dependency`` resolves the Principal. Override it when the app
    supplies its own instead of reading ``app.state.auth``.
    """

    async def dependency(
        user: Principal = Depends(user_dependency),
    ) -> Principal:
        if not user.has_role(role):
            raise HTTPException(
                status_code=403,
                detail=f"Required role: {role}",
            )
        return user

    return dependency


def require_permission(
    permission: str,
    user_dependency: Callable[..., Any] = current_user,
) -> Callable[..., Any]:
    """Build a dependency admitting only callers holding ``permission``.

    ``user_dependency`` resolves the Principal. Override it when the app
    supplies its own instead of reading ``app.state.auth``.
    """

    async def dependency(
        user: Principal = Depends(user_dependency),
    ) -> Principal:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=403,
                detail=f"Required permission: {permission}",
            )
        return user

    return dependency


def create_auth_router(
    client: OIDCClient,
    token_manager: TokenManager | None = None,
    login_path: str = "/login",
    callback_path: str = "/callback",
    post_login_redirect: str = "/",
    session_key: str = "session_id",
) -> APIRouter:
    """Create a router with /login and /callback endpoints for the auth code flow.

    The browser never sees client credentials or tokens. It only follows
    redirects and receives a session cookie.
    """
    store = InMemoryTokenStore()
    manager = token_manager or TokenManager(client=client, store=store)
    _pending_states: dict[str, str] = {}

    router = APIRouter()

    @router.get(login_path)
    async def login(request: Request) -> RedirectResponse:
        url, state = await client.authorization_url()
        _pending_states[state] = post_login_redirect
        return RedirectResponse(url)

    @router.get(callback_path)
    async def callback(request: Request, code: str, state: str) -> RedirectResponse:
        if state not in _pending_states:
            raise HTTPException(400, "Invalid or expired state parameter")

        redirect_to = _pending_states.pop(state)

        token_set = await client.exchange_code(code)

        import secrets

        sid = secrets.token_urlsafe(32)
        await manager.store_token(sid, token_set)

        response = RedirectResponse(redirect_to)
        response.set_cookie(
            key=session_key,
            value=sid,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        return response

    return router


def create_dev_router(issuer: str, audience: str, prefix: str = "/dev") -> APIRouter:
    """Mount discovery, JWKS, and token-minting endpoints for local development."""
    from oidcutils.dev import discovery_document, mint_token, public_jwks

    router = APIRouter()

    @router.get("/.well-known/openid-configuration")
    async def discovery() -> dict[str, Any]:
        return discovery_document(issuer)

    @router.get("/.well-known/jwks.json")
    async def jwks() -> dict[str, Any]:
        return public_jwks()

    @router.post(f"{prefix}/token")
    async def dev_token(request: Request) -> dict[str, Any]:
        body = await request.json() if await request.body() else {}
        return mint_token(issuer=issuer, audience=audience, **body)

    return router


def create_dev_idp(issuer: str, audience: str) -> FastAPI:
    """Return a standalone app serving discovery, JWKS and token minting.

    An app of its own rather than routes added to yours. That keeps the issuer
    a separate thing from the application validating against it, so the app
    makes an ordinary outward request for a key instead of calling itself.

    Run it on its own port, or mount it in-process during development::

        idp = create_dev_idp(issuer="http://localhost:8000/idp", audience="my-api")
        app.mount("/idp", idp)

    ``issuer`` must be the address the IdP answers on, mount path included, so
    that the discovery document points at endpoints a client can actually
    reach. Mounted in-process there is no port to reach it on, so the validator
    needs an ``httpx.ASGITransport`` client: see :func:`dev_auth`.

    It signs with an ephemeral key generated at import and mints a token for
    anybody who asks, so it has no business anywhere but a developer's machine.
    """
    idp = FastAPI(title="Development IdP", docs_url=None, redoc_url=None)
    idp.include_router(create_dev_router(issuer=issuer, audience=audience))
    return idp


def dev_auth(app: FastAPI, issuer: str, audience: str) -> FastAPIAuth:
    """Return auth that reaches an in-process IdP rather than the network.

    ``app`` is whatever the IdP is reachable through: the mounted parent, or
    the IdP itself. Requests for discovery and JWKS are handed straight to it,
    because an app mounted in another process is not listening on a port and a
    test has no server at all.
    """
    return FastAPIAuth(
        issuer=issuer,
        audience=audience,
        http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=issuer),
    )


def configure_dev(app: FastAPI, settings: OIDCSettings) -> None:
    """Set up auth with a built-in dev IdP. No external provider needed."""
    issuer = settings.OIDC_ISSUER or "http://localhost:8000"
    audience = settings.OIDC_AUDIENCE or "dev"

    app.include_router(create_dev_router(issuer=issuer, audience=audience))

    app.state.auth = FastAPIAuth(issuer=issuer, audience=audience)
