"""Verifying Supabase access tokens.

The session API needs to know who is playing. Taking that from the request body
would let anyone write results under someone else's account, so the identity
comes from a signed token the client cannot forge.

Verification is local, against the project's JWT secret, rather than a call to
Supabase's /auth/v1/user on every request. A guess endpoint runs several times a
minute per player; adding a network round trip to each one would roughly double
its latency for no extra safety, since the signature already proves the token
came from Supabase.

Anonymous play stays supported: no Authorization header means no user, which is
allowed. An Authorization header that is present but bad is rejected outright --
falling back to anonymous there would hide real bugs and make a broken login
look like a working one.
"""

from __future__ import annotations

import jwt

# Supabase stamps every user token with this audience.
AUDIENCE = "authenticated"

# Supabase signs with HS256. Pinning the algorithm list is what stops the
# classic JWT attack: a forged token declaring "alg": "none", or declaring HS256
# against a server that would otherwise accept an asymmetric key, is refused
# before the signature is even considered.
ALGORITHMS = ["HS256"]


class AuthError(Exception):
    """The caller supplied a token that cannot be trusted."""


def bearer_token(headers):
    """Pull the token out of an Authorization header. None when absent."""
    header = headers.get("Authorization") or headers.get("authorization")
    if not header:
        return None

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must be 'Bearer <token>'")

    return token.strip()


def verify_token(token, secret):
    """Return the token's claims, or raise AuthError."""
    if not secret:
        raise AuthError("token verification is not configured")

    try:
        return jwt.decode(
            token,
            secret,
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
            options={"require": ["exp", "sub"]},
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


def user_id_from_headers(headers, secret):
    """The verified user id, or None for anonymous play.

    Raises AuthError when a token is supplied but unusable, so a broken client
    gets a 401 rather than being silently downgraded to anonymous.
    """
    token = bearer_token(headers)
    if token is None:
        return None

    claims = verify_token(token, secret)

    subject = claims.get("sub")
    if not subject:
        raise AuthError("token carries no subject")

    return subject
