# Installation

## Basic

Install from the repository. The package is not on PyPI, and the `oauth2` name
there belongs to an unrelated project.

```bash
uv pip install git+https://github.com/kmjbyrne/python-easy-oidc.git
```

## With FastAPI Support

```bash
uv pip install "oauth2[fastapi] @ git+https://github.com/kmjbyrne/python-easy-oidc.git"
```

## Pin A Version

```bash
uv pip install git+https://github.com/kmjbyrne/python-easy-oidc.git@v0.1.0
```

The FastAPI extra pulls in `fastapi` as a dependency. The core package depends
only on:

- [Authlib](https://authlib.org/) -- OAuth2 client flows
- [joserfc](https://jose.authlib.org/) -- JWT/JWKS validation
- [httpx](https://www.python-httpx.org/) -- async HTTP

## Requirements

- Python 3.12+
