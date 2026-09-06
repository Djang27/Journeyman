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

    def __init__(self, secret="sk_test_x", webhook="whsec_test", price="price_x", public=""):
        self.stripe_secret_key = secret
        self.stripe_webhook_secret = webhook
        self.stripe_price_id = price
        self.public_url = public


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
