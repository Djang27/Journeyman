"""Entitlements: what someone bought, and whether it is still theirs.

The rules with money behind them are the idempotency ones. A payment provider
delivers the same webhook more than once as a matter of routine, so granting
twice must be one grant, and revoking twice must be distinguishable from
revoking once -- that return value is how a duplicate refund is told apart from
a first one without a second read.
"""

import pytest
from entitlements import (
    LIFETIME,
    Entitlements,
    FreeTierOnly,
    InMemoryEntitlements,
)


class TestTheContract:
    def test_free_tier_grants_nobody_anything(self):
        assert FreeTierOnly().is_unlimited("anyone") is False

    def test_free_tier_is_an_entitlements(self):
        # app.py builds one of these when there is no database, so it has to
        # satisfy the same interface the Postgres one does.
        assert isinstance(FreeTierOnly(), Entitlements)

    def test_the_product_is_named_once(self):
        # A literal scattered through call sites is wrong somewhere the day
        # there are two products.
        assert LIFETIME == "journeyman_lifetime"


class TestInMemory:
    def test_nobody_is_entitled_by_default(self):
        assert InMemoryEntitlements().is_unlimited("u1") is False

    def test_a_grant_takes_effect(self):
        e = InMemoryEntitlements()
        e.grant("u1")
        assert e.is_unlimited("u1")

    def test_a_grant_is_not_shared(self):
        e = InMemoryEntitlements()
        e.grant("u1")
        assert not e.is_unlimited("u2")

    def test_revoke_reports_whether_it_changed_anything(self):
        e = InMemoryEntitlements()
        e.grant("u1")
        assert e.revoke("u1") is True
        assert e.revoke("u1") is False

    def test_revoking_removes_access(self):
        e = InMemoryEntitlements()
        e.grant("u1")
        e.revoke("u1")
        assert not e.is_unlimited("u1")


class TestAnonymousCallers:
    """An anonymous caller has nothing to check an entitlement against."""

    @pytest.mark.parametrize("user_id", [None, ""])
    def test_postgres_does_not_query_for_an_anonymous_caller(self, user_id):
        # Returning False without a round trip keeps callers from having to
        # know that entitlements are account-shaped.
        from entitlements import PostgresEntitlements

        class ExplodingClient:
            def rpc(self, *args, **kwargs):
                raise AssertionError("should not have queried for an anonymous caller")

        assert PostgresEntitlements(ExplodingClient()).is_unlimited(user_id) is False


class TestTheQuotaUsesIt:
    """The seam actually being consumed, rather than merely existing."""

    def test_an_entitled_player_is_not_metered(self):
        from quota import FREE_GAMES_PER_DAY, InMemoryQuotaStore
        from quota import consume as consume_quota

        store = InMemoryQuotaStore()
        e = InMemoryEntitlements(granted={"u1"})

        for _ in range(FREE_GAMES_PER_DAY + 5):
            decision = consume_quota(store, e, "unlimited", "u1", "2026-09-05")
            assert decision.allowed
            assert decision.unmetered

        # And costs no query at all, which is why the check comes first.
        assert store.used("user:u1", "2026-09-05") == 0

    def test_revoking_puts_a_player_back_on_the_free_tier(self):
        # The refund path, end to end through the quota. What a player keeps
        # after a refund is nothing, starting immediately.
        from quota import FREE_GAMES_PER_DAY, InMemoryQuotaStore
        from quota import consume as consume_quota

        store = InMemoryQuotaStore()
        e = InMemoryEntitlements(granted={"u1"})

        consume_quota(store, e, "unlimited", "u1", "2026-09-05")
        e.revoke("u1")

        for _ in range(FREE_GAMES_PER_DAY):
            assert consume_quota(store, e, "unlimited", "u1", "2026-09-05").allowed
        assert not consume_quota(store, e, "unlimited", "u1", "2026-09-05").allowed
