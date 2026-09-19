# Development

## Setup

```bash
uv sync --dev --group docs
```

This installs runtime deps, dev tools (pytest, ruff, mypy), and documentation
dependencies (mkdocs-material, mkdocstrings).

## Tests

```bash
uv run pytest tests/ -v
```

All tests use fake HTTP transports and ephemeral RSA keys. No real IdP or
network access required.

## Linting and Type Checking

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

## Documentation

Build and serve locally:

```bash
uv run mkdocs serve
```

Build for deployment:

```bash
uv run mkdocs build
```

The site outputs to `site/`. Documentation source lives in `docs/` and is
configured by `mkdocs.yml`.

## Examples

Run the combined local IdP + resource server:

```bash
uv run uvicorn examples.combined:app --port 8000
```

Or run them separately:

```bash
uv run uvicorn examples.local_idp:app --port 9000
uv run uvicorn examples.resource_server:app --port 8000
```

See `examples/README.md` for the full walkthrough.

## Project Layout

```text
oidcutils/
├── principal.py      # Identity model
├── claims.py         # Claim-to-Principal mapping
├── resource.py       # Token validation (joserfc)
├── client.py         # OIDC client (Authlib)
├── tokens.py         # Token storage and auto-refresh
├── dev.py            # Dev signing key, minting, JWKS, discovery
├── idp.py            # Standalone dev provider (http.server)
├── mint.py           # Mint a dev token from the command line
├── testing.py        # Test helpers for apps using the SDK
└── contrib/
    └── fastapi.py    # FastAPI dependency functions

tests/
├── test_principal.py
├── test_claims.py
├── test_resource.py
├── test_tokens.py
├── test_fastapi_contrib.py
└── test_idp.py

docs/                 # MkDocs Material source
examples/             # Runnable local IdP + resource server
```

## Making Changes

1. Write tests first.
2. Run `uv run pytest tests/ -v` to verify.
3. Run `uv run ruff check src/ tests/` before committing.
4. Update docs if the public API changed.
