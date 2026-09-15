"""
Combined local IdP + resource server using subdomain routing.

    auth.127.0.0.1.nip.io:8000  -- the identity provider
    api.127.0.0.1.nip.io:8000   -- the resource server

Both subdomains resolve to 127.0.0.1 via nip.io, but browsers treat them as
separate origins. Cookies with SameSite=Strict work correctly.

Run:
    uv run uvicorn examples.combined:app --port 8000

Browser flow:
    Open http://api.127.0.0.1.nip.io:8000/auth/login

Curl flow:
    TOKEN=$(curl -s http://auth.127.0.0.1.nip.io:8000/token \
      -H 'Content-Type: application/json' \
      -d '{"subject": "user-1", "roles": ["admin"], "permissions": ["orders.read"]}' \
      | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

    curl -s http://api.127.0.0.1.nip.io:8000/me \
      -H "Authorization: Bearer $TOKEN"
"""

import secrets
import time
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import ECKey
from pydantic import BaseModel
from starlette.routing import Host

from oauth2 import OIDCClient, Principal
from oauth2.contrib.fastapi import (
    FastAPIAuth,
    create_auth_router,
    current_user,
    require_permission,
    require_role,
)

PORT = 8000
IDP_HOST = f"auth.127.0.0.1.nip.io:{PORT}"
API_HOST = f"api.127.0.0.1.nip.io:{PORT}"
ISSUER = f"http://{IDP_HOST}"
API_BASE = f"http://{API_HOST}"
AUDIENCE = "local-api"
CLIENT_ID = "local-app"
CLIENT_SECRET = "local-secret"
TOKEN_LIFETIME = 3600

_signing_key = ECKey.generate_key("P-256")
_pending_codes: dict[str, dict] = {}


def _public_jwks() -> dict:
    pub = _signing_key.as_dict(is_private=False)
    pub["kid"] = "local-dev-key"
    pub["use"] = "sig"
    pub["alg"] = "ES256"
    return {"keys": [pub]}


# --- IdP sub-application ---

idp = FastAPI()


@idp.get("/.well-known/openid-configuration")
async def discovery():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["ES256"],
    }


@idp.get("/.well-known/jwks.json")
async def jwks():
    return _public_jwks()


@idp.get("/authorize")
async def authorize(
    client_id: str = Query(),
    redirect_uri: str = Query(),
    state: str = Query(),
    response_type: str = Query(default="code"),
    scope: str = Query(default="openid"),
):
    code = secrets.token_urlsafe(32)
    _pending_codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "subject": "user-1",
        "email": "user@localhost",
        "name": "Local User",
        "roles": ["admin", "viewer"],
        "permissions": ["orders.read", "orders.write"],
    }
    params = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}?{params}")


class TokenRequest(BaseModel):
    subject: str = "user-1"
    email: str = "user@localhost"
    name: str = "Local User"
    roles: list[str] = []
    permissions: list[str] = []
    lifetime: int = TOKEN_LIFETIME


def _mint(claims_data: dict, lifetime: int = TOKEN_LIFETIME) -> dict:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + lifetime,
        **claims_data,
    }
    header = {"alg": "ES256", "kid": "local-dev-key"}
    token = jwt.encode(header, claims, _signing_key)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": lifetime,
        "refresh_token": secrets.token_urlsafe(32),
    }


@idp.post("/token")
async def token_endpoint(request: Request):
    content_type = request.headers.get("content-type", "")

    if "form" in content_type:
        form = await request.form()
        grant_type = form.get("grant_type", "")
        code = form.get("code", "")

        if grant_type == "authorization_code" and code in _pending_codes:
            code_data = _pending_codes.pop(code)
            return JSONResponse(
                _mint(
                    {
                        "sub": code_data["subject"],
                        "email": code_data["email"],
                        "name": code_data["name"],
                        "roles": code_data["roles"],
                        "permissions": code_data["permissions"],
                    }
                )
            )

        if grant_type == "refresh_token":
            return JSONResponse(
                _mint(
                    {
                        "sub": "user-1",
                        "email": "user@localhost",
                        "name": "Local User",
                        "roles": ["admin", "viewer"],
                        "permissions": ["orders.read", "orders.write"],
                    }
                )
            )

        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    body = await request.json() if await request.body() else {}
    req = TokenRequest(**body)
    return JSONResponse(
        _mint(
            {
                "sub": req.subject,
                "email": req.email,
                "name": req.name,
                "roles": req.roles,
                "permissions": req.permissions,
            },
            req.lifetime,
        )
    )


# --- Resource server sub-application ---

api = FastAPI()

api.state.auth = FastAPIAuth.from_settings(
    issuer=ISSUER,
    audience=AUDIENCE,
)

oidc_client = OIDCClient(
    issuer=ISSUER,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=f"{API_BASE}/auth/callback",
)

auth_router = create_auth_router(
    client=oidc_client,
    post_login_redirect="/me",
)
api.include_router(auth_router, prefix="/auth")


@api.get("/me")
async def me(user: Principal = Depends(current_user)):
    return {
        "subject": user.subject,
        "email": user.email,
        "name": user.name,
        "roles": sorted(user.roles),
        "permissions": sorted(user.permissions),
    }


@api.get("/orders")
async def list_orders(
    user: Principal = Depends(require_permission("orders.read")),
):
    return {
        "orders": [{"id": 1, "item": "widget"}],
        "requested_by": user.subject,
    }


@api.post("/orders")
async def create_order(
    user: Principal = Depends(require_permission("orders.write")),
):
    return {"created_by": user.subject, "status": "ok"}


@api.get("/admin")
async def admin_panel(user: Principal = Depends(require_role("admin"))):
    return {"admin": user.subject}


# --- Subdomain routing ---

app = FastAPI(title="oauth2 Local Development")
app.router.routes.extend(
    [
        Host(IDP_HOST, app=idp, name="idp"),
        Host(API_HOST, app=api, name="api"),
    ]
)
