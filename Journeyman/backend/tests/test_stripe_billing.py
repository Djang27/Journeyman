"""Stripe: the parts that decide whether money becomes access.

No test here reaches Stripe. Signatures are computed locally with the real
algorithm, which is the same thing Stripe's library verifies, so these exercise
the real verification path against payloads we control.
"""

import hashlib
import hmac
import json
import time

import pytest
import stripe_billing


class Config:
    """The four settings billing reads."""

    def __init__(
        self,
        secret="sk_test_x",
        webhook="whsec_test",
        price="price_x",
        public="",
        automatic_tax=False,
    ):
        self.stripe_secret_key = secret
        self.stripe_webhook_secret = webhook
        self.stripe_price_id = price
        self.public_url = public
        self.stripe_automatic_tax = automatic_tax


def signed(payload: bytes, secret: str, timestamp=None) -> str:
    """A genuine Stripe-Signature header, computed the way Stripe computes it."""
    timestamp = timestamp or int(time.time())
    signature = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def event_bytes(event_type, **obj):
    return json.dumps({"id": "evt_1", "type": event_type, "data": {"object": obj}}).encode()


class TestConfiguration:
    """`available` has to mean what it says.

    It used to check two of the three settings checkout needs, so a deployment
    with a missing or malformed price reported itself ready and then returned a
    500 when somebody pressed the button. That happened.
    """

    def test_a_complete_configuration_is_ready(self):
        assert stripe_billing.is_configured(Config()) is True
        assert stripe_billing.configuration_status(Config()) == stripe_billing.STRIPE_READY

    def test_the_secret_key_is_required(self):
        assert stripe_billing.is_configured(Config(secret="")) is False
        assert (
            stripe_billing.configuration_status(Config(secret=""))
            == stripe_billing.STRIPE_NO_SECRET_KEY
        )

    def test_the_webhook_secret_is_required(self):
        # Without it a payment is taken and never fulfilled, which is worse
        # than not selling at all.
        assert stripe_billing.is_configured(Config(webhook="")) is False
        assert (
            stripe_billing.configuration_status(Config(webhook=""))
            == stripe_billing.STRIPE_NO_WEBHOOK_SECRET
        )

    def test_the_price_is_required(self):
        # The gap that shipped: this used to report ready with no price at all.
        assert stripe_billing.is_configured(Config(price="")) is False
        assert (
            stripe_billing.configuration_status(Config(price="")) == stripe_billing.STRIPE_NO_PRICE
        )

    def test_a_product_id_pasted_as_a_price_is_caught(self):
        # The actual mistake. Stripe shows the product id most prominently, and
        # a prod_ where a price_ belongs is a 500 at checkout and a config
        # endpoint reporting everything fine.
        config = Config(price="prod_VCyQuhukWbr55N")
        assert stripe_billing.is_configured(config) is False
        assert (
            stripe_billing.configuration_status(config) == stripe_billing.STRIPE_PRICE_IS_A_PRODUCT
        )

    def test_the_statuses_are_distinct(self):
        # Read by a person deciding what to fix, so two collapsing is silent.
        assert (
            len(
                {
                    stripe_billing.STRIPE_READY,
                    stripe_billing.STRIPE_NO_SECRET_KEY,
                    stripe_billing.STRIPE_NO_WEBHOOK_SECRET,
                    stripe_billing.STRIPE_NO_PRICE,
                    stripe_billing.STRIPE_PRICE_IS_A_PRODUCT,
                }
            )
            == 5
        )


