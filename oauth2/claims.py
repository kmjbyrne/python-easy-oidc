from typing import Any, Protocol

from oauth2.principal import Principal


class ClaimMapper(Protocol):
    def map(self, claims: dict[str, Any]) -> Principal: ...


class DefaultClaimMapper:
    """Maps standard OIDC and common IdP claims to a Principal."""

    def __init__(
        self,
        roles_claim: str = "roles",
        permissions_claim: str = "permissions",
        tenant_claim: str = "tenant_id",
    ) -> None:
        self._roles_claim = roles_claim
        self._permissions_claim = permissions_claim
        self._tenant_claim = tenant_claim

    def map(self, claims: dict[str, Any]) -> Principal:
        return Principal(
            subject=claims["sub"],
            issuer=claims["iss"],
            audience=claims.get("aud", ""),
            email=claims.get("email"),
            name=claims.get("name"),
            tenant_id=claims.get(self._tenant_claim),
            roles=frozenset(claims.get(self._roles_claim, [])),
            permissions=frozenset(claims.get(self._permissions_claim, [])),
            raw_claims=claims,
        )
