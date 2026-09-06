"""Stripe: taking the money, and hearing about it afterwards.

The only file that knows what Stripe is. Everything it decides is expressed in
terms entitlements.py and payment_events.py already understand, so a second
provider is a sibling of this file rather than a change to those.

## The security boundary is the signature, not the redirect

A browser returning from Checkout proves nothing: the success URL is
client-controlled and anyone can visit it. Fulfilment happens on a
signature-verified webhook and nowhere else. This is the Phase 0 lesson in a
more expensive setting -- the client is not a source of truth, least of all
about whether it paid.

## Identity comes from client_reference_id

Not from the customer's email. People pay with a different address than the one
they signed up with, constantly, and an email-keyed entitlement turns that into
a support ticket every time. The checkout session carries our own user id, and
that is the only thing fulfilment reads.

It also means checkout requires a signed-in player. That is a real constraint
following from a real choice: the game allows anonymous play, and an anonymous
purchase would have nothing to attach itself to.

## What we act on

Three events, and deliberately not more:

    checkout.session.completed   somebody paid           -> grant
    charge.refunded              money went back         -> revoke
    charge.dispute.created       a chargeback was opened -> revoke

Everything else is acknowledged and ignored. Stripe sends a great deal, and a
handler that tries to be exhaustive is a handler that breaks when Stripe adds an
event type.

A dispute revokes immediately rather than waiting for the outcome. The money is
already gone at that point, along with a fee, and the alternative is somebody
keeping the product for the weeks a dispute takes to resolve. `grant_entitlement`
is idempotent, so winning the dispute is one call to put it back.
"""

from __future__ import annotations

PROVIDER = "stripe"

# Paid once, kept forever. A one-time purchase rather than a subscription
# removes churn management entirely, and puzzle audiences convert better on it.
CHECKOUT_MODE = "payment"

PAID = "checkout.session.completed"
REFUNDED = "charge.refunded"
DISPUTED = "charge.dispute.created"

HANDLED_EVENTS = frozenset({PAID, REFUNDED, DISPUTED})


class BillingError(Exception):
    """Checkout could not be started, or an event could not be understood."""


class SignatureError(Exception):
    """The payload did not come from Stripe, or did not survive the trip."""


# Why checkout is not being offered. Reported rather than reduced to a boolean,
# because these have different fixes and the boolean sent an operator hunting
# through an error tracker for something a config endpoint could have said.
STRIPE_READY = "ready"
STRIPE_NO_SECRET_KEY = "no_secret_key"
STRIPE_NO_WEBHOOK_SECRET = "no_webhook_secret"
STRIPE_NO_PRICE = "no_price"
STRIPE_PRICE_IS_A_PRODUCT = "price_is_a_product"


def configuration_status(config) -> str:
    """Which of the four states the payment configuration is in.

    All three settings are required and they fail differently. Without the
    secret key there is nothing to create a session with. Without the webhook
    secret a payment is taken and never fulfilled, which is worse than not
    selling. Without a price there is nothing to sell.

    The last case is the one that cost an evening: Stripe has both products and
    prices, the dashboard shows the product id most prominently, and pasting a
    `prod_` where a `price_` belongs produces a 500 at checkout and a perfectly
    healthy-looking config endpoint. It is worth naming rather than discovering.
    """
    if not config.stripe_secret_key:
        return STRIPE_NO_SECRET_KEY
    if not config.stripe_webhook_secret:
        return STRIPE_NO_WEBHOOK_SECRET
    if not config.stripe_price_id:
        return STRIPE_NO_PRICE
    if config.stripe_price_id.startswith("prod_"):
        return STRIPE_PRICE_IS_A_PRODUCT
    return STRIPE_READY


def is_configured(config) -> bool:
    """Whether checkout can be offered at all.

    True only when every setting checkout needs is present and plausible.
    Reporting True on a partial configuration is how a buy button ends up
    leading to a 500 -- which it did, because this used to check two of the
    three.
    """
    return configuration_status(config) == STRIPE_READY


def create_checkout_session(config, user_id, success_url, cancel_url, client=None):
    """A hosted Checkout session for the lifetime unlock.

    Hosted rather than an embedded card form: Stripe holds the card data, which
    keeps this out of PCI scope beyond the simplest self-assessment. There is no
    version of taking card numbers ourselves that is worth it.
    """
    if not user_id:
        # The constraint from the module docstring, enforced rather than
        # documented: there would be nothing to attach the purchase to.
        raise BillingError("sign in before buying, so the purchase has an owner")
    if not is_configured(config):
        raise BillingError("payments are not configured")

    stripe = client or _stripe(config)
    session = stripe.checkout.Session.create(
        mode=CHECKOUT_MODE,
        line_items=[{"price": config.stripe_price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        # The whole of fulfilment's identity story. Set in two places because
        # the session and the resulting charge are read at different times.
        client_reference_id=str(user_id),
        metadata={"user_id": str(user_id)},
        payment_intent_data={"metadata": {"user_id": str(user_id)}},
    )
    return {"id": session.id, "url": session.url}


def verify_event(payload_bytes, signature_header, webhook_secret, client=None):
    """Parse a webhook body, or refuse it.

    Signature first, always. Without this anyone who finds the endpoint can post
    a `checkout.session.completed` and grant themselves the product, which is
    the single most valuable request an attacker could forge against this app.
    """
    if not webhook_secret:
        raise SignatureError("no webhook secret configured")
    if not signature_header:
        raise SignatureError("no signature header")

    stripe = client or _stripe_module()
    try:
        return stripe.Webhook.construct_event(payload_bytes, signature_header, webhook_secret)
    except Exception as exc:
        # Deliberately flattened: the caller returns 400 and says nothing about
        # why, because a precise answer is a way to test signatures cheaply.
        raise SignatureError(str(exc)) from exc


def user_id_from_event(event) -> str | None:
    """Whose purchase this is.

    Reads our own reference rather than anything Stripe owns. `metadata` is the
    fallback because a charge is not a session and does not carry
    client_reference_id -- both are set at checkout for exactly this reason.
    """
    obj = (event.get("data") or {}).get("object") or {}

    reference = obj.get("client_reference_id")
    if reference:
        return reference

    for source in (obj.get("metadata"), (obj.get("payment_intent_data") or {}).get("metadata")):
        if isinstance(source, dict) and source.get("user_id"):
            return source["user_id"]

    return None


def describe(event) -> dict:
    """What this event means, in terms that know nothing about Stripe.

    Returns `action` of "grant", "revoke" or None, so the caller decides what to
    do without a second look at the provider's vocabulary.
    """
    event_type = event.get("type")
    action = None
    if event_type == PAID:
        action = "grant"
    elif event_type in (REFUNDED, DISPUTED):
        action = "revoke"

    return {
        "event_id": event.get("id"),
        "type": event_type,
        "action": action,
        "user_id": user_id_from_event(event),
        "reason": {REFUNDED: "refund", DISPUTED: "chargeback"}.get(event_type),
    }


def _stripe_module():
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise BillingError("the stripe package is not installed") from exc
    return stripe


def _stripe(config):
    stripe = _stripe_module()
    stripe.api_key = config.stripe_secret_key
    return stripe