class TestSignatureVerification:
    """The security boundary. Forging this is the most valuable request an
    attacker could make against the app: it grants the product for free."""

    def test_a_genuine_signature_is_accepted(self):
        payload = event_bytes(stripe_billing.PAID)
        event = stripe_billing.verify_event(payload, signed(payload, "whsec_test"), "whsec_test")
        assert event["type"] == stripe_billing.PAID

    def test_an_unsigned_payload_is_refused(self):
        payload = event_bytes(stripe_billing.PAID)
        with pytest.raises(stripe_billing.SignatureError):
            stripe_billing.verify_event(payload, None, "whsec_test")

    def test_a_forged_signature_is_refused(self):
        payload = event_bytes(stripe_billing.PAID)
        with pytest.raises(stripe_billing.SignatureError):
            stripe_billing.verify_event(payload, "t=1,v1=deadbeef", "whsec_test")

    def test_a_signature_from_the_wrong_secret_is_refused(self):
        payload = event_bytes(stripe_billing.PAID)
        with pytest.raises(stripe_billing.SignatureError):
            stripe_billing.verify_event(payload, signed(payload, "whsec_other"), "whsec_test")

    def test_a_tampered_payload_is_refused(self):
        # Signed genuinely, then edited. This is the attack the signature
        # exists for: a real event with the user id swapped.
        payload = event_bytes(stripe_billing.PAID, client_reference_id="victim")
        header = signed(payload, "whsec_test")
        tampered = payload.replace(b"victim", b"attack")
        with pytest.raises(stripe_billing.SignatureError):
            stripe_billing.verify_event(tampered, header, "whsec_test")

    def test_an_old_signature_is_refused(self):
        # Replay protection: Stripe's tolerance window. Without it a captured
        # webhook could be posted back indefinitely.
        payload = event_bytes(stripe_billing.PAID)
        old = signed(payload, "whsec_test", timestamp=int(time.time()) - 3600)
        with pytest.raises(stripe_billing.SignatureError):
            stripe_billing.verify_event(payload, old, "whsec_test")

    def test_no_configured_secret_refuses_everything(self):
        # Closed rather than open, like the admin token.
        payload = event_bytes(stripe_billing.PAID)
        with pytest.raises(stripe_billing.SignatureError):
            stripe_billing.verify_event(payload, signed(payload, "whsec_test"), "")


class TestReadingAnEvent:
    def test_a_payment_grants(self):
        described = stripe_billing.describe(
            {"id": "evt_1", "type": stripe_billing.PAID, "data": {"object": {}}}
        )
        assert described["action"] == "grant"

    @pytest.mark.parametrize(
        "event_type,reason",
        [(stripe_billing.REFUNDED, "refund"), (stripe_billing.DISPUTED, "chargeback")],
    )
    def test_a_refund_or_dispute_revokes(self, event_type, reason):
        described = stripe_billing.describe(
            {"id": "evt_1", "type": event_type, "data": {"object": {}}}
        )
        assert described["action"] == "revoke"
        assert described["reason"] == reason

    def test_everything_else_is_ignored(self):
        # Stripe sends a great deal. A handler that tries to be exhaustive
        # breaks when Stripe adds an event type.
        described = stripe_billing.describe(
            {"id": "evt_1", "type": "invoice.created", "data": {"object": {}}}
        )
        assert described["action"] is None


class TestIdentity:
    """Never email. People pay from a different address than they signed up
    with constantly, and email-keyed entitlements make that a support ticket."""

    def test_the_client_reference_is_preferred(self):
        event = {"data": {"object": {"client_reference_id": "u1", "metadata": {"user_id": "u2"}}}}
        assert stripe_billing.user_id_from_event(event) == "u1"

    def test_metadata_is_the_fallback(self):
        # A charge is not a session and carries no client_reference_id, which
        # is why checkout sets both.
        event = {"data": {"object": {"metadata": {"user_id": "u2"}}}}
        assert stripe_billing.user_id_from_event(event) == "u2"

    def test_an_email_is_never_used_as_identity(self):
        event = {"data": {"object": {"customer_email": "someone@example.com"}}}
        assert stripe_billing.user_id_from_event(event) is None

    def test_a_missing_reference_is_none_rather_than_a_guess(self):
        assert stripe_billing.user_id_from_event({"data": {"object": {}}}) is None


