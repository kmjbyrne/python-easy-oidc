from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from oauth2.claims import ClaimMapper
from oauth2.client import OIDCClient
from oauth2.principal import Principal
from oauth2.resource import TokenError, TokenValidator
from oauth2.tokens import InMemoryTokenStore, TokenManager


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
    ) -> None:
        self._validator = TokenValidator(
            issuer=issuer,
            audience=audience,
            algorithms=algorithms,
            claim_mapper=claim_mapper,
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


_BYPASS_PRINCIPAL = Principal(
    subject="anonymous",
    issuer="bypass",
)


def _get_auth(request: Request) -> FastAPIAuth | None:
    return getattr(request.app.state, "auth", None)


async def current_user(
    auth: FastAPIAuth | None = Depends(_get_auth),
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> Principal:
    if auth is None:
        return _BYPASS_PRINCIPAL
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await auth.get_principal(credentials)


def require_role(role: str) -> Callable[..., Any]:
    async def dependency(
        user: Principal = Depends(current_user),
    ) -> Principal:
        if not user.has_role(role):
            raise HTTPException(
                status_code=403,
                detail=f"Required role: {role}",
            )
        return user

    return dependency


def require_permission(permission: str) -> Callable[..., Any]:
    async def dependency(
        user: Principal = Depends(current_user),
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
    from oauth2.dev import discovery_document, mint_token, public_jwks

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


def configure_dev(app: FastAPI, settings: OIDCSettings) -> None:
    """Set up auth with a built-in dev IdP. No external provider needed."""
    issuer = settings.OIDC_ISSUER or "http://localhost:8000"
    audience = settings.OIDC_AUDIENCE or "dev"

    app.include_router(create_dev_router(issuer=issuer, audience=audience))

    app.state.auth = FastAPIAuth(issuer=issuer, audience=audience)
