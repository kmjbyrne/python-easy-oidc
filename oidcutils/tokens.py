import time
from typing import Protocol

from oidcutils.client import OIDCClient, TokenSet


class TokenStore(Protocol):
    """Where tokens live between requests. Implement per framework."""

    async def get(self, key: str) -> TokenSet | None: ...
    async def set(self, key: str, token_set: TokenSet) -> None: ...
    async def delete(self, key: str) -> None: ...


class InMemoryTokenStore:
    """Good for CLIs, scripts, and tests. Not for multi-process web apps."""

    def __init__(self) -> None:
        self._store: dict[str, TokenSet] = {}

    async def get(self, key: str) -> TokenSet | None:
        return self._store.get(key)

    async def set(self, key: str, token_set: TokenSet) -> None:
        self._store[key] = token_set

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class TokenManager:
    """Manages token lifecycle: storage, expiry check, auto-refresh.

    Consumers call `get_access_token(key)` and get back a valid token string.
    The manager handles refresh transparently.
    """

    def __init__(
        self,
        client: OIDCClient,
        store: TokenStore | None = None,
        refresh_margin_seconds: float = 30,
    ) -> None:
        self._client = client
        self._store = store or InMemoryTokenStore()
        self._margin = refresh_margin_seconds

    async def store_token(self, key: str, token_set: TokenSet) -> None:
        await self._store.set(key, token_set)

    async def get_access_token(self, key: str) -> str:
        """Return a valid access token, refreshing if needed."""
        token_set = await self._store.get(key)
        if token_set is None:
            raise LookupError(f"No token stored for key: {key}")

        if not self._needs_refresh(token_set):
            return token_set.access_token

        if token_set.refresh_token is None:
            raise ValueError("Access token expired and no refresh token available")

        new_token_set = await self._client.refresh(token_set.refresh_token)

        if new_token_set.refresh_token is None:
            new_token_set = TokenSet(
                access_token=new_token_set.access_token,
                token_type=new_token_set.token_type,
                refresh_token=token_set.refresh_token,
                expires_at=new_token_set.expires_at,
                id_token=new_token_set.id_token,
                scope=new_token_set.scope,
                raw=new_token_set.raw,
            )

        await self._store.set(key, new_token_set)
        return new_token_set.access_token

    async def clear(self, key: str) -> None:
        await self._store.delete(key)

    def _needs_refresh(self, token_set: TokenSet) -> bool:
        if token_set.expires_at is None:
            return False
        return time.time() >= (token_set.expires_at - self._margin)
