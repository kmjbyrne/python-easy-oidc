# Installation

## Basic

```bash
pip install oauth2
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add oauth2
```

## With FastAPI Support

```bash
pip install oauth2[fastapi]
```

```bash
uv add oauth2[fastapi]
```

The FastAPI extra pulls in `fastapi` as a dependency. The core package depends
only on:

- [Authlib](https://authlib.org/) -- OAuth2 client flows
- [joserfc](https://jose.authlib.org/) -- JWT/JWKS validation
- [httpx](https://www.python-httpx.org/) -- async HTTP

## Requirements

- Python 3.12+
