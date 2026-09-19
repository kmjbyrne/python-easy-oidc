# Claim Mapping

Claim mapping converts raw JWT claims into a `Principal`. Different identity
providers use different claim names for the same concepts.

## DefaultClaimMapper

Works out of the box with standard OIDC claims:

```python
from oidcutils.claims import DefaultClaimMapper

mapper = DefaultClaimMapper()
```

| Principal field | Default claim name |
| --------------- | ------------------ |
| `roles`         | `roles`            |
| `permissions`   | `permissions`      |
| `tenant_id`     | `tenant_id`        |

Override the claim names for your IdP:

```python
mapper = DefaultClaimMapper(
    roles_claim="realm_roles",  # Keycloak
    permissions_claim="scope_perms",
    tenant_claim="org_id",
)
```

## Custom Mapper

Implement the `ClaimMapper` protocol for full control:

```python
from oidcutils.claims import ClaimMapper
from oidcutils import Principal


class KeycloakMapper:
    def map(self, claims: dict) -> Principal:
        realm_access = claims.get("realm_access", {})
        return Principal(
            subject=claims["sub"],
            issuer=claims["iss"],
            audience=claims.get("aud", ""),
            email=claims.get("email"),
            name=claims.get("preferred_username"),
            roles=frozenset(realm_access.get("roles", [])),
            permissions=frozenset(claims.get("scope", "").split()),
            raw_claims=claims,
        )
```

Wire it into the validator or FastAPI auth:

```python
from oidcutils import TokenValidator

validator = TokenValidator(
    issuer="https://keycloak.example.com/realms/myrealm",
    audience="my-api",
    claim_mapper=KeycloakMapper(),
)
```

## The Principal Model

All fields:

| Field         | Type               | Source         |
| ------------- | ------------------ | -------------- |
| `subject`     | `str`              | `sub` (always) |
| `issuer`      | `str`              | `iss` (always) |
| `audience`    | `str \| list[str]` | `aud`          |
| `email`       | `str \| None`      | `email`        |
| `name`        | `str \| None`      | `name`         |
| `tenant_id`   | `str \| None`      | configurable   |
| `roles`       | `frozenset[str]`   | configurable   |
| `permissions` | `frozenset[str]`   | configurable   |
| `raw_claims`  | `dict`             | full JWT       |

The `raw_claims` dict gives access to any claim not mapped to a named field.
The `Principal` is frozen (immutable) after creation.
