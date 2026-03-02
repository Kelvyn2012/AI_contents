"""
Tests for webhook idempotency, signature verification, and upgrade flow.
"""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Payment, Subscription, WebhookEventLog
from apps.billing.services import (
    process_charge_success_webhook,
    verify_webhook_signature,
)


TEST_SECRET = "test_secret_key_xyz"


def make_user(username="billuser"):
    return User.objects.create_user(username=username, email=f"{username}@test.com", password="pw")


def make_payment(user, reference="ref_001", plan="pro", amount_kobo=500_000):
    return Payment.objects.create(
        user=user,
        reference=reference,
        amount_kobo=amount_kobo,
        currency="NGN",
        plan=plan,
        status="pending",
    )


def build_charge_success_payload(reference, amount=500_000, event_id="evt_001", status="success"):
    return {
        "id": event_id,
        "event": "charge.success",
        "data": {
            "id": 12345,
            "status": status,
            "reference": reference,
            "amount": amount,
            "currency": "NGN",
            "customer": {"customer_code": "CUS_xyz"},
        },
    }


# ─── Signature verification ──────────────────────────────────────────────────

class WebhookSignatureTests(TestCase):
    @override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
    def test_valid_signature_passes(self):
        payload = b'{"event": "charge.success"}'
        sig = hmac.new(TEST_SECRET.encode(), payload, hashlib.sha512).hexdigest()
        self.assertTrue(verify_webhook_signature(payload, sig))

    @override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
    def test_invalid_signature_fails(self):
        payload = b'{"event": "charge.success"}'
        self.assertFalse(verify_webhook_signature(payload, "wrong_sig"))

    @override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
    def test_tampered_payload_fails(self):
        payload = b'{"event": "charge.success"}'
        sig = hmac.new(TEST_SECRET.encode(), payload, hashlib.sha512).hexdigest()
        tampered = b'{"event": "charge.success", "extra": "injected"}'
        self.assertFalse(verify_webhook_signature(tampered, sig))


# ─── Webhook idempotency ─────────────────────────────────────────────────────

class WebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.user = make_user()

    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PLANS={
            "free": {"name": "Free", "words_per_month": 5000, "max_projects": 3, "price_kobo": 0},
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_first_webhook_activates_subscription(self):
        make_payment(self.user, reference="ref_001")
        payload = build_charge_success_payload("ref_001", event_id="evt_001")
        result = process_charge_success_webhook(payload)
        self.assertEqual(result, "processed")
        self.assertTrue(Subscription.objects.filter(user=self.user, status="active").exists())
        payment = Payment.objects.get(reference="ref_001")
        self.assertEqual(payment.status, "success")

    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PLANS={
            "free": {"name": "Free", "words_per_month": 5000, "max_projects": 3, "price_kobo": 0},
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_duplicate_webhook_is_skipped(self):
        make_payment(self.user, reference="ref_002")
        payload = build_charge_success_payload("ref_002", event_id="evt_002")
        # First call
        result1 = process_charge_success_webhook(payload)
        # Second call (replay)
        result2 = process_charge_success_webhook(payload)
        self.assertEqual(result1, "processed")
        self.assertEqual(result2, "duplicate")
        # Only one subscription
        self.assertEqual(Subscription.objects.filter(user=self.user, status="active").count(), 1)

    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PLANS={
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_amount_mismatch_skips_activation(self):
        make_payment(self.user, reference="ref_003")
        payload = build_charge_success_payload("ref_003", amount=100, event_id="evt_003")
        result = process_charge_success_webhook(payload)
        self.assertEqual(result, "skipped")
        self.assertFalse(Subscription.objects.filter(user=self.user, status="active").exists())
        log = WebhookEventLog.objects.get(event_key="charge.success:evt_003")
        self.assertEqual(log.status, "error")

    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PLANS={
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_unknown_reference_skips_activation(self):
        payload = build_charge_success_payload("ref_nonexistent", event_id="evt_004")
        result = process_charge_success_webhook(payload)
        self.assertEqual(result, "skipped")

    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PLANS={
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_previous_subscription_cancelled_on_upgrade(self):
        old_sub = Subscription.objects.create(
            user=self.user,
            plan="pro",
            status="active",
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )
        make_payment(self.user, reference="ref_005")
        payload = build_charge_success_payload("ref_005", event_id="evt_005")
        process_charge_success_webhook(payload)
        old_sub.refresh_from_db()
        self.assertEqual(old_sub.status, "cancelled")
        self.assertEqual(Subscription.objects.filter(user=self.user, status="active").count(), 1)


# ─── Webhook HTTP endpoint ───────────────────────────────────────────────────

class WebhookEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("billing:webhook")

    @override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
    def test_invalid_signature_returns_400(self):
        resp = self.client.post(
            self.url,
            data=json.dumps({"event": "charge.success"}),
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="bad_sig",
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PLANS={
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_valid_webhook_returns_200(self):
        user = make_user("webhookuser")
        make_payment(user, reference="ref_http_001")
        payload = build_charge_success_payload("ref_http_001", event_id="evt_http_001")
        body = json.dumps(payload).encode()
        sig = hmac.new(TEST_SECRET.encode(), body, hashlib.sha512).hexdigest()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=sig,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Subscription.objects.filter(user=user, status="active").exists())


# ─── Checkout init flow ──────────────────────────────────────────────────────

class CheckoutFlowTests(TestCase):
    def setUp(self):
        self.user = make_user("checkoutuser")
        self.client = Client()
        self.client.force_login(self.user)

    @patch("apps.billing.services.httpx.post")
    @override_settings(
        PAYSTACK_SECRET_KEY=TEST_SECRET,
        PAYSTACK_BASE_URL="https://api.paystack.co",
        PLANS={
            "pro": {"name": "Pro", "words_per_month": 60000, "max_projects": 20, "price_kobo": 500_000},
        },
    )
    def test_checkout_creates_payment_and_redirects(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "authorization_url": "https://checkout.paystack.com/abc123",
                "access_code": "acc_123",
                "reference": "ref_checkout",
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        resp = self.client.post(
            reverse("billing:checkout"),
            data={"plan": "pro"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("paystack.com", resp["Location"])
        self.assertTrue(Payment.objects.filter(user=self.user, plan="pro").exists())