def _capture_session(config):
    """Start a checkout against a fake Stripe and return what it was sent."""
    captured = {}

    class FakeStripe:
        class checkout:
            class Session:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return type("S", (), {"id": "cs_1", "url": "https://stripe/x"})()

    stripe_billing.create_checkout_session(
        config, "u1", "https://x/ok", "https://x/no", client=FakeStripe
    )
    return captured


class TestCheckout:
    def test_an_anonymous_caller_cannot_buy(self):
        # There would be nothing to attach the purchase to.
        with pytest.raises(stripe_billing.BillingError):
            stripe_billing.create_checkout_session(Config(), None, "s", "c")

    def test_unconfigured_payments_cannot_start_checkout(self):
        with pytest.raises(stripe_billing.BillingError):
            stripe_billing.create_checkout_session(Config(webhook=""), "u1", "s", "c")

    def test_the_session_carries_our_user_id_in_both_places(self):
        captured = {}

        class FakeStripe:
            class checkout:
                class Session:
                    @staticmethod
                    def create(**kwargs):
                        captured.update(kwargs)
                        return type("S", (), {"id": "cs_1", "url": "https://stripe/x"})()

        result = stripe_billing.create_checkout_session(
            Config(), "u1", "https://x/ok", "https://x/no", client=FakeStripe
        )

        assert result == {"id": "cs_1", "url": "https://stripe/x"}
        assert captured["client_reference_id"] == "u1"
        assert captured["metadata"]["user_id"] == "u1"
        # The charge needs it too: a refund event is a charge, not a session.
        assert captured["payment_intent_data"]["metadata"]["user_id"] == "u1"
        assert captured["mode"] == "payment"

    def test_tax_is_not_calculated_unless_it_is_switched_on(self):
        # Asking Stripe for automatic tax before Stripe Tax is set up in the
        # dashboard fails the whole session, so the default has to be off. A
        # deployment that has not thought about tax still sells.
        captured = _capture_session(Config())
        assert "automatic_tax" not in captured

    def test_switching_tax_on_asks_stripe_to_calculate_it(self):
        # And collects the address it needs to, since tax is owed where the
        # buyer is. Enabling Stripe Tax in the dashboard alone does nothing --
        # the session has to ask, which is the half that is easy to miss.
        captured = _capture_session(Config(automatic_tax=True))
        assert captured["automatic_tax"] == {"enabled": True}
        assert captured["billing_address_collection"] == "required"


class TestMode:
    """Live and sandbox are indistinguishable from every other signal.

    `configuration_status` returns `ready` for a perfectly healthy sandbox, so
    an operator switching to live had nothing to confirm the switch against.
    """

    def test_live_keys_report_live(self):
        assert stripe_billing.mode(Config(secret="sk_live_abc")) == stripe_billing.MODE_LIVE

    def test_test_keys_report_test(self):
        assert stripe_billing.mode(Config(secret="sk_test_abc")) == stripe_billing.MODE_TEST

    def test_restricted_keys_carry_the_marker_too(self):
        assert stripe_billing.mode(Config(secret="rk_live_abc")) == stripe_billing.MODE_LIVE

    def test_an_unset_key_is_unknown_rather_than_a_guess(self):
        assert stripe_billing.mode(Config(secret="")) == stripe_billing.MODE_UNKNOWN


def fake_stripe(price=None, endpoints=None, price_error=None):
    """A Stripe that answers the two calls verification makes."""

    class FakeStripe:
        class Price:
            @staticmethod
            def retrieve(_price_id):
                if price_error:
                    raise price_error
                return price

        class WebhookEndpoint:
            @staticmethod
            def list(limit=100):
                return {"data": endpoints or []}

    return FakeStripe


def a_price(**overrides):
    base = {
        "unit_amount": 999,
        "currency": "usd",
        "type": "one_time",
        "active": True,
        "livemode": True,
        "tax_behavior": "exclusive",
    }
    base.update(overrides)
    return base


