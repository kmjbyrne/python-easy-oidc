import time

import pytest

from oauth2.client import TokenSet
from oauth2.tokens import InMemoryTokenStore, TokenManager


class FakeOIDCClient:
    def __init__(self, refreshed_token: dict | None = None) -> None:
        self.refresh_calls: list[str] = []
        self._refreshed = refreshed_token or {
            "access_token": "new-access",
            "token_type": "Bearer",
            "refresh_token": "new-refresh",
            "expires_at": time.time() + 3600,
        }

    async def refresh(self, refresh_token: str) -> TokenSet:
        self.refresh_calls.append(refresh_token)
        return TokenSet(
            access_token=self._refreshed["access_token"],
            token_type=self._refreshed["token_type"],
            refresh_token=self._refreshed.get("refresh_token"),
            expires_at=self._refreshed.get("expires_at"),
            raw=self._refreshed,
        )


@pytest.mark.asyncio
async def test_returns_valid_token():
    store = InMemoryTokenStore()
    manager = TokenManager(client=FakeOIDCClient(), store=store)

    token_set = TokenSet(
        access_token="valid-token",
        expires_at=time.time() + 3600,
    )
    await manager.store_token("user-1", token_set)

    result = await manager.get_access_token("user-1")
    assert result == "valid-token"


@pytest.mark.asyncio
async def test_refreshes_expired_token():
    fake_client = FakeOIDCClient()
    manager = TokenManager(client=fake_client)

    token_set = TokenSet(
        access_token="old-token",
        refresh_token="refresh-abc",
        expires_at=time.time() - 100,
    )
    await manager.store_token("user-1", token_set)

    result = await manager.get_access_token("user-1")
    assert result == "new-access"
    assert fake_client.refresh_calls == ["refresh-abc"]


@pytest.mark.asyncio
async def test_refreshes_within_margin():
    fake_client = FakeOIDCClient()
    manager = TokenManager(client=fake_client, refresh_margin_seconds=60)

    token_set = TokenSet(
        access_token="almost-expired",
        refresh_token="refresh-abc",
        expires_at=time.time() + 30,
    )
    await manager.store_token("user-1", token_set)

    result = await manager.get_access_token("user-1")
    assert result == "new-access"


@pytest.mark.asyncio
async def test_no_refresh_token_raises():
    manager = TokenManager(client=FakeOIDCClient())

    token_set = TokenSet(
        access_token="expired",
        expires_at=time.time() - 100,
    )
    await manager.store_token("user-1", token_set)

    with pytest.raises(ValueError, match="no refresh token"):
        await manager.get_access_token("user-1")


@pytest.mark.asyncio
async def test_missing_key_raises():
    manager = TokenManager(client=FakeOIDCClient())

    with pytest.raises(LookupError, match="No token stored"):
        await manager.get_access_token("nonexistent")


@pytest.mark.asyncio
async def test_preserves_refresh_token_when_not_rotated():
    fake_client = FakeOIDCClient(
        refreshed_token={
            "access_token": "new-access",
            "token_type": "Bearer",
            "expires_at": time.time() + 3600,
        }
    )
    store = InMemoryTokenStore()
    manager = TokenManager(client=fake_client, store=store)

    token_set = TokenSet(
        access_token="old",
        refresh_token="original-refresh",
        expires_at=time.time() - 100,
    )
    await manager.store_token("user-1", token_set)
    await manager.get_access_token("user-1")

    stored = await store.get("user-1")
    assert stored is not None
    assert stored.refresh_token == "original-refresh"


@pytest.mark.asyncio
async def test_clear():
    manager = TokenManager(client=FakeOIDCClient())

    await manager.store_token("user-1", TokenSet(access_token="x"))
    await manager.clear("user-1")

    with pytest.raises(LookupError):
        await manager.get_access_token("user-1")


def test_token_set_expired():
    assert TokenSet(access_token="x", expires_at=time.time() - 10).expired
    assert not TokenSet(access_token="x", expires_at=time.time() + 10).expired
    assert not TokenSet(access_token="x").expired
