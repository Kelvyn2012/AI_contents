from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "user", "ip_address", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("user__username", "event_type")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
