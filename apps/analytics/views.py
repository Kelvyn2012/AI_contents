from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta

from apps.content.models import ContentGeneration, UsageLedger
from apps.billing.models import Payment, Subscription
from .models import AuditEvent


@staff_member_required
def analytics_dashboard(request):
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    stats = {
        "total_users": ContentGeneration.objects.values("user").distinct().count(),
        "total_generations": ContentGeneration.objects.count(),
        "successful_generations": ContentGeneration.objects.filter(status="success").count(),
        "total_words": ContentGeneration.objects.filter(status="success").aggregate(
            total=Sum("word_count")
        )["total"] or 0,
        "active_subs": Subscription.objects.filter(status="active", plan="pro").count(),
        "revenue_kobo": Payment.objects.filter(status="success").aggregate(
            total=Sum("amount_kobo")
        )["total"] or 0,
        "recent_events": AuditEvent.objects.select_related("user")[:20],
    }
    stats["revenue_naira"] = stats["revenue_kobo"] // 100

    content_types = (
        ContentGeneration.objects.values("content_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return render(
        request,
        "analytics/dashboard.html",
        {"stats": stats, "content_types": content_types},
    )
