# FastAPI Integration

Three patterns for wiring auth into FastAPI. See the comparison table below for
trade-offs.

!!! tip "Recommended: App State"
    The `app.state` pattern gives you the cleanest routes with built-in
    `require_permission` and `require_role` support.

## Pattern 1: App State

Store the auth instance on `app.state`. The SDK's dependency functions resolve it
from the request automatically.

```python
from fastapi import Depends, FastAPI
from oauth2.contrib.fastapi import FastAPIAuth, current_user, require_permission
from oauth2 import Principal


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.auth = FastAPIAuth.from_settings(
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
    )
    app.include_router(orders_router)
    return app
```

Routes use the dependency functions:

```python
@router.get("/orders")
async def list_orders(user: Principal = Depends(current_user)):
    return {"user": user.subject}


@router.post("/orders")
async def create_order(
    user: Principal = Depends(require_permission("orders.write")),
):
    return {"created_by": user.subject}
```

## Pattern 2: Dependency Overrides

Define a stub dependency, override it in the factory:

```python
async def get_current_user() -> Principal:
    raise NotImplementedError


# In routes
@router.get("/orders")
async def list_orders(user: Principal = Depends(get_current_user)): ...


# In factory
app.dependency_overrides[get_current_user] = auth.get_principal
```

!!! note
    Building permission-specific dependencies requires more manual wiring with
    this pattern, since each permission check needs its own override.

## Pattern 3: Router Factories

Pass dependencies into a function that builds the router:

```python
def create_orders_router(current_user=Depends(current_user)) -> APIRouter:
    router = APIRouter()

    @router.get("/orders")
    async def list_orders(user: Principal = current_user):
        return {"user": user.subject}

    return router
```

## Comparison

| Concern                 | App state  | Overrides | Router factories |
| ----------------------- | ---------- | --------- | ---------------- |
| Route readability       | Clean      | Clean     | Clean            |
| Wiring boilerplate      | Low        | Medium    | High             |
| Test isolation          | Good       | Best      | Best             |
| Permission dependencies | Built-in   | Manual    | Manual           |

## Testing

=== "App State"

    ```python
    def create_test_app() -> FastAPI:
        app = create_app(test_settings)
        app.state.auth._validator._client = httpx.AsyncClient(transport=FakeTransport())
        return app
    ```

=== "Dependency Overrides"

    ```python
    app.dependency_overrides[get_current_user] = lambda: Principal(
        subject="test-user",
        issuer="https://test.example.com",
    )
    ```
