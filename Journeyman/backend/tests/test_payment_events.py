"""The payment event log, which is what makes a webhook safe to receive twice.

Providers redeliver as a matter of routine. A handler that is not idempotent
grants the same purchase twice, and it does it in production rather than in a
test, because a redelivery needs a timeout or a deploy to provoke it.
"""

import pytest
from payment_events import InMemoryPaymentEventStore, apply_once


@pytest.fixture
def store():
    return InMemoryPaymentEventStore()


@pytest.fixture
def fulfilments():
    return []


def handler_for(fulfilments, value="granted"):
    def handler():
        fulfilments.append(value)

    return handler


class TestSeeingAnEventOnce:
    def test_the_first_delivery_is_new(self, store):
        assert store.seen("stripe", "evt_1", "checkout.session.completed") is True

    def test_a_redelivery_is_not(self, store):
        store.seen("stripe", "evt_1", "checkout.session.completed")
        assert store.seen("stripe", "evt_1", "checkout.session.completed") is False

    def test_providers_do_not_share_an_id_space(self, store):
        # Two providers can both call an event 'evt_1'. Treating those as the
        # same event would silently drop one.
        store.seen("stripe", "evt_1", "a")
        assert store.seen("paddle", "evt_1", "b") is True


class TestApplyingOnce:
    def test_the_handler_runs_the_first_time(self, store, fulfilments):
        result = apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments))
        assert result == "applied"
        assert fulfilments == ["granted"]

    def test_the_handler_does_not_run_again(self, store, fulfilments):
        for _ in range(10):
            apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments))
        # The whole point: ten deliveries, one purchase.
        assert fulfilments == ["granted"]

    def test_a_duplicate_reports_itself_as_such(self, store, fulfilments):
        apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments))
        assert apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments)) == "duplicate"

    def test_different_events_both_apply(self, store, fulfilments):
        apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments, "one"))
        apply_once(store, "stripe", "evt_2", "paid", handler_for(fulfilments, "two"))
        assert fulfilments == ["one", "two"]


class TestWhenTheHandlerFails:
    def test_the_failure_is_raised(self, store):
        def explode():
            raise RuntimeError("no such user")

        with pytest.raises(RuntimeError):
            apply_once(store, "stripe", "evt_1", "paid", explode)

    def test_a_failed_event_stays_visible(self, store):
        # Otherwise a handler that threw is discovered by a customer email
        # rather than by the reconciliation job.
        def explode():
            raise RuntimeError("no such user")

        with pytest.raises(RuntimeError):
            apply_once(store, "stripe", "evt_1", "paid", explode)

        pending = store.unprocessed("stripe")
        assert [event.event_id for event in pending] == ["evt_1"]
        assert "no such user" in pending[0].error

    def test_a_failed_event_is_not_retried_by_a_redelivery(self, store, fulfilments):
        # A deliberate limitation, worth pinning so it is a decision rather than
        # a surprise: the event is already recorded, so a provider redelivery
        # sees a duplicate. Recovery is the reconciliation job replaying it from
        # the stored payload, not the provider trying again.
        def explode():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            apply_once(store, "stripe", "evt_1", "paid", explode)

        assert apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments)) == "duplicate"
        assert fulfilments == []

    def test_the_payload_is_kept_so_it_can_be_replayed(self, store):
        def explode():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            apply_once(
                store, "stripe", "evt_1", "paid", explode, payload={"id": "evt_1", "amount": 999}
            )

        assert store.unprocessed("stripe")[0].payload == {"id": "evt_1", "amount": 999}


class TestTrackingWhatIsOutstanding:
    def test_a_completed_event_is_not_outstanding(self, store, fulfilments):
        apply_once(store, "stripe", "evt_1", "paid", handler_for(fulfilments))
        assert store.unprocessed("stripe") == []

    def test_outstanding_is_scoped_to_one_provider(self, store):
        store.seen("stripe", "evt_1", "paid")
        store.seen("paddle", "evt_2", "paid")
        assert [event.event_id for event in store.unprocessed("stripe")] == ["evt_1"]

    def test_the_limit_is_respected(self, store):
        for index in range(10):
            store.seen("stripe", f"evt_{index}", "paid")
        assert len(store.unprocessed("stripe", limit=3)) == 3
