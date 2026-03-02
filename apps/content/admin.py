from django.contrib import admin
from .models import ContentGeneration, Project, UsageLedger


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "brand_name", "user", "tone", "created_at")
    list_filter = ("tone",)
    search_fields = ("name", "brand_name", "user__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ContentGeneration)
class ContentGenerationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "project", "content_type", "status", "word_count", "created_at")
    list_filter = ("status", "content_type")
    search_fields = ("user__username", "project__name")
    readonly_fields = ("created_at", "updated_at", "celery_task_id")
    date_hierarchy = "created_at"
    actions = ["retry_failed"]

    @admin.action(description="Re-queue failed generations")
    def retry_failed(self, request, queryset):
        from apps.content.tasks import generate_content_task
        count = 0
        for gen in queryset.filter(status="failed"):
            gen.status = "queued"
            gen.error_message = ""
            gen.save(update_fields=["status", "error_message"])
            generate_content_task.delay(gen.id)
            count += 1
        self.message_user(request, f"{count} generation(s) re-queued.")


@admin.register(UsageLedger)
class UsageLedgerAdmin(admin.ModelAdmin):
    list_display = ("user", "year", "month", "words_used", "updated_at")
    list_filter = ("year", "month")
    search_fields = ("user__username",)
    readonly_fields = ("created_at", "updated_at")
