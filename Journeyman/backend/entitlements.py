"""What someone has bought, and whether it is still theirs.

Split out of quota.py now rather than later. The quota *consumes* an
entitlement decision; it does not own the concept, and the payment work about
to land here would have made quota.py a module about two things.

## No provider anywhere in this file

Grant and revoke take a source string and a reference. Stripe fills those in
from a webhook, an operator fills them in by hand, and neither is visible from
here. That is what makes swapping or adding a payment provider a change in one
place.

## Revoked, not deleted

A refund six months later must not erase the fact that somebody paid. Same
reasoning as game_results.voided: the moment you want the history is the moment
you least expected to need it, and by then a delete has already happened.

## On not caching this

is_unlimited runs on every metered start, so a signed-in free player now costs
two queries instead of one. That is deliberate for the moment. The obvious fix
is a short TTL cache like the puzzle's, and the reason not to reach for it yet
is that this decision is about money in the direction that matters: a cache
delays a *revocation*, so a refunded player keeps what they paid back for until
it expires. One query is a fine price for that until measurement says otherwise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# The one product. A constant rather than a literal scattered through call
# sites, because the day there are two of these is the day the literals are
# wrong somewhere.
LIFETIME = "journeyman_lifetime"


class Entitlements(ABC):
    """Whether a caller has bought their way out of the quota."""

    @abstractmethod
    def is_unlimited(self, user_id) -> bool: ...


class FreeTierOnly(Entitlements):
    """Nobody has bought anything.

    The default until a payment provider is wired up, and still the right
    answer for a deployment with no database.
    """

    def is_unlimited(self, user_id) -> bool:
        return False


class InMemoryEntitlements(Entitlements):
    """For tests and local runs. Grants are lost when the process ends."""

    def __init__(self, granted=()):
        self._granted = set(granted)

    def is_unlimited(self, user_id) -> bool:
        return user_id in self._granted

    def grant(self, user_id, product=LIFETIME, source="manual", reference=None):
        self._granted.add(user_id)

    def revoke(self, user_id, product=LIFETIME, reason=None) -> bool:
        if user_id in self._granted:
            self._granted.discard(user_id)
            return True
        return False


class PostgresEntitlements(Entitlements):
    """Reads and writes the entitlements table. See migration 0013."""

    def __init__(self, client, product=LIFETIME):
        self._client = client
        self._product = product

    def is_unlimited(self, user_id) -> bool:
        if not user_id:
            # An anonymous caller has nothing to check an entitlement against.
            # Returning False here rather than querying keeps the caller from
            # having to know that.
            return False
        response = self._client.rpc(
            "has_entitlement",
            {"p_user_id": str(user_id), "p_product": self._product},
        ).execute()
        return bool(response.data)

    def grant(self, user_id, product=None, source="manual", reference=None) -> None:
        """Idempotent: granting twice is one row, and clears any revocation."""
        self._client.rpc(
            "grant_entitlement",
            {
                "p_user_id": str(user_id),
                "p_product": product or self._product,
                "p_source": source,
                "p_source_reference": reference,
            },
        ).execute()

    def revoke(self, user_id, product=None, reason=None) -> bool:
        """Returns whether anything changed.

        False means it was already revoked, which is how a duplicate refund
        webhook is told apart from the first one without a second read.
        """
        response = self._client.rpc(
            "revoke_entitlement",
            {
                "p_user_id": str(user_id),
                "p_product": product or self._product,
                "p_reason": reason,
            },
        ).execute()
        return bool(response.data)
