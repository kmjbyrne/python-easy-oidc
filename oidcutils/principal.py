from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    subject: str
    issuer: str
    audience: str | list[str] = ""
    email: str | None = None
    name: str | None = None
    tenant_id: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    raw_claims: dict = field(default_factory=dict, repr=False)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any_role(self, *roles: str) -> bool:
        return bool(self.roles & set(roles))

    def has_all_permissions(self, *permissions: str) -> bool:
        return set(permissions) <= self.permissions
