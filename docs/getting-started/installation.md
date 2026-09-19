# Installation

## Basic

Install from the repository. The package is not yet on PyPI.

```bash
uv pip install git+https://github.com/kmjbyrne/python-oidcutils.git
```

## With FastAPI Support

```bash
uv pip install "oidcutils[fastapi] @ git+https://github.com/kmjbyrne/python-oidcutils.git"
```

## Pin A Version

```bash
uv pip install git+https://github.com/kmjbyrne/python-oidcutils.git@v0.1.0
```

The FastAPI extra pulls in `fastapi` as a dependency. The core package depends
only on:

- [Authlib](https://authlib.org/) -- OAuth2 client flows
- [joserfc](https://jose.authlib.org/) -- JWT/JWKS validation
- [httpx](https://www.python-httpx.org/) -- async HTTP

## Requirements

- Python 3.12+
