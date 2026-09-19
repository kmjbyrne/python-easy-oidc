"""A development identity provider, runnable on its own.

    python -m oidcutils.idp --port 9000 --audience my-api

Serves the three things an app needs to validate a token it did not mint:
discovery at ``/.well-known/openid-configuration``, the public key at
``/.well-known/jwks.json``, and ``POST /dev/token`` to mint one.

Built on :mod:`http.server` rather than a framework, so it runs with nothing
installed beyond this package. An app then points ``OIDC_ISSUER`` at it and
fetches keys over an ordinary socket, which is the arrangement production will
use. Nothing has to be mounted, injected or transported.

The alternative is :func:`oidcutils.contrib.fastapi.create_dev_idp`, which returns
a mountable app for a single-process dev loop. Prefer this one where a second
process is acceptable: an issuer that is genuinely somewhere else is one fewer
thing behaving differently from production.

It signs with an ephemeral key generated at import and mints a token for
anybody who asks, without a password, a client secret or a redirect. Run it on
a developer's machine and nowhere else.
"""

import argparse
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from oidcutils.dev import KEY_ENV, discovery_document, mint_token, public_jwks, use_signing_key

logger = logging.getLogger(__name__)

DISCOVERY_PATH = "/.well-known/openid-configuration"
JWKS_PATH = "/.well-known/jwks.json"
TOKEN_PATH = "/dev/token"  # noqa: S105 - a URL path, not a credential

# A minted token carries only these. Anything else in the body is refused
# rather than passed through, so a typo is an error instead of a claim nobody
# meant to grant.
MINTABLE = frozenset(
    {
        "subject",
        "email",
        "name",
        "roles",
        "permissions",
        "lifetime",
        "extra_claims",
    }
)


def _handler(issuer: str, audience: str) -> type[BaseHTTPRequestHandler]:
    """Build a handler class closing over the issuer this server answers as."""

    class Handler(BaseHTTPRequestHandler):
        """Answers the three endpoints, and 404 for everything else."""

        # Kept out of the protocol version default so keep-alive works and a
        # client fetching discovery then JWKS does not pay for a second
        # connection.
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - the base class names it
            """Serve discovery and the public key."""
            if self.path == DISCOVERY_PATH:
                self._json(discovery_document(issuer))
            elif self.path == JWKS_PATH:
                self._json(public_jwks())
            else:
                self._json({"error": "not_found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802 - the base class names it
            """Mint a token from the claims the body asks for."""
            if self.path != TOKEN_PATH:
                self._json({"error": "not_found"}, status=404)
                return

            try:
                body = self._body()
            except ValueError:
                self._json({"error": "invalid_request"}, status=400)
                return

            unknown = set(body) - MINTABLE
            if unknown:
                self._json({"error": "invalid_request", "unknown": sorted(unknown)}, status=400)
                return

            self._json(mint_token(issuer=issuer, audience=audience, **body))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Log through the package logger rather than onto stderr."""
            logger.info("%s %s", self.address_string(), format % args)

        def _body(self) -> dict[str, Any]:
            """Return the request body as a dict, empty where there is none.

            :raises ValueError: if a body is present and is not a JSON object.
            """
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            parsed = json.loads(self.rfile.read(length))
            if not isinstance(parsed, dict):
                raise ValueError("body must be a JSON object")
            return parsed

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            """Write ``payload`` as JSON with a length, so keep-alive holds."""
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


def serve(
    host: str = "127.0.0.1",
    port: int = 9000,
    audience: str = "dev",
    issuer: str | None = None,
    signing_key: str | None = None,
) -> ThreadingHTTPServer:
    """Return a server ready to answer as ``issuer``, not yet serving.

    ``issuer`` defaults to the address the server binds to, which is what an
    app should set ``OIDC_ISSUER`` to. Pass it explicitly when the server sits
    behind something that rewrites the host, since the discovery document it
    publishes has to name an address clients can reach.

    ``signing_key`` is a key file or the key's own text; ``None`` reads
    ``OIDC_DEV_SIGNING_KEY`` and otherwise signs with an ephemeral key. Supply
    one where tokens have to survive a restart or match a committed fixture.

    Returned rather than served, so a caller can read ``server_address`` before
    traffic starts. That is how a test binds port 0 and learns which port it
    was given.
    """
    use_signing_key(signing_key)
    bound = ThreadingHTTPServer((host, port), _handler(issuer or "", audience))
    resolved = issuer or f"http://{host}:{bound.server_address[1]}"
    bound.RequestHandlerClass = _handler(resolved, audience)
    return bound


def main() -> None:
    """Run the server until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--audience", default="dev")
    parser.add_argument(
        "--issuer",
        default=None,
        help="What to publish as the issuer. Defaults to the bound address.",
    )
    parser.add_argument(
        "--signing-key",
        default=None,
        help=(
            "A JWK or PEM file, or the key itself. Defaults to "
            f"${KEY_ENV}, then to an ephemeral key."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = serve(host=args.host, port=args.port, audience=args.audience, issuer=args.issuer)
    host, port = server.server_address[0], server.server_address[1]
    published = args.issuer or f"http://{host}:{port}"

    logger.info("development IdP on http://%s:%s", host, port)
    logger.info("set OIDC_ISSUER=%s", published)
    logger.info("mint a token: curl -XPOST %s%s", published, TOKEN_PATH)
    if not (args.signing_key or os.environ.get(KEY_ENV)):
        logger.info("signing with an ephemeral key: tokens will not survive a restart")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("stopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
