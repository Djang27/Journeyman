"""Token verification.

These are the tests that decide whether one player can write results under
another player's account, so the forgery cases matter more than the happy path.
"""

import time

import jwt
import pytest
from auth import (
    AUDIENCE,
    AuthError,
    bearer_token,
    jwks_url_for,
    user_id_from_headers,
    verify_token,
)

SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"
OTHER_SECRET = "a-completely-different-signing-secret-of-similar-size"
USER = "11111111-1111-1111-1111-111111111111"


def make_token(secret=SECRET, sub=USER, audience=AUDIENCE, expires_in=3600, **extra):
    """Mint a token the way Supabase would. `expires_in=None` omits `exp`."""
    claims = {
        "sub": sub,
        "aud": audience,
        "role": "authenticated",
        "iat": int(time.time()),
    }
    if expires_in is not None:
        claims["exp"] = int(time.time()) + expires_in

    claims.update(extra)
    claims = {key: value for key, value in claims.items() if value is not None}
    return jwt.encode(claims, secret, algorithm="HS256")


class TestBearerToken:
    def test_extracts_the_token(self):
        assert bearer_token({"Authorization": "Bearer abc.def.ghi"}) == "abc.def.ghi"

    def test_is_case_insensitive_about_the_scheme(self):
        assert bearer_token({"Authorization": "bearer abc"}) == "abc"

    def test_reads_a_lowercase_header_name(self):
        assert bearer_token({"authorization": "Bearer abc"}) == "abc"

    def test_absent_header_is_not_an_error(self):
        # Anonymous play is allowed, so no header simply means no user.
        assert bearer_token({}) is None

    @pytest.mark.parametrize("header", ["abc.def", "Basic dXNlcjpwYXNz", "Bearer", "Bearer   "])
    def test_a_malformed_header_is_rejected(self, header):
        with pytest.raises(AuthError):
            bearer_token({"Authorization": header})


class TestVerifyToken:
    def test_a_valid_token_yields_its_claims(self):
        claims = verify_token(make_token(), secret=SECRET)
        assert claims["sub"] == USER
        assert claims["aud"] == AUDIENCE

    def test_a_token_signed_with_another_secret_is_rejected(self):
        """The core property: only Supabase can mint a token we accept."""
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(secret=OTHER_SECRET), secret=SECRET)

    def test_an_expired_token_is_rejected(self):
        with pytest.raises(AuthError, match="expired"):
            verify_token(make_token(expires_in=-60), secret=SECRET)

    def test_a_token_for_another_audience_is_rejected(self):
        with pytest.raises(AuthError, match="not issued for this application"):
            verify_token(make_token(audience="some-other-app"), secret=SECRET)

    def test_a_token_without_an_expiry_is_rejected(self):
        # A token that never expires is a permanent key if it ever leaks.
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(expires_in=None), secret=SECRET)

    def test_a_token_without_a_subject_is_rejected(self):
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(sub=None), secret=SECRET)

    def test_an_unsigned_token_is_rejected(self):
        """The classic JWT attack: alg "none", claiming no signature is needed.

        Pinning algorithms=["HS256"] is what refuses this.
        """
        forged = jwt.encode(
            {"sub": USER, "aud": AUDIENCE, "exp": int(time.time()) + 3600},
            key="",
            algorithm="none",
        )
        with pytest.raises(AuthError):
            verify_token(forged, secret=SECRET)

    def test_garbage_is_rejected(self):
        with pytest.raises(AuthError):
            verify_token("not-a-jwt", secret=SECRET)

    def test_an_unconfigured_secret_refuses_every_token(self):
        """Fail closed. A missing secret must never mean 'trust everything'."""
        with pytest.raises(AuthError, match="not configured"):
            verify_token(make_token())

    def test_the_error_message_does_not_explain_the_failure(self):
        """Telling a forger why their token failed helps them fix it."""
        with pytest.raises(AuthError) as caught:
            verify_token(make_token(secret=OTHER_SECRET), secret=SECRET)
        assert "signature" not in str(caught.value).lower()


class TestUserIdFromHeaders:
    def test_returns_the_verified_subject(self):
        headers = {"Authorization": f"Bearer {make_token()}"}
        assert user_id_from_headers(headers, secret=SECRET) == USER

    def test_no_header_means_anonymous(self):
        assert user_id_from_headers({}, secret=SECRET) is None

    def test_a_bad_token_raises_rather_than_falling_back_to_anonymous(self):
        """Silently downgrading would make a broken login look like it worked."""
        headers = {"Authorization": f"Bearer {make_token(secret=OTHER_SECRET)}"}
        with pytest.raises(AuthError):
            user_id_from_headers(headers, secret=SECRET)

    def test_the_subject_comes_from_the_token_not_anywhere_else(self):
        """A forged 'sub' is only usable if it is also correctly signed."""
        attacker = user_id_from_headers(
            {"Authorization": f"Bearer {make_token(sub='victim-user-id')}"}, secret=SECRET
        )
        # Signed with the real secret, so this is legitimate -- the point is that
        # the value is read from verified claims, never from the request body.
        assert attacker == "victim-user-id"

        forged = make_token(sub="victim-user-id", secret=OTHER_SECRET)
        with pytest.raises(AuthError):
            user_id_from_headers({"Authorization": f"Bearer {forged}"}, secret=SECRET)


