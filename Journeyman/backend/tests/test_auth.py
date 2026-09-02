"""Token verification.

These are the tests that decide whether one player can write results under
another player's account, so the forgery cases matter more than the happy path.
"""

import time

import jwt
import pytest
from auth import AUDIENCE, AuthError, bearer_token, user_id_from_headers, verify_token

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
        claims = verify_token(make_token(), SECRET)
        assert claims["sub"] == USER
        assert claims["aud"] == AUDIENCE

    def test_a_token_signed_with_another_secret_is_rejected(self):
        """The core property: only Supabase can mint a token we accept."""
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(secret=OTHER_SECRET), SECRET)

    def test_an_expired_token_is_rejected(self):
        with pytest.raises(AuthError, match="expired"):
            verify_token(make_token(expires_in=-60), SECRET)

    def test_a_token_for_another_audience_is_rejected(self):
        with pytest.raises(AuthError, match="not issued for this application"):
            verify_token(make_token(audience="some-other-app"), SECRET)

    def test_a_token_without_an_expiry_is_rejected(self):
        # A token that never expires is a permanent key if it ever leaks.
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(expires_in=None), SECRET)

    def test_a_token_without_a_subject_is_rejected(self):
        with pytest.raises(AuthError, match="invalid token"):
            verify_token(make_token(sub=None), SECRET)

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
            verify_token(forged, SECRET)

    def test_garbage_is_rejected(self):
        with pytest.raises(AuthError):
            verify_token("not-a-jwt", SECRET)

    def test_an_unconfigured_secret_refuses_every_token(self):
        """Fail closed. A missing secret must never mean 'trust everything'."""
        with pytest.raises(AuthError, match="not configured"):
            verify_token(make_token(), "")

    def test_the_error_message_does_not_explain_the_failure(self):
        """Telling a forger why their token failed helps them fix it."""
        with pytest.raises(AuthError) as caught:
            verify_token(make_token(secret=OTHER_SECRET), SECRET)
        assert "signature" not in str(caught.value).lower()


class TestUserIdFromHeaders:
    def test_returns_the_verified_subject(self):
        headers = {"Authorization": f"Bearer {make_token()}"}
        assert user_id_from_headers(headers, SECRET) == USER

    def test_no_header_means_anonymous(self):
        assert user_id_from_headers({}, SECRET) is None

    def test_a_bad_token_raises_rather_than_falling_back_to_anonymous(self):
        """Silently downgrading would make a broken login look like it worked."""
        headers = {"Authorization": f"Bearer {make_token(secret=OTHER_SECRET)}"}
        with pytest.raises(AuthError):
            user_id_from_headers(headers, SECRET)

    def test_the_subject_comes_from_the_token_not_anywhere_else(self):
        """A forged 'sub' is only usable if it is also correctly signed."""
        attacker = user_id_from_headers(
            {"Authorization": f"Bearer {make_token(sub='victim-user-id')}"}, SECRET
        )
        # Signed with the real secret, so this is legitimate -- the point is that
        # the value is read from verified claims, never from the request body.
        assert attacker == "victim-user-id"

        forged = make_token(sub="victim-user-id", secret=OTHER_SECRET)
        with pytest.raises(AuthError):
            user_id_from_headers({"Authorization": f"Bearer {forged}"}, SECRET)
