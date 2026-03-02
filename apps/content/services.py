"""
Content service layer:
- Quota checks (server-side, before enqueue)
- Enqueue generation task
- Persist results + deduct usage atomically
- Rate limiting (DB-based, per user)
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import ContentGeneration, UsageLedger

logger = logging.getLogger(__name__)

PLAN_LIMITS = settings.PLANS


def get_plan_config(user) -> dict:
    plan = user.profile.active_plan
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def check_quota(user) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    Checks words/month AND checks active plan status.
    """
    plan_cfg = get_plan_config(user)
    ledger = UsageLedger.current_for(user)
    if ledger.words_used >= plan_cfg["words_per_month"]:
        return (
            False,
            f"Monthly word limit reached ({plan_cfg['words_per_month']:,} words). "
            "Upgrade your plan or wait for next month.",
        )
    return True, ""


def check_project_limit(user) -> tuple[bool, str]:
    plan_cfg = get_plan_config(user)
    count = user.projects.count()
    if count >= plan_cfg["max_projects"]:
        return (
            False,
            f"Project limit reached ({plan_cfg['max_projects']} projects). "
            "Upgrade to Pro for more projects.",
        )
    return True, ""


def check_rate_limit(user, window_seconds=60, max_requests=5) -> tuple[bool, str]:
    """
    Simple DB-based rate limiter: max_requests per window_seconds per user.
    """
    since = timezone.now() - timedelta(seconds=window_seconds)
    recent = ContentGeneration.objects.filter(
        user=user, created_at__gte=since
    ).count()
    if recent >= max_requests:
        return False, f"Rate limit: max {max_requests} generations per {window_seconds}s."
    return True, ""


def enqueue_generation(user, project, content_type: str, prompt_extra: str = "") -> ContentGeneration:
    """
    Quota-check then enqueue. Returns the ContentGeneration record.
    Raises ValueError with a user-facing message on limit violations.
    """
    # Rate limit
    ok, msg = check_rate_limit(user)
    if not ok:
        raise ValueError(msg)

    # Quota
    ok, msg = check_quota(user)
    if not ok:
        raise ValueError(msg)

    with transaction.atomic():
        gen = ContentGeneration.objects.create(
            user=user,
            project=project,
            content_type=content_type,
            prompt_extra=prompt_extra,
            status="queued",
        )

    # Import task here to avoid circular import
    from apps.content.tasks import generate_content_task

    result = generate_content_task.delay(gen.id)
    gen.celery_task_id = result.id
    gen.save(update_fields=["celery_task_id"])
    logger.info("Enqueued generation task %s for user %s", result.id, user.id)
    return gen


def deduct_usage(user, word_count: int):
    """
    Atomically increment words_used for current month.
    Called only AFTER successful generation.
    get_or_create ensures the ledger row exists before the update.
    """
    now = timezone.now()
    with transaction.atomic():
        # Ensure row exists (handles first generation of the month)
        ledger, _ = UsageLedger.objects.select_for_update().get_or_create(
            user=user,
            year=now.year,
            month=now.month,
            defaults={"words_used": 0},
        )
        UsageLedger.objects.filter(pk=ledger.pk).update(
            words_used=F("words_used") + word_count
        )
    logger.debug("Deducted %d words for user %s", word_count, user.id)


def usage_summary(user) -> dict:
    plan_cfg = get_plan_config(user)
    ledger = UsageLedger.current_for(user)
    used = ledger.words_used
    limit = plan_cfg["words_per_month"]
    return {
        "words_used": used,
        "words_limit": limit,
        "words_remaining": max(0, limit - used),
        "percent_used": min(100, round((used / limit) * 100)) if limit else 0,
        "plan": user.profile.active_plan,
        "plan_name": plan_cfg["name"],
    }
