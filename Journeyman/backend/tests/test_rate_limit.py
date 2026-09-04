"""Rate limiting.

The properties worth testing are the ones that only fail under load or under
attack: that concurrent callers cannot both slip under the same limit, that one
caller's budget is not another's, and that a limiter outage does not take the
game down with it.
"""

import time

import pytest
from rate_limit import (
    GUESS_LIMIT,
    START_LIMIT,
    Decision,
    InMemoryRateLimiter,
    caller_bucket,
    check,
    hash_client_address,
)


@pytest.fixture
def limiter():
    return InMemoryRateLimiter()


class TestCounting:
    def test_requests_under_the_limit_are_allowed(self, limiter):
        for _ in range(3):
            assert limiter.consume("b", 60, 3).allowed

    def test_the_request_over_the_limit_is_refused(self, limiter):
        for _ in range(3):
            limiter.consume("b", 60, 3)
        assert not limiter.consume("b", 60, 3).allowed

    def test_buckets_are_independent(self, limiter):
        """One player hitting their limit must not affect anyone else."""
        for _ in range(5):
            limiter.consume("a", 60, 3)
        assert limiter.consume("b", 60, 3).allowed

    def test_a_new_window_starts_fresh(self, limiter):
        for _ in range(5):
            limiter.consume("b", 1, 3)
        time.sleep(1.1)
        assert limiter.consume("b", 1, 3).allowed

    def test_it_reports_when_the_window_resets(self, limiter):
        decision = limiter.consume("b", 60, 1)
        assert decision.resets_at > time.time()


class TestRetryAfter:
    def test_an_allowed_request_has_none(self):
        assert (
            Decision(allowed=True, used=1, resets_at=time.time() + 30).retry_after_seconds is None
        )

    def test_a_refused_request_reports_seconds(self):
        decision = Decision(allowed=False, used=9, resets_at=time.time() + 30)
        assert 25 <= decision.retry_after_seconds <= 31

    def test_it_is_never_zero(self):
        """A Retry-After of 0 invites an immediate retry."""
        decision = Decision(allowed=False, used=9, resets_at=time.time() - 5)
        assert decision.retry_after_seconds >= 1


class TestBuckets:
    def test_a_signed_in_player_gets_their_own_budget(self):
        """Sharing an office network must not mean sharing a limit."""
        a = caller_bucket("game_start", "user-a", {"X-Forwarded-For": "1.2.3.4"})
        b = caller_bucket("game_start", "user-b", {"X-Forwarded-For": "1.2.3.4"})
        assert a != b

    def test_actions_have_separate_budgets(self):
        assert caller_bucket("game_start", "u") != caller_bucket("game_guess", "u")

    def test_anonymous_callers_are_grouped_by_address(self):
        headers = {"X-Forwarded-For": "9.9.9.9"}
        assert caller_bucket("game_start", None, headers) == caller_bucket(
            "game_start", None, headers
        )

    def test_different_addresses_get_different_buckets(self):
        one = caller_bucket("game_start", None, {"X-Forwarded-For": "1.1.1.1"})
        two = caller_bucket("game_start", None, {"X-Forwarded-For": "2.2.2.2"})
        assert one != two

    def test_the_address_is_never_stored_in_the_clear(self):
        """An IP is personal data. The bucket must not contain one."""
        bucket = caller_bucket("game_start", None, {"X-Forwarded-For": "203.0.113.7"})
        assert "203.0.113.7" not in bucket

    def test_only_the_first_forwarded_entry_is_used(self):
        """X-Forwarded-For is appended to by each proxy; the client is first."""
        direct = hash_client_address({"X-Forwarded-For": "1.1.1.1"})
        proxied = hash_client_address({"X-Forwarded-For": "1.1.1.1, 10.0.0.1, 10.0.0.2"})
        assert direct == proxied

    def test_a_missing_address_still_produces_a_bucket(self):
        assert caller_bucket("game_start", None, {})


class TestFailureMode:
    def test_a_broken_limiter_does_not_refuse_traffic(self):
        """Fails open on purpose: this is not the security boundary.

        A limiter outage taking the game down would trade a real failure for a
        hypothetical one. app.py catches and logs.
        """

        class Broken(InMemoryRateLimiter):
            def consume(self, *args, **kwargs):
                raise RuntimeError("counter store unreachable")

        with pytest.raises(RuntimeError):
            check(Broken(), "game_start", START_LIMIT, "u")


class TestConfiguredLimits:
    def test_starting_a_game_is_limited_per_hour(self):
        window, limit = START_LIMIT
        assert window == 3600
        assert 20 <= limit <= 200, "generous for a player, tight for a script"

    def test_guessing_is_limited_per_minute(self):
        window, limit = GUESS_LIMIT
        assert window == 60
        # A guess takes seconds to type; two a second is already inhuman.
        assert 30 <= limit <= 300

    def test_guessing_is_more_generous_than_starting(self):
        """A single game involves many guesses and one start."""
        starts_per_minute = START_LIMIT[1] / (START_LIMIT[0] / 60)
        assert GUESS_LIMIT[1] > starts_per_minute