def an_endpoint(**overrides):
    base = {
        "url": "https://x.test/api/billing/webhook",
        "livemode": True,
        "status": "enabled",
        "enabled_events": sorted(stripe_billing.HANDLED_EVENTS),
    }
    base.update(overrides)
    return base


LIVE = dict(secret="sk_live_abc")
HOOK = "https://x.test/api/billing/webhook"


class TestVerifyConfiguration:
    """The checks that need Stripe to answer, not just string shapes."""

    def test_a_good_live_configuration_passes(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(), endpoints=[an_endpoint()]),
        )
        assert report["ok"] is True
        assert report["problems"] == []
        assert report["details"]["mode"] == "live"
        assert report["details"]["price"]["amount"] == 999

    def test_a_live_key_with_a_test_price_is_caught(self):
        # The failure this exists for: it looks ready, and 500s for every real
        # buyer while working perfectly in the dashboard's test view.
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(livemode=False), endpoints=[an_endpoint()]),
        )
        assert report["ok"] is False
        assert any("different modes" in p for p in report["problems"])

    def test_an_archived_price_is_caught(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(active=False), endpoints=[an_endpoint()]),
        )
        assert any("archived" in p for p in report["problems"])

    def test_a_recurring_price_is_caught(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(type="recurring"), endpoints=[an_endpoint()]),
        )
        assert any("sold once" in p for p in report["problems"])

    def test_tax_on_without_a_tax_behaviour_is_caught(self):
        report = stripe_billing.verify_configuration(
            Config(automatic_tax=True, **LIVE),
            webhook_url=HOOK,
            client=fake_stripe(
                price=a_price(tax_behavior="unspecified"), endpoints=[an_endpoint()]
            ),
        )
        assert any("tax behaviour" in p for p in report["problems"])

    def test_tax_behaviour_is_only_required_when_tax_is_on(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(
                price=a_price(tax_behavior="unspecified"), endpoints=[an_endpoint()]
            ),
        )
        assert report["ok"] is True

    def test_only_a_sandbox_webhook_is_caught(self):
        # The worst half-switch there is: payments succeed and nothing is ever
        # fulfilled, because the live endpoint was never created.
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(), endpoints=[an_endpoint(livemode=False)]),
        )
        assert any("never fulfilled" in p for p in report["problems"])

    def test_a_webhook_for_another_deployment_does_not_count(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(
                price=a_price(),
                endpoints=[an_endpoint(url="https://other.test/api/billing/webhook")],
            ),
        )
        assert any("never fulfilled" in p for p in report["problems"])

    def test_a_disabled_webhook_does_not_count(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(), endpoints=[an_endpoint(status="disabled")]),
        )
        assert any("never fulfilled" in p for p in report["problems"])

    def test_a_webhook_missing_an_event_is_named(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(
                price=a_price(),
                endpoints=[an_endpoint(enabled_events=[stripe_billing.PAID])],
            ),
        )
        assert any(stripe_billing.REFUNDED in p for p in report["problems"])

    def test_a_wildcard_subscription_covers_every_event(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price=a_price(), endpoints=[an_endpoint(enabled_events=["*"])]),
        )
        assert report["ok"] is True

    def test_an_unreadable_price_reports_rather_than_raises(self):
        report = stripe_billing.verify_configuration(
            Config(**LIVE),
            webhook_url=HOOK,
            client=fake_stripe(price_error=Exception("No such price: 'price_x'")),
        )
        assert report["ok"] is False
        assert any("No such price" in p for p in report["problems"])

    def test_an_incomplete_configuration_says_so_without_calling_stripe(self):
        report = stripe_billing.verify_configuration(Config(secret=""), webhook_url=HOOK)
        assert report["ok"] is False
        assert report["problems"] == ["configuration is no_secret_key"]