# --------------------------------------------------------------------------
# Asymmetric verification -- what hosted Supabase projects actually issue.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def es256_keys():
    """A real P-256 key pair, matching the ECC key Supabase now signs with."""
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


@pytest.fixture
def jwks_server(es256_keys):
    """Serve a JWKS document over HTTP, the way Supabase does.

    A local socket rather than a mock, so PyJWKClient's real fetching, parsing
    and key-matching all run. It is our own process, not a third party.
    """
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    _, public_key = es256_keys
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(public_key))
    jwk.update({"kid": KID, "use": "sig", "alg": "ES256"})
    document = json.dumps({"keys": [jwk]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    import auth

    auth._jwks_clients.clear()  # no key cache carried between tests
    yield f"http://127.0.0.1:{server.server_address[1]}/auth/v1/.well-known/jwks.json"

    server.shutdown()
    auth._jwks_clients.clear()


KID = "bbfcfdbf-f442-48a4-b2f7-7d9b171ce529"


def make_es256_token(private_key, sub=USER, audience=AUDIENCE, expires_in=3600, kid=KID):
    claims = {
        "sub": sub,
        "aud": audience,
        "role": "authenticated",
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": kid})


class TestJwksUrl:
    def test_derives_from_the_project_url(self):
        assert jwks_url_for("https://abc.supabase.co") == (
            "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
        )

    def test_tolerates_a_trailing_slash(self):
        assert jwks_url_for("https://abc.supabase.co/").endswith("/auth/v1/.well-known/jwks.json")

    def test_is_empty_when_unconfigured(self):
        assert jwks_url_for("") == ""


class TestAsymmetricVerification:
    def test_a_valid_es256_token_is_accepted(self, es256_keys, jwks_server):
        private_key, _ = es256_keys
        claims = verify_token(make_es256_token(private_key), jwks_url=jwks_server)
        assert claims["sub"] == USER

    def test_a_token_signed_by_another_key_is_rejected(self, jwks_server):
        from cryptography.hazmat.primitives.asymmetric import ec

        attacker_key = ec.generate_private_key(ec.SECP256R1())
        with pytest.raises(AuthError):
            verify_token(make_es256_token(attacker_key), jwks_url=jwks_server)

    def test_an_expired_es256_token_is_rejected(self, es256_keys, jwks_server):
        private_key, _ = es256_keys
        with pytest.raises(AuthError, match="expired"):
            verify_token(make_es256_token(private_key, expires_in=-60), jwks_url=jwks_server)

    def test_an_unknown_key_id_is_rejected(self, es256_keys, jwks_server):
        private_key, _ = es256_keys
        token = make_es256_token(private_key, kid="a-key-that-is-not-published")
        with pytest.raises(AuthError):
            verify_token(token, jwks_url=jwks_server)

    def test_an_unreachable_jwks_endpoint_is_distinguished_from_a_bad_token(self, es256_keys):
        """A server problem must not be reported as the caller's forgery."""
        private_key, _ = es256_keys
        token = make_es256_token(private_key)
        with pytest.raises(AuthError, match="could not reach"):
            verify_token(token, jwks_url="http://127.0.0.1:9/nope.json")


class TestNoAlgorithmDowngrade:
    """The reason the scheme is chosen by configuration, not by the token.

    A project's legacy HS256 secret stays visible in its dashboard after
    rotation to asymmetric keys. If both schemes were accepted at once, anyone
    holding that old secret could forge a token for any user.
    """

    def test_an_hs256_token_is_refused_when_jwks_is_configured(self, jwks_server):
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(secret=SECRET), jwks_url=jwks_server)

    def test_the_legacy_secret_is_ignored_when_jwks_is_configured(self, jwks_server):
        """Even passing both, the shared secret buys an attacker nothing."""
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(secret=SECRET), jwks_url=jwks_server, secret=SECRET)

    def test_hs256_still_works_when_only_a_secret_is_configured(self):
        """The local `supabase start` stack, which still signs with HS256."""
        assert verify_token(make_token(), secret=SECRET)["sub"] == USER

    def test_an_es256_token_is_refused_when_only_a_secret_is_configured(self, es256_keys):
        private_key, _ = es256_keys
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_es256_token(private_key), secret=SECRET)
