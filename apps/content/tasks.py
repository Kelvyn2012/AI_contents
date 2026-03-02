"""
Celery tasks:
- generate_content_task: runs AI generation, deducts usage
- monthly_usage_reset: resets words_used each month (beat schedule)
- export_pdf_task: generates a PDF export of a ContentGeneration
"""
import io
import logging
import os

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def generate_content_task(self, generation_id: int):
    """
    Main generation task. Updates status, calls AI, deducts usage.
    """
    from apps.content.models import ContentGeneration
    from apps.ai.services import generate_content
    from apps.content.services import deduct_usage

    try:
        gen = ContentGeneration.objects.select_related("project", "user").get(id=generation_id)
    except ContentGeneration.DoesNotExist:
        logger.error("ContentGeneration %s not found", generation_id)
        return

    gen.status = "running"
    gen.save(update_fields=["status", "updated_at"])

    try:
        result_text = generate_content(
            project=gen.project,
            content_type=gen.content_type,
            prompt_extra=gen.prompt_extra,
        )

        word_count = len(result_text.split())

        gen.result_text = result_text
        gen.word_count = word_count
        gen.status = "success"
        gen.save(update_fields=["result_text", "word_count", "status", "updated_at"])

        # Deduct usage only after successful generation
        deduct_usage(gen.user, word_count)
        logger.info(
            "Generation %s complete: %d words for user %s",
            generation_id,
            word_count,
            gen.user_id,
        )

    except Exception as exc:
        logger.error("Generation %s failed: %s", generation_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            gen.status = "failed"
            gen.error_message = str(exc)
            gen.save(update_fields=["status", "error_message", "updated_at"])


@shared_task
def monthly_usage_reset():
    """
    Reset words_used to 0 for the new month.
    Scheduled via Celery Beat on the 1st of each month.
    Creates new UsageLedger rows for the current month; old rows are kept for history.
    """
    from apps.content.models import UsageLedger
    from django.contrib.auth.models import User

    now = timezone.now()
    users = User.objects.filter(is_active=True)
    created_count = 0
    for user in users:
        _, created = UsageLedger.objects.get_or_create(
            user=user,
            year=now.year,
            month=now.month,
            defaults={"words_used": 0},
        )
        if created:
            created_count += 1

    logger.info("monthly_usage_reset: created %d new ledger rows", created_count)
    return created_count


@shared_task
def export_pdf_task(generation_id: int, user_id: int) -> str:
    """
    Export a ContentGeneration result to PDF.
    Returns the relative path to the generated PDF file.
    """
    from apps.content.models import ContentGeneration
    from django.template.loader import render_to_string
    import weasyprint

    try:
        gen = ContentGeneration.objects.select_related("project", "user").get(
            id=generation_id, user_id=user_id
        )
    except ContentGeneration.DoesNotExist:
        logger.error("Export: ContentGeneration %s not found", generation_id)
        return ""

    html_content = render_to_string(
        "content/export_pdf.html",
        {"generation": gen, "project": gen.project},
    )

    output_dir = os.path.join("media", "exports", str(user_id))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"generation_{generation_id}.pdf")

    try:
        weasyprint.HTML(string=html_content).write_pdf(output_path)
        logger.info("PDF export complete: %s", output_path)
        return output_path
    except Exception as exc:
        logger.error("PDF export failed: %s", exc)
        return ""
