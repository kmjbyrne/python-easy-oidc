from oidcutils.principal import Principal


def test_has_role():
    p = Principal(
        subject="user-1",
        issuer="https://id.example.com",
        roles=frozenset({"admin", "viewer"}),
    )
    assert p.has_role("admin")
    assert not p.has_role("editor")


def test_has_permission():
    p = Principal(
        subject="user-1",
        issuer="https://id.example.com",
        permissions=frozenset({"orders.read", "orders.write"}),
    )
    assert p.has_permission("orders.read")
    assert not p.has_permission("users.delete")


def test_has_any_role():
    p = Principal(
        subject="user-1",
        issuer="https://id.example.com",
        roles=frozenset({"viewer"}),
    )
    assert p.has_any_role("admin", "viewer")
    assert not p.has_any_role("admin", "editor")


def test_has_all_permissions():
    p = Principal(
        subject="user-1",
        issuer="https://id.example.com",
        permissions=frozenset({"a", "b", "c"}),
    )
    assert p.has_all_permissions("a", "b")
    assert not p.has_all_permissions("a", "d")


def test_frozen():
    p = Principal(subject="user-1", issuer="https://id.example.com")
    try:
        p.subject = "user-2"  # type: ignore[misc]
        raise AssertionError("Should be frozen")
    except AttributeError:
        pass
