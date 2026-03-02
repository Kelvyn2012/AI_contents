"""
Billing views:
- /billing/           Billing page (plan status, upgrade)
- /billing/checkout/  POST — init Paystack transaction
- /billing/callback/  GET  — verify server-side (UX only)
- /billing/webhook/   POST — Paystack webhook (source of truth)
"""
import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.services import (
    initialize_checkout,
    process_charge_success_webhook,
    verify_transaction_server_side,
    verify_webhook_signature,
)
from apps.billing.models import Payment
from apps.content.services import usage_summary

logger = logging.getLogger(__name__)


@login_required
def billing_page(request):
    subscription = request.user.profile.active_subscription
    payments = Payment.objects.filter(user=request.user).order_by("-created_at")[:10]
    summary = usage_summary(request.user)
    return render(
        request,
        "billing/billing.html",
        {"subscription": subscription, "payments": payments, "summary": summary},
    )


@login_required
@require_POST
def checkout(request):
    plan = request.POST.get("plan", "pro")
    if plan not in ("pro",):
        messages.error(request, "Invalid plan selected.")
        return redirect("billing:billing_page")

    # Already on pro plan
    sub = request.user.profile.active_subscription
    if sub and sub.plan == plan and sub.is_active:
        messages.info(request, "You are already on the Pro plan.")
        return redirect("billing:billing_page")

    try:
        data = initialize_checkout(request.user, plan)
        return redirect(data["authorization_url"])
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("billing:billing_page")


@login_required
def payment_callback(request):
    """
    Paystack redirects here after payment attempt.
    We verify server-side for UX feedback, but the webhook is the source of truth.
    """
    reference = request.GET.get("reference", "")
    if not reference:
        messages.error(request, "Missing payment reference.")
        return redirect("billing:billing_page")

    try:
        data = verify_transaction_server_side(reference)
        status = data.get("data", {}).get("status", "")
        if status == "success":
            messages.success(
                request,
                "Payment received! Your subscription will be activated within moments.",
            )
        else:
            messages.warning(
                request,
                f"Payment status: {status}. Contact support if you were charged.",
            )
    except RuntimeError as exc:
        messages.warning(request, str(exc))

    return redirect("billing:billing_page")


@csrf_exempt
@require_POST
def webhook(request):
    """
    Paystack webhook endpoint.
    Validates HMAC-SHA512 signature then processes event idempotently.
    """
    signature = request.headers.get("X-Paystack-Signature", "")
    payload_bytes = request.body

    if not verify_webhook_signature(payload_bytes, signature):
        logger.warning("Webhook: invalid signature")
        return HttpResponse("Invalid signature", status=400)

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    event = payload.get("event", "")
    logger.info("Paystack webhook received: %s", event)

    if event == "charge.success":
        try:
            outcome = process_charge_success_webhook(payload)
            logger.info("Webhook outcome: %s", outcome)
        except Exception as exc:
            logger.error("Webhook processing error: %s", exc)
            # Return 200 to prevent Paystack from retrying on our bugs
            return HttpResponse("Error logged", status=200)

    # Always return 200 so Paystack stops retrying for unhandled events
    return HttpResponse("OK", status=200)


@login_required
def payment_success(request):
    return render(request, "billing/payment_success.html")


@login_required
def payment_failure(request):
    return render(request, "billing/payment_failure.html")
