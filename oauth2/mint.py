"""Mint a dev JWT from the command line.

Usage:
    python -m oauth2.mint --issuer http://localhost:8000 --audience my-api
    python -m oauth2.mint --subject admin --roles admin,viewer --permissions orders.read
"""

import argparse
import json
import sys

from oauth2.dev import mint_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a development JWT")
    parser.add_argument("--issuer", default="http://localhost:8000")
    parser.add_argument("--audience", default="dev")
    parser.add_argument("--subject", default="dev-user")
    parser.add_argument("--email", default="dev@localhost")
    parser.add_argument("--name", default="Dev User")
    parser.add_argument("--roles", default="", help="Comma-separated roles")
    parser.add_argument("--permissions", default="", help="Comma-separated permissions")
    parser.add_argument("--lifetime", type=int, default=3600)
    parser.add_argument("--token-only", action="store_true", help="Print only the access token")
    args = parser.parse_args()

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    permissions = [p.strip() for p in args.permissions.split(",") if p.strip()]

    result = mint_token(
        issuer=args.issuer,
        audience=args.audience,
        subject=args.subject,
        email=args.email,
        name=args.name,
        roles=roles,
        permissions=permissions,
        lifetime=args.lifetime,
    )

    if args.token_only:
        print(result["access_token"])
    else:
        json.dump(result, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
