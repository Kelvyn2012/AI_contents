"""Analytics / audit log for admin visibility."""
from django.db import models
from django.contrib.auth.models import User


class AuditEvent(models.Model):
    EVENT_TYPES = [
        ("generation_created", "Generation Created"),
        ("generation_success", "Generation Success"),
        ("generation_failed", "Generation Failed"),
        ("subscription_activated", "Subscription Activated"),
        ("subscription_cancelled", "Subscription Cancelled"),
        ("payment_success", "Payment Success"),
        ("payment_failed", "Payment Failed"),
        ("quota_exceeded", "Quota Exceeded"),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    metadata = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "event_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Audit({self.event_type}, user={self.user_id})"
