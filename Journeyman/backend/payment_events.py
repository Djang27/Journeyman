"""Every payment event we were told about, exactly once.

Providers redeliver, and a redelivery is routine rather than exceptional: a
timeout on our side, a deploy mid-request, an operator replaying an event by
hand. Stripe retries for up to three days. So a webhook handler that is not
idempotent will eventually grant the same purchase twice, or apply the same
refund twice, and it will do it in production rather than in a test.

The only reliable answer to "have I already applied this?" is the provider's own
event id. Nothing we generate on receipt can tell two identical deliveries
apart.

## Record first, then act

`seen` records the event and says whether it is new, in one statement. The
handler acts only when it is new, and calls `complete` when it is done. An event
that is recorded but never completed stays visible to
`unprocessed` -- which is what makes a handler that threw findable, instead of
being discovered by a customer email weeks later.

This ordering is deliberate and is the opposite of the tempting one. Acting
first and recording afterwards loses the record if the process dies in between,
and the redelivery then fulfils a second time. Recording first can at worst
leave an event marked seen but unapplied, which is recoverable because it is
*visible*.

## Provider-agnostic

`provider` is a column and nothing here knows what Stripe is. The payload is
stored verbatim so a handler that parsed it wrongly can be fixed and the event
replayed, rather than the event being lost because our code was wrong.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecordedEvent:
    event_id: str
    type: str
    payload: dict = field(default_factory=dict)
    error: str | None = None


class PaymentEventStore(ABC):
    @abstractmethod
    def seen(self, provider, event_id, event_type, payload=None) -> bool:
        """Record the event. Returns True the first time only."""

    @abstractmethod
    def complete(self, provider, event_id, error=None) -> None:
        """Mark it finished, or record why it was not."""

    @abstractmethod
    def unprocessed(self, provider, limit=100) -> list:
        """Events that arrived and never completed."""


class InMemoryPaymentEventStore(PaymentEventStore):
    """For tests and local runs. Not usable in production: each serverless
    invocation gets its own dict, so every delivery would look like the first.
    """

    def __init__(self):
        self._events = {}

    def seen(self, provider, event_id, event_type, payload=None) -> bool:
        key = (provider, event_id)
        if key in self._events:
            return False
        self._events[key] = {
            "type": event_type,
            "payload": payload or {},
            "processed": False,
            "error": None,
        }
        return True

    def complete(self, provider, event_id, error=None) -> None:
        row = self._events.get((provider, event_id))
        if row is None:
            return
        row["processed"] = error is None
        row["error"] = error

    def unprocessed(self, provider, limit=100) -> list:
        return [
            RecordedEvent(
                event_id=event_id,
                type=row["type"],
                payload=row["payload"],
                error=row["error"],
            )
            for (stored_provider, event_id), row in self._events.items()
            if stored_provider == provider and not row["processed"]
        ][:limit]


class PostgresPaymentEventStore(PaymentEventStore):
    """Records in Postgres, atomically. See migration 0014."""

    def __init__(self, client):
        self._client = client

    def seen(self, provider, event_id, event_type, payload=None) -> bool:
        response = self._client.rpc(
            "record_payment_event",
            {
                "p_provider": provider,
                "p_event_id": event_id,
                "p_type": event_type,
                "p_payload": payload,
            },
        ).execute()
        return bool(response.data)

    def complete(self, provider, event_id, error=None) -> None:
        self._client.rpc(
            "complete_payment_event",
            {"p_provider": provider, "p_event_id": event_id, "p_error": error},
        ).execute()

    def unprocessed(self, provider, limit=100) -> list:
        response = self._client.rpc(
            "unprocessed_payment_events",
            {"p_provider": provider, "p_limit": limit},
        ).execute()
        return [
            RecordedEvent(
                event_id=row["event_id"],
                type=row["type"],
                payload=row.get("payload") or {},
                error=row.get("error"),
            )
            for row in (response.data or [])
        ]


def apply_once(store, provider, event_id, event_type, handler, payload=None) -> str:
    """Run `handler` for this event at most once, ever.

    Returns what happened, as a string the caller can log and a webhook can put
    in its response body: "applied", "duplicate", or "failed".

    A duplicate is a success from the provider's point of view -- it must be
    acknowledged with a 2xx, or the provider keeps redelivering an event that
    has already been handled. Only a genuine failure should be reported as one,
    so that a redelivery is a retry rather than noise.
    """
    if not store.seen(provider, event_id, event_type, payload):
        return "duplicate"

    try:
        handler()
    except Exception as exc:
        # Left unprocessed on purpose, with the reason attached, so the
        # reconciliation job can find it. Swallowing this would turn a fixable
        # problem into a customer email.
        store.complete(provider, event_id, error=f"{type(exc).__name__}: {exc}")
        raise

    store.complete(provider, event_id)
    return "applied"
