from oauth2.claims import DefaultClaimMapper


def test_default_mapper_standard_claims():
    claims = {
        "sub": "user-123",
        "iss": "https://id.example.com",
        "aud": "my-api",
        "email": "user@example.com",
        "name": "Test User",
        "roles": ["admin"],
        "permissions": ["orders.read", "orders.write"],
        "tenant_id": "tenant-abc",
    }
    principal = DefaultClaimMapper().map(claims)

    assert principal.subject == "user-123"
    assert principal.issuer == "https://id.example.com"
    assert principal.audience == "my-api"
    assert principal.email == "user@example.com"
    assert principal.name == "Test User"
    assert principal.tenant_id == "tenant-abc"
    assert principal.roles == frozenset({"admin"})
    assert principal.permissions == frozenset({"orders.read", "orders.write"})
    assert principal.raw_claims == claims


def test_default_mapper_minimal_claims():
    claims = {"sub": "user-1", "iss": "https://id.example.com"}
    principal = DefaultClaimMapper().map(claims)

    assert principal.subject == "user-1"
    assert principal.roles == frozenset()
    assert principal.permissions == frozenset()
    assert principal.email is None
    assert principal.tenant_id is None


def test_custom_claim_names():
    claims = {
        "sub": "user-1",
        "iss": "https://id.example.com",
        "realm_roles": ["manager"],
        "scope_perms": ["read"],
        "org_id": "org-99",
    }
    mapper = DefaultClaimMapper(
        roles_claim="realm_roles",
        permissions_claim="scope_perms",
        tenant_claim="org_id",
    )
    principal = mapper.map(claims)

    assert principal.roles == frozenset({"manager"})
    assert principal.permissions == frozenset({"read"})
    assert principal.tenant_id == "org-99"
