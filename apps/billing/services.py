"""
Billing service layer: Paystack checkout init, verify, webhook processing,
subscription state transitions — all via atomic DB transactions.
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import timedelta

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Payment, Subscription, WebhookEventLog

logger = logging.getLogger(__name__)

PAYSTACK_BASE = settings.PAYSTACK_BASE_URL


def _paystack_headers():
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def initialize_checkout(user, plan: str) -> dict:
    """
    Create a pending Payment record and initialize a Paystack transaction.
    Returns {'authorization_url': ..., 'reference': ...}
    """
    plan_config = settings.PLANS.get(plan)
    if not plan_config:
        raise ValueError(f"Unknown plan: {plan}")

    reference = f"aicontent_{user.id}_{uuid.uuid4().hex}"
    amount_kobo = plan_config["price_kobo"]

    with transaction.atomic():
        payment = Payment.objects.create(
            user=user,
            reference=reference,
            amount_kobo=amount_kobo,
            currency="NGN",
            plan=plan,
            status="pending",
        )

    payload = {
        "email": user.email,
        "amount": amount_kobo,
        "reference": reference,
        "currency": "NGN",
        "callback_url": f"{settings.PAYSTACK_BASE_URL}/billing/callback/",
        "metadata": {
            "user_id": user.id,
            "plan": plan,
            "payment_id": payment.id,
        },
    }

    try:
        resp = httpx.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=payload,
            headers=_paystack_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
    except Exception as exc:
        logger.error("Paystack init failed: %s", exc)
        raise RuntimeError("Payment gateway error. Please try again.") from exc

    with transaction.atomic():
        payment.authorization_url = data["authorization_url"]
        payment.paystack_access_code = data.get("access_code", "")
        payment.save(update_fields=["authorization_url", "paystack_access_code", "updated_at"])

    return {"authorization_url": data["authorization_url"], "reference": reference}


def verify_transaction_server_side(reference: str) -> dict:
    """
    Verify a Paystack transaction. Returns Paystack data dict.
    NOTE: Used for callback UX only — webhook is the source of truth.
    """
    try:
        resp = httpx.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers=_paystack_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Paystack verify failed for %s: %s", reference, exc)
        raise RuntimeError("Could not verify payment.") from exc


def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """Validate Paystack HMAC-SHA512 webhook signature."""
    secret = settings.PAYSTACK_SECRET_KEY.encode()
    expected = hmac.new(secret, payload_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def process_charge_success_webhook(payload: dict) -> str:
    """
    Idempotently process a charge.success webhook event.
    Returns 'processed' | 'duplicate' | 'skipped'.
    """
    event_id = payload.get("id") or payload.get("data", {}).get("id", "")
    event_key = f"charge.success:{event_id}"

    with transaction.atomic():
        # Idempotency: if already processed, skip
        if WebhookEventLog.objects.filter(event_key=event_key).exists():
            logger.info("Duplicate webhook event: %s", event_key)
            return "duplicate"

        # Lock row to prevent race on concurrent webhook deliveries
        log = WebhookEventLog.objects.create(
            event_key=event_key,
            event_type="charge.success",
            payload=payload,
            status="ok",
        )

        data = payload.get("data", {})
        reference = data.get("reference", "")
        amount = data.get("amount", 0)
        currency = data.get("currency", "")
        status = data.get("status", "")

        if status != "success":
            log.status = "skipped"
            log.error_message = f"Unexpected status: {status}"
            log.save(update_fields=["status", "error_message"])
            return "skipped"

        try:
            payment = (
                Payment.objects.select_for_update().get(reference=reference)
            )
        except Payment.DoesNotExist:
            log.status = "error"
            log.error_message = f"No Payment found for reference: {reference}"
            log.save(update_fields=["status", "error_message"])
            logger.error("Webhook: unknown reference %s", reference)
            return "skipped"

        plan_config = settings.PLANS.get(payment.plan)
        if not plan_config:
            log.status = "error"
            log.error_message = f"Unknown plan in payment: {payment.plan}"
            log.save(update_fields=["status", "error_message"])
            return "skipped"

        # Validate amount and currency
        if amount != plan_config["price_kobo"] or currency != "NGN":
            log.status = "error"
            log.error_message = (
                f"Amount/currency mismatch: got {amount} {currency}, "
                f"expected {plan_config['price_kobo']} NGN"
            )
            log.save(update_fields=["status", "error_message"])
            logger.error("Webhook amount mismatch for %s", reference)
            return "skipped"

        # Already processed payment
        if payment.status == "success":
            log.status = "skipped"
            log.error_message = "Payment already marked success"
            log.save(update_fields=["status", "error_message"])
            return "duplicate"

        # Activate subscription
        user = payment.user
        now = timezone.now()
        period_end = now + timedelta(days=30)

        # Deactivate any previous active subscription
        Subscription.objects.filter(user=user, status="active").update(status="cancelled")

        customer = data.get("customer", {})
        sub = Subscription.objects.create(
            user=user,
            plan=payment.plan,
            status="active",
            paystack_customer_code=customer.get("customer_code", ""),
            current_period_start=now,
            current_period_end=period_end,
        )

        payment.status = "success"
        payment.paystack_tx_id = str(data.get("id", ""))
        payment.subscription = sub
        payment.save(update_fields=["status", "paystack_tx_id", "subscription", "updated_at"])

        # Initialise usage ledger for the new period
        from apps.content.models import UsageLedger
        UsageLedger.objects.get_or_create(
            user=user,
            year=now.year,
            month=now.month,
            defaults={"words_used": 0},
        )

        logger.info(
            "Subscription activated for user=%s plan=%s ref=%s",
            user.id,
            payment.plan,
            reference,
        )
        return "processed"
