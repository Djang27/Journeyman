"""Verifying Supabase access tokens.

The session API needs to know who is playing. Taking that from the request body
would let anyone write results under someone else's account, so the identity
comes from a signed token the client cannot forge.

Two signing schemes are in play, because Supabase has moved from one to the
other:

* **Asymmetric (ES256/RS256)** -- what hosted projects issue now. Tokens are
  verified against the project's public keys, fetched once from its JWKS
  endpoint and cached. Nothing secret is needed to verify them.
* **HS256 with a shared secret** -- the legacy scheme, still what the local
  `supabase start` stack uses.

Which one applies is decided by configuration, never by the token: if a JWKS URL
is available, HS256 is refused outright. That matters. A project's legacy shared
secret stays visible in its dashboard after rotation, so accepting HS256
alongside asymmetric keys would let anyone holding that old secret forge tokens
for any user -- an algorithm-confusion downgrade. Choosing the scheme from
config closes it.

Verification is local either way. A guess endpoint runs several times a minute
per player; calling /auth/v1/user on each would roughly double its latency for
no extra safety, since the signature already proves Supabase minted the token.

Anonymous play stays supported: no Authorization header means no user. An
Authorization header that is present but bad is rejected outright -- falling
back to anonymous there would hide real bugs and make a broken login look like
a working one.
"""

from __future__ import annotations

import threading

import jwt
from jwt import PyJWKClient

# Supabase stamps every user token with this audience.
AUDIENCE = "authenticated"

# Pinning an explicit allowlist per scheme is what refuses the classic JWT
# attacks: a token declaring "alg": "none", or one declaring HS256 so that a
# public key gets used as an HMAC secret.
ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]
SYMMETRIC_ALGORITHMS = ["HS256"]

_REQUIRED_CLAIMS = {"require": ["exp", "sub"]}

# PyJWKClient caches keys by id, so this costs one fetch per process rather than
# one per request. Cached per URL because preview and production are different
# projects with different keys.
_jwks_clients: dict[str, PyJWKClient] = {}
_jwks_lock = threading.Lock()


class AuthError(Exception):
    """The caller supplied a token that cannot be trusted."""


def jwks_url_for(supabase_url):
    """The public keys for a Supabase project. Empty when unconfigured."""
    if not supabase_url:
        return ""
    return f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _jwks_client(url):
    with _jwks_lock:
        client = _jwks_clients.get(url)
        if client is None:
            client = PyJWKClient(url, cache_keys=True, lifespan=3600)
            _jwks_clients[url] = client
        return client


def bearer_token(headers):
    """Pull the token out of an Authorization header. None when absent."""
    header = headers.get("Authorization") or headers.get("authorization")
    if not header:
        return None

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must be 'Bearer <token>'")

    return token.strip()


def verify_token(token, jwks_url="", secret=""):
    """Return the token's claims, or raise AuthError.

    `jwks_url` wins when both are supplied -- see the module docstring on why
    accepting both schemes at once would be a downgrade path.
    """
    if jwks_url:
        return _verify_asymmetric(token, jwks_url)
    if secret:
        return _verify_symmetric(token, secret)

    # Fail closed. A missing configuration must never mean "trust everyone".
    raise AuthError("token verification is not configured")


def _verify_asymmetric(token, jwks_url):
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    except jwt.exceptions.PyJWKClientConnectionError as exc:
        # Our problem, not the caller's -- checked before PyJWKClientError,
        # which it subclasses. Reporting an outage as a forged token would send
        # whoever is debugging it looking in entirely the wrong place.
        raise AuthError("could not reach the token verification service") from exc
    except jwt.exceptions.PyJWKClientError as exc:
        # No key matching the token's `kid`: the token was not signed by this
        # project.
        raise AuthError("invalid token") from exc

    return _decode(token, signing_key.key, ASYMMETRIC_ALGORITHMS)


def _verify_symmetric(token, secret):
    return _decode(token, secret, SYMMETRIC_ALGORITHMS)


def _decode(token, key, algorithms):
    try:
        return jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=AUDIENCE,
            options=_REQUIRED_CLAIMS,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("token was not issued for this application") from exc
    except jwt.InvalidTokenError as exc:
        # Covers a bad signature, a missing claim, and an unexpected algorithm.
        # The message is deliberately vague: telling a caller *why* their forged
        # token failed helps them forge a better one.
        raise AuthError("invalid token") from exc


def user_id_from_headers(headers, jwks_url="", secret=""):
    """The verified user id, or None for anonymous play.

    Raises AuthError when a token is supplied but unusable, so a broken client
    gets a 401 rather than being silently downgraded to anonymous.
    """
    token = bearer_token(headers)
    if token is None:
        return None

    claims = verify_token(token, jwks_url=jwks_url, secret=secret)

    subject = claims.get("sub")
    if not subject:
        raise AuthError("token carries no subject")

    return subject
