from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "created_at", "active_plan")
    search_fields = ("user__username", "user__email", "company")
    readonly_fields = ("created_at",)

    @admin.display(description="Plan")
    def active_plan(self, obj):
        return obj.active_plan
