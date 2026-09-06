"""Reconciliation: finding payments that were made and never fulfilled.

The bug this exists for raises nothing. Somebody pays, the webhook never lands,
and every other check reports a healthy game. So the tests here are mostly about
what it must *not* do -- grant for an unpaid session, grant twice, or stay quiet
when something is wrong.
"""

import pytest
from entitlements import InMemoryEntitlements
from payment_events import InMemoryPaymentEventStore
from reconcile_billing import (
    missing_fulfilments,
    repair,
    stalled_events,
)


def session(session_id, payment_status="paid", user_id="u1", metadata=None):
    return {
        "id": session_id,
        "payment_status": payment_status,
        "client_reference_id": user_id,
        "metadata": metadata or {},
    }


@pytest.fixture
def entitlements():
    return InMemoryEntitlements()


@pytest.fixture
def events():
    return InMemoryPaymentEventStore()


class TestFindingUnfulfilledPayments:
    def test_a_paid_session_with_no_entitlement_is_a_problem(self, entitlements, events):
        problems = missing_fulfilments([session("cs_1")], events, entitlements.is_unlimited)
        assert [p["session_id"] for p in problems] == ["cs_1"]
        assert problems[0]["repairable"] is True

    def test_a_fulfilled_payment_is_not_a_problem(self, entitlements, events):
        entitlements.grant("u1")
        assert missing_fulfilments([session("cs_1")], events, entitlements.is_unlimited) == []

    def test_an_unpaid_session_is_never_granted(self, entitlements, events):
        # The distinction that would otherwise hand out the product for free: a
        # session can be complete with payment_status unpaid.
        problems = missing_fulfilments(
            [session("cs_1", payment_status="unpaid")], events, entitlements.is_unlimited
        )
        assert problems == []

    def test_an_abandoned_session_is_never_granted(self, entitlements, events):
        problems = missing_fulfilments(
            [session("cs_1", payment_status="no_payment_required")],
            events,
            entitlements.is_unlimited,
        )
        assert problems == []

    def test_metadata_is_used_when_there_is_no_client_reference(self, entitlements, events):
        problems = missing_fulfilments(
            [session("cs_1", user_id=None, metadata={"user_id": "u2"})],
            events,
            entitlements.is_unlimited,
        )
        assert problems[0]["user_id"] == "u2"

    def test_a_paid_session_with_no_user_is_reported_but_not_repairable(self, entitlements, events):
        # Somebody's money with nothing to attach it to. It must be visible --
        # this is a refund or a support conversation, not something to guess at.
        problems = missing_fulfilments(
            [session("cs_1", user_id=None)], events, entitlements.is_unlimited
        )
        assert problems[0]["repairable"] is False
        assert problems[0]["user_id"] is None


class TestFindingStalledEvents:
    def test_an_applied_event_is_not_stalled(self, events):
        events.seen("stripe", "evt_1", "checkout.session.completed")
        events.complete("stripe", "evt_1")
        assert stalled_events(events) == []

    def test_a_failed_event_is_stalled(self, events):
        events.seen("stripe", "evt_1", "checkout.session.completed", {"client_reference_id": "u1"})
        events.complete("stripe", "evt_1", error="boom")
        stalled = stalled_events(events)
        assert [event["event_id"] for event in stalled] == ["evt_1"]
        assert stalled[0]["error"] == "boom"

    def test_the_user_is_recovered_from_the_stored_payload(self, events):
        # This is why the payload is stored verbatim: the handler can be fixed
        # and the event replayed, rather than the money being lost because our
        # parsing was wrong.
        events.seen("stripe", "evt_1", "checkout.session.completed", {"client_reference_id": "u7"})
        events.complete("stripe", "evt_1", error="boom")
        assert stalled_events(events)[0]["user_id"] == "u7"


class TestRepairing:
    def test_dry_run_changes_nothing(self, entitlements, events):
        # A job that silently grants the first time somebody runs it by hand is
        # a job nobody trusts enough to run.
        problems = missing_fulfilments([session("cs_1")], events, entitlements.is_unlimited)
        repair(problems, entitlements, dry_run=True)
        assert not entitlements.is_unlimited("u1")

    def test_repairing_grants_what_is_owed(self, entitlements, events):
        problems = missing_fulfilments([session("cs_1")], events, entitlements.is_unlimited)
        repair(problems, entitlements, dry_run=False)
        assert entitlements.is_unlimited("u1")

    def test_repairing_twice_is_harmless(self, entitlements, events):
        problems = missing_fulfilments([session("cs_1")], events, entitlements.is_unlimited)
        repair(problems, entitlements, dry_run=False)
        repair(problems, entitlements, dry_run=False)
        assert entitlements.is_unlimited("u1")

    def test_an_unattributable_payment_is_not_repaired(self, entitlements, events):
        problems = missing_fulfilments(
            [session("cs_1", user_id=None)], events, entitlements.is_unlimited
        )
        assert repair(problems, entitlements, dry_run=False) == []

    def test_only_the_unfulfilled_are_touched(self, entitlements, events):
        entitlements.grant("u1")
        problems = missing_fulfilments(
            [session("cs_1", user_id="u1"), session("cs_2", user_id="u2")],
            events,
            entitlements.is_unlimited,
        )
        repaired = repair(problems, entitlements, dry_run=False)
        assert [p["user_id"] for p in repaired] == ["u2"]


class TestTheWholeStory:
    def test_a_lost_webhook_is_found_and_fixed(self, entitlements, events):
        """The scenario, end to end.

        Somebody paid. Stripe says so. No webhook ever arrived, so there is no
        event and no entitlement, and nothing anywhere threw.
        """
        paid = [session("cs_lost", user_id="u_paid")]

        assert not entitlements.is_unlimited("u_paid")

        problems = missing_fulfilments(paid, events, entitlements.is_unlimited)
        assert len(problems) == 1

        repair(problems, entitlements, dry_run=False)
        assert entitlements.is_unlimited("u_paid")

        # And a second run finds nothing left to do.
        assert missing_fulfilments(paid, events, entitlements.is_unlimited) == []
