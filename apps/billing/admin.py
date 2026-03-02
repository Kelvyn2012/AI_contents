from django.contrib import admin
from .models import Payment, Subscription, WebhookEventLog


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "current_period_start", "current_period_end", "created_at")
    list_filter = ("plan", "status")
    search_fields = ("user__username", "user__email", "paystack_customer_code")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    actions = ["cancel_subscription"]

    @admin.action(description="Cancel selected subscriptions")
    def cancel_subscription(self, request, queryset):
        updated = queryset.filter(status="active").update(status="cancelled")
        self.message_user(request, f"{updated} subscription(s) cancelled.")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "plan", "amount_naira", "status", "created_at")
    list_filter = ("status", "plan", "currency")
    search_fields = ("reference", "user__username", "paystack_tx_id")
    readonly_fields = ("reference", "created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.display(description="Amount (₦)")
    def amount_naira(self, obj):
        return f"₦{obj.amount_kobo / 100:,.0f}"


@admin.register(WebhookEventLog)
class WebhookEventLogAdmin(admin.ModelAdmin):
    list_display = ("event_key", "event_type", "status", "processed_at")
    list_filter = ("event_type", "status")
    search_fields = ("event_key",)
    readonly_fields = ("event_key", "event_type", "payload", "processed_at")
