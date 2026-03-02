import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Subscription(models.Model):
    PLAN_CHOICES = [("free", "Free"), ("pro", "Pro")]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    paystack_subscription_code = models.CharField(max_length=200, blank=True)
    paystack_customer_code = models.CharField(max_length=200, blank=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "current_period_end"]),
        ]

    def __str__(self):
        return f"Subscription({self.user.username}, {self.plan}, {self.status})"

    @property
    def is_active(self):
        if self.status != "active":
            return False
        if self.current_period_end and timezone.now() > self.current_period_end:
            return False
        return True


class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subscription = models.ForeignKey(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True
    )
    reference = models.CharField(max_length=200, unique=True)
    amount_kobo = models.PositiveIntegerField()
    currency = models.CharField(max_length=10, default="NGN")
    plan = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    paystack_tx_id = models.CharField(max_length=200, blank=True)
    paystack_access_code = models.CharField(max_length=200, blank=True)
    authorization_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return f"Payment({self.reference}, {self.status})"


class WebhookEventLog(models.Model):
    """Idempotency guard for Paystack webhook events."""

    event_key = models.CharField(max_length=500, unique=True)  # Paystack event id or computed hash
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[("ok", "OK"), ("error", "Error"), ("skipped", "Skipped")],
        default="ok",
    )
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["event_key"])]

    def __str__(self):
        return f"WebhookEvent({self.event_key}, {self.status})"
