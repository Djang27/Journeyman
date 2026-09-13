"""The shared client builder, and the retry the scheduled jobs use.

The retry exists because the daily reconciliation failed on a single gateway
timeout: it runs at a quiet hour and its first query met a database that had
gone idle. The tests that matter most here are the ones about what is *not*
retried -- a retry that swallows real errors is worse than none.
"""

import httpx
import pytest
import supabase_client as SC
from postgrest.exceptions import APIError


class FakeConfig:
    supabase_url = "https://example.supabase.co"
    supabase_service_key = "not-a-real-key"


def api_error(code):
    return APIError({"message": "x", "code": code, "hint": None, "details": None})


class TestBuild:
    def test_the_bound_reaches_the_http_client(self):
        client = SC.build(FakeConfig(), timeout=7)
        assert client.postgrest.session.timeout.read == 7

    def test_the_default_is_the_app_bound(self):
        read = SC.build(FakeConfig()).postgrest.session.timeout.read
        assert read == SC.DATABASE_TIMEOUT_SECONDS

    def test_the_policies_are_ordered(self):
        # The limiter fails open so waits least; jobs race no function limit so
        # wait most.
        assert SC.LIMITER_TIMEOUT_SECONDS < SC.DATABASE_TIMEOUT_SECONDS < SC.BATCH_TIMEOUT_SECONDS


class TestIsTransient:
    @pytest.mark.parametrize("code", [504, "504", 503, 502])
    def test_gateway_failures_are_transient(self, code):
        assert SC.is_transient(api_error(code))

    @pytest.mark.parametrize("code", ["400", "401", "403", "404", "23505", "PGRST116", None])
    def test_real_errors_are_not(self, code):
        # Retrying these hides a genuine fault, and around a write can do it
        # twice. 23505 is a unique violation; PGRST116 is "no rows".
        assert not SC.is_transient(api_error(code))

    def test_a_dropped_connection_is_transient(self):
        assert SC.is_transient(httpx.ConnectError("refused"))

    def test_a_read_timeout_is_transient(self):
        assert SC.is_transient(httpx.ReadTimeout("slow"))

    def test_an_ordinary_bug_is_not(self):
        assert not SC.is_transient(ValueError("a real bug"))


class TestWithRetries:
    def test_it_recovers_from_a_cold_start(self):
        # The reconciliation failure: one gateway timeout, then a warm database.
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise api_error(504)
            return "ok"

        slept = []
        assert SC.with_retries(flaky, sleep=slept.append) == "ok"
        assert len(calls) == 2
        assert slept == [2.0]

    def test_a_real_error_is_raised_at_once(self):
        calls = []

        def broken():
            calls.append(1)
            raise api_error("23505")

        with pytest.raises(APIError):
            SC.with_retries(broken, sleep=lambda _s: None)
        assert len(calls) == 1, "a non-transient failure must not be retried"

    def test_an_ordinary_exception_is_raised_at_once(self):
        calls = []

        def buggy():
            calls.append(1)
            raise KeyError("missing")

        with pytest.raises(KeyError):
            SC.with_retries(buggy, sleep=lambda _s: None)
        assert len(calls) == 1

    def test_it_gives_up_after_the_last_attempt(self):
        calls = []

        def down():
            calls.append(1)
            raise api_error(504)

        with pytest.raises(APIError):
            SC.with_retries(down, attempts=3, sleep=lambda _s: None)
        assert len(calls) == 3

    def test_the_pause_grows(self):
        def down():
            raise httpx.ConnectError("refused")

        slept = []
        with pytest.raises(httpx.ConnectError):
            SC.with_retries(down, attempts=3, base_delay=2.0, sleep=slept.append)
        assert slept == [2.0, 4.0]

    def test_success_is_returned_untouched(self):
        assert SC.with_retries(lambda: 42, sleep=lambda _s: None) == 42

    def test_zero_attempts_still_tries_once(self):
        assert SC.with_retries(lambda: "ran", attempts=0, sleep=lambda _s: None) == "ran"
