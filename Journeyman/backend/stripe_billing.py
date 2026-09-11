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


# Which set of keys is in use. Not a secret: the prefix is the first eight
# characters of a key, Stripe's own publishable key carries the same marker in
# public, and knowing a deployment is in test mode grants nobody anything.
MODE_LIVE = "live"
MODE_TEST = "test"
MODE_UNKNOWN = "unknown"


def mode(config) -> str:
    """Live keys or sandbox keys.

    Worth reporting because every other signal is identical across the two.
    `configuration_status` returns `ready` for a perfectly healthy sandbox, so
    an operator who has just switched to live has no way to confirm the switch
    actually took -- and the failure it hides is the expensive direction: a
    launched product quietly taking play money.

    Read from the secret key alone. The price and webhook secret do not carry a
    mode marker, so a mismatched set shows as live here and fails at checkout;
    `live_configuration_is_consistent` is the check for that.
    """
    key = config.stripe_secret_key or ""
    if key.startswith(("sk_live_", "rk_live_")):
        return MODE_LIVE
    if key.startswith(("sk_test_", "rk_test_")):
        return MODE_TEST
    return MODE_UNKNOWN


def is_configured(config) -> bool:
    """Whether checkout can be offered at all.

    True only when every setting checkout needs is present and plausible.
    Reporting True on a partial configuration is how a buy button ends up
    leading to a 500 -- which it did, because this used to check two of the
    three.
    """
    return configuration_status(config) == STRIPE_READY


def verify_configuration(config, webhook_url=None, client=None):
    """Ask Stripe whether this configuration would actually take a payment.

    Everything else about billing is checked without leaving the process, which
    is why a sandbox and a live deployment look identical from outside: the key
    prefix is a string, the price id is a string, and `ready` means "three
    strings are present and shaped right". None of that notices a live key
    pointed at a test price, which fails only when a real buyer presses the
    button.

    So this one call goes to Stripe. It is the check that would also have caught
    a `prod_` pasted where a `price_` belonged, a price left inactive, a
    recurring price on a one-time product, and a price whose tax behaviour is
    unset -- the last of which breaks checkout the moment automatic tax is on.

    Returns findings rather than raising: an operator wants the whole list, not
    the first problem. `ok` is True only when nothing was found.
    """
    problems = []
    details = {
        "mode": mode(config),
        "automatic_tax": bool(getattr(config, "stripe_automatic_tax", False)),
    }

    status = configuration_status(config)
    if status != STRIPE_READY:
        return {"ok": False, "problems": [f"configuration is {status}"], "details": details}

    stripe = client or _stripe(config)
    live = details["mode"] == MODE_LIVE

    try:
        price = stripe.Price.retrieve(config.stripe_price_id)
    except Exception as exc:  # noqa: BLE001 -- any failure here is a finding
        problems.append(f"the price could not be read with this key: {exc}")
        return {"ok": False, "problems": problems, "details": details}

    def field(name, default=None):
        if isinstance(price, dict):
            return price.get(name, default)
        return getattr(price, name, default)

    details["price"] = {
        "amount": field("unit_amount"),
        "currency": field("currency"),
        "type": field("type"),
        "active": field("active"),
        "livemode": field("livemode"),
        "tax_behavior": field("tax_behavior"),
    }

    if field("livemode") is not live:
        # The mismatch this function exists for. A live key and a test price is
        # a checkout that 500s for every real buyer and nobody else.
        problems.append(
            "the key and the price are from different modes -- "
            f"key is {details['mode']}, price is {'live' if field('livemode') else 'test'}"
        )
    if field("active") is False:
        problems.append("the price is archived, so checkout cannot use it")
    if field("type") not in (None, "one_time"):
        problems.append(
            f"the price is {field('type')}, but this is sold once, not as a subscription"
        )
    if details["automatic_tax"] and field("tax_behavior") in (None, "unspecified"):
        # Set at creation and never changeable. Worth naming precisely, because
        # the fix is a new price rather than an edit.
        problems.append(
            "automatic tax is on but the price has no tax behaviour, which fails every "
            "checkout -- tax behaviour cannot be edited, so this needs a new price"
        )

    if webhook_url:
        try:
            endpoints = stripe.WebhookEndpoint.list(limit=100)
            listed = endpoints["data"] if isinstance(endpoints, dict) else endpoints.data
        except Exception as exc:  # noqa: BLE001
            problems.append(f"the webhook endpoints could not be listed: {exc}")
            listed = None
        if listed is not None:
            details["webhooks"] = _webhook_findings(listed, webhook_url, live, problems)

    return {"ok": not problems, "problems": problems, "details": details}


def _webhook_findings(endpoints, webhook_url, live, problems):
    """Whether a webhook for this deployment exists in the right mode.

    The signing secret cannot be checked from here -- Stripe does not hand it
    back -- so a matching endpoint is necessary and not sufficient. What this
    does catch is the common half-switch: a live key with only the sandbox
    webhook still configured, where every payment succeeds and nothing is ever
    fulfilled. That is the worst failure in the system, because the money moves
    and the buyer gets nothing.
    """

    def get(ep, name, default=None):
        if isinstance(ep, dict):
            return ep.get(name, default)
        return getattr(ep, name, default)

    matching = [
        ep
        for ep in endpoints
        if (get(ep, "url") or "").rstrip("/") == webhook_url.rstrip("/")
        and bool(get(ep, "livemode")) is live
        and get(ep, "status") != "disabled"
    ]
    if not matching:
        problems.append(
            f"no enabled {'live' if live else 'test'} webhook points at {webhook_url}, "
            "so payments would be taken and never fulfilled"
        )
        return []

    found = []
    for ep in matching:
        enabled = set(get(ep, "enabled_events") or [])
        missing = sorted(HANDLED_EVENTS - enabled) if "*" not in enabled else []
        if missing:
            problems.append(f"the webhook does not send {', '.join(missing)}")
        found.append({"url": get(ep, "url"), "events": sorted(enabled), "missing": missing})
    return found


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
    params = dict(
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
    if getattr(config, "stripe_automatic_tax", False):
        # Tax is owed where the buyer is, not where we are, and the buyer's
        # location is a thing only they can tell us. Checkout asks for an
        # address when automatic tax is on; requiring it is explicit about
        # why the extra field appeared.
        params["automatic_tax"] = {"enabled": True}
        params["billing_address_collection"] = "required"
    session = stripe.checkout.Session.create(**params)
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
