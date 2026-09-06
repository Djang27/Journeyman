"""The free-tier quota.

The rules that matter are the ones with money behind them: the daily is never
charged for, signing out does not reset an allowance, and the sixth game is
refused even when two requests arrive together.
"""

import pytest
from quota import (
    FREE_GAMES_PER_DAY,
    Entitlements,
    FreeTierOnly,
    InMemoryQuotaStore,
    QuotaDecision,
    consume,
    is_metered,
    quota_subject,
    remaining,
)

TODAY = "2026-09-05"


@pytest.fixture
def store():
    return InMemoryQuotaStore()


@pytest.fixture
def free():
    return FreeTierOnly()


class Paid(Entitlements):
    def is_unlimited(self, user_id):
        return True


class TestWhatIsCharged:
    def test_the_daily_is_never_charged(self, store, free):
        # The funnel. A wall here would be the most expensive possible place
        # to put one.
        for _ in range(50):
            decision = consume(store, free, "daily", "u1", TODAY)
            assert decision.allowed
        assert store.used("user:u1", TODAY) == 0

    def test_unlimited_is_charged(self, store, free):
        assert is_metered("unlimited")
        consume(store, free, "unlimited", "u1", TODAY)
        assert store.used("user:u1", TODAY) == 1

    def test_an_unknown_mode_is_not_charged(self, store, free):
        # Fail open on classification: a mode nobody has decided about should
        # not silently start costing players games.
        assert consume(store, free, "practice", "u1", TODAY).unmetered


class TestTheAllowance:
    def test_five_games_are_allowed(self, store, free):
        for _ in range(FREE_GAMES_PER_DAY):
            assert consume(store, free, "unlimited", "u1", TODAY).allowed

    def test_the_sixth_is_refused(self, store, free):
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, free, "unlimited", "u1", TODAY)
        decision = consume(store, free, "unlimited", "u1", TODAY)
        assert not decision.allowed
        assert decision.exhausted

    def test_remaining_counts_down(self, store, free):
        seen = [consume(store, free, "unlimited", "u1", TODAY).remaining for _ in range(5)]
        assert seen == [4, 3, 2, 1, 0]

    def test_remaining_never_goes_negative(self, store, free):
        for _ in range(10):
            decision = consume(store, free, "unlimited", "u1", TODAY)
        assert decision.remaining == 0

    def test_a_new_day_is_a_new_allowance(self, store, free):
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, free, "unlimited", "u1", TODAY)
        assert consume(store, free, "unlimited", "u1", "2026-09-06").allowed


class TestIdentity:
    def test_two_players_do_not_share_an_allowance(self, store, free):
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, free, "unlimited", "u1", TODAY)
        assert consume(store, free, "unlimited", "u2", TODAY).allowed

    def test_signing_out_does_not_reset_the_allowance(self, store, free):
        # The reason anonymous play is metered at all. If it were not, the cap
        # would be one click away from being decorative.
        headers = {"X-Forwarded-For": "203.0.113.7"}
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, free, "unlimited", None, TODAY, headers=headers)
        assert not consume(store, free, "unlimited", None, TODAY, headers=headers).allowed

    def test_a_signed_in_player_is_keyed_on_their_account_not_their_address(self):
        # Otherwise an office network would share one allowance between
        # everyone signed in on it.
        headers = {"X-Forwarded-For": "203.0.113.7"}
        assert quota_subject("u1", headers) == "user:u1"
        assert quota_subject(None, headers).startswith("ip:")

    def test_two_addresses_are_two_allowances(self, store, free):
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, free, "unlimited", None, TODAY, headers={"X-Forwarded-For": "1.1.1.1"})
        assert consume(
            store, free, "unlimited", None, TODAY, headers={"X-Forwarded-For": "2.2.2.2"}
        ).allowed


class TestEntitlements:
    def test_a_paid_player_is_not_metered(self, store):
        for _ in range(50):
            decision = consume(store, Paid(), "unlimited", "u1", TODAY)
            assert decision.allowed
            assert decision.unmetered
        # And costs no query at all, which is the point of checking first.
        assert store.used("user:u1", TODAY) == 0

    def test_the_default_entitlement_is_free_tier(self):
        assert FreeTierOnly().is_unlimited("anyone") is False

    def test_an_anonymous_caller_is_never_treated_as_paid(self, store):
        # is_unlimited is only consulted for a verified user id. An anonymous
        # caller has nothing to check an entitlement against.
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, Paid(), "unlimited", None, TODAY)
        assert not consume(store, Paid(), "unlimited", None, TODAY).allowed


class TestReadingWithoutSpending:
    def test_remaining_does_not_consume(self, store, free):
        for _ in range(3):
            remaining(store, free, "u1", TODAY)
        assert store.used("user:u1", TODAY) == 0

    def test_remaining_reflects_what_was_spent(self, store, free):
        for _ in range(2):
            consume(store, free, "unlimited", "u1", TODAY)
        assert remaining(store, free, "u1", TODAY).remaining == 3

    def test_remaining_reports_unmetered_for_a_paid_player(self, store):
        assert remaining(store, Paid(), "u1", TODAY).unmetered

    def test_remaining_is_not_allowed_once_exhausted(self, store, free):
        for _ in range(FREE_GAMES_PER_DAY):
            consume(store, free, "unlimited", "u1", TODAY)
        assert not remaining(store, free, "u1", TODAY).allowed


class TestTheDecision:
    def test_unmetered_is_never_exhausted(self):
        # The UI branches on this. An unmetered caller showing "0 left" would
        # be exactly wrong for the people who paid.
        decision = QuotaDecision(allowed=True, used=0, remaining=0, unmetered=True)
        assert not decision.exhausted

    def test_a_refused_free_player_is_exhausted(self):
        assert QuotaDecision(allowed=False, used=6, remaining=0).exhausted
